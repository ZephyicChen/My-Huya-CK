"""房间工人：在独立线程里跑同步 Playwright，避免堵住 WebUI。"""

from __future__ import annotations

import queue
import threading
import time
from typing import Any

from playwright.sync_api import Error as PlaywrightError

from huya_ck.features.danmaku.handler import danmaku
from huya_ck.features.novel.player import novel_player
from huya_ck.log import get_logger
from huya_ck.platform.channel import channel_state
from huya_ck.platform.chat_state import chat_state
from huya_ck.platform.official_taf import attach_official_taf
from huya_ck.platform.session import HUYA_HOME, current_page, launch_persistent, room_url

log = get_logger()

CHANNEL_SILENCE_SECONDS = 120
CHANNEL_STARTUP_GRACE = 15


def _is_target_closed(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "targetclosederror" in text or "target page, context or browser has been closed" in text


def _close(pw, context) -> tuple[None, None]:
    if context is not None:
        try:
            context.close()
        except Exception:
            pass
    if pw is not None:
        try:
            pw.stop()
        except Exception:
            pass
    return None, None


class RoomWorker:
    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._running = False
        self._logged_in: bool | None = None
        self._headless: bool | None = None
        self._message = "先填房间、设好欢迎和感谢，再点启动。"
        self._room = ""
        self._started_at = 0.0
        self._thread = threading.Thread(target=self._loop, name="huya-ck-worker", daemon=True)
        self._thread.start()
        log.info("工人线程已就绪（关命令行窗口即退出整个场控）")

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            state = {
                "running": self._running,
                "logged_in": self._logged_in,
                "headless": self._headless,
                "room": self._room,
                "message": self._message,
            }
        state["taf_connected"] = channel_state.is_connected()
        state.update(danmaku.snapshot())
        return state

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            if "running" in kwargs:
                self._running = bool(kwargs["running"])
            if "logged_in" in kwargs:
                self._logged_in = kwargs["logged_in"]
            if "headless" in kwargs:
                self._headless = kwargs["headless"]
            if "message" in kwargs:
                self._message = str(kwargs["message"])
            if "room" in kwargs:
                self._room = str(kwargs["room"])

    def login(self) -> dict[str, Any]:
        return self._ask("login", None, timeout=90)

    def start(self, room: str, *, headless: bool = True) -> dict[str, Any]:
        room = (room or "").strip()
        if not room:
            self._set(message="请先填写房间号。")
            return {"ok": False, "status": self.snapshot(), "message": "请先填写房间号。"}
        try:
            url = room_url(room)
        except ValueError as exc:
            self._set(message=str(exc))
            return {"ok": False, "status": self.snapshot(), "message": str(exc)}
        return self._ask("start", {"url": url, "headless": bool(headless)}, timeout=90)

    def stop(self) -> dict[str, Any]:
        return self._ask("stop", None, timeout=30)

    def shutdown(self) -> None:
        try:
            self._ask("quit", None, timeout=15)
        except Exception:
            pass

    def _ask(self, cmd: str, payload: Any, timeout: float) -> dict[str, Any]:
        reply: queue.Queue = queue.Queue()
        self._queue.put((cmd, payload, reply))
        try:
            result = reply.get(timeout=timeout)
        except queue.Empty:
            message = "操作超时。登录需要弹出窗口；启动场控默认在后台，可打开「显示直播间窗口」排查。"
            self._set(message=message)
            return {"ok": False, "status": self.snapshot(), "message": message}
        return result

    def _is_running(self) -> bool:
        with self._lock:
            return self._running

    def _pump_playwright(self, context) -> None:
        """同步 Playwright 只在调用 API 时分发 WS 回调。挂房后必须继续泵，否则收不到进场/礼物。"""
        if context is None:
            return
        pages = list(context.pages)
        if not pages:
            return
        page = pages[0]
        try:
            page.wait_for_timeout(200)
        except Exception:
            return
        if self._is_running() and time.monotonic() - self._started_at > CHANNEL_STARTUP_GRACE:
            silent_for = time.monotonic() - channel_state.last_activity()
            if not channel_state.is_connected():
                if channel_state.ever_connected():
                    log.info("事件通道已断开（收到 close）")
                else:
                    log.info("事件通道从未连上（页面可能没加载或被验证码/登录挡住）")
                self._rehang(page)
                return
            if silent_for > CHANNEL_SILENCE_SECONDS:
                log.info("事件通道已静默 %d 秒，视为假死", int(silent_for))
                self._rehang(page)
                return
        danmaku.pump(page)
        novel_player.tick()

    def _rehang(self, page) -> None:
        """TAF 通道断开：重新进直播间让页面重建订阅。"""
        room = ""
        with self._lock:
            room = self._room
        self._started_at = time.monotonic()
        if not room:
            return
        log.info("事件通道断开，重新进入直播间 %s", room)
        try:
            channel_state.reset()
            chat_state.reset_connection()
            page.goto(room, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(2000)
            log.info("直播间已重新挂上")
        except Exception as exc:
            log.info("重新挂房失败：%s（稍后再试）", exc)

    def _open_room(self, context, url: str):
        """登录可能切换页面；目标页在准备阶段关闭时，重新选择最新页面再试。"""
        last_error: PlaywrightError | None = None
        for attempt in range(2):
            page = current_page(context)
            try:
                attach_official_taf(page)
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)
                return page
            except PlaywrightError as exc:
                if not _is_target_closed(exc) or attempt == 1:
                    raise
                last_error = exc
                log.info("登录页面发生切换，自动改用新页面重新进入直播间")
        if last_error is not None:
            raise last_error
        raise RuntimeError("没有可用的直播间页面")

    def _next_command(self, context):
        if self._is_running() and context is not None:
            try:
                return self._queue.get(timeout=0.05)
            except queue.Empty:
                self._pump_playwright(context)
                return None
        return self._queue.get()

    def _loop(self) -> None:
        pw = None
        context = None
        ctx_headless: bool | None = None
        while True:
            item = self._next_command(context)
            if item is None:
                continue
            cmd, payload, reply = item
            try:
                if cmd in ("stop", "quit"):
                    log.info("停止挂房，关闭后台浏览器")
                    danmaku.clear()
                    novel_player.pause(reason="已停止挂房")
                    channel_state.reset()
                    chat_state.reset_connection()
                    pw, context = _close(pw, context)
                    ctx_headless = None
                    self._set(running=False, headless=None, room="", message="已停止挂房。命令行窗口仍在，可再次启动。")
                    reply.put(
                        {
                            "ok": True,
                            "status": self.snapshot(),
                            "message": "已停止挂房。关掉命令行窗口才会退出场控。",
                        }
                    )
                    if cmd == "quit":
                        log.info("场控进程退出")
                        break
                    continue

                want_headless = False if cmd == "login" else bool(payload.get("headless", True))
                if context is not None and ctx_headless != want_headless:
                    pw, context = _close(pw, context)
                    ctx_headless = None

                if context is None:
                    log.info("启动 Chromium（%s）", "无窗口" if want_headless else "显示窗口")
                    pw, context = launch_persistent(headless=want_headless)
                    ctx_headless = want_headless
                    self._set(headless=want_headless)

                page = current_page(context)
                if cmd == "login":
                    log.info("打开登录页 %s", HUYA_HOME)
                    page.goto(HUYA_HOME, wait_until="domcontentloaded", timeout=30000)
                    self._set(message="已打开浏览器，请在窗口里完成登录。")
                    reply.put(
                        {
                            "ok": True,
                            "status": self.snapshot(),
                            "message": "已打开浏览器，请在窗口里完成登录。登录后再点启动场控，正式运行默认不弹出直播间窗口。",
                        }
                    )
                    continue

                if cmd == "start":
                    url = str(payload["url"])
                    log.info("进入直播间 %s", url)
                    channel_state.reset()
                    chat_state.reset_connection()
                    page = self._open_room(context, url)
                    log.info("直播间已挂上（%s），持续监听弹幕、进场、礼物和开通", "后台无窗口" if want_headless else "有窗口")
                    if want_headless:
                        message = "已在后台进入直播间（无窗口）。场控页可点停止。"
                    else:
                        message = "已打开直播间窗口，将一直挂着。"
                    self._set(running=True, room=url, message=message)
                    self._started_at = time.monotonic()
                    reply.put({"ok": True, "status": self.snapshot(), "message": message})
                    continue

                reply.put(
                    {
                        "ok": False,
                        "status": self.snapshot(),
                        "message": f"未知命令: {cmd}",
                    }
                )
            except Exception as exc:
                if _is_target_closed(exc):
                    pw, context = _close(pw, context)
                    ctx_headless = None
                    self._set(running=False, headless=None)
                message = f"启动失败: {exc}"
                log.exception("%s", message)
                self._set(message=message)
                reply.put({"ok": False, "status": self.snapshot(), "message": message})


worker = RoomWorker()
