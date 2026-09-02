"""房间监督者：在 asyncio 事件循环里跑 Playwright，与 WebUI 同循环。

事件（进场/礼物/弹幕）由事件循环自动分发，不再需要同步 API 的“泵”；
发送队列、轮播 tick 和 TAF 健康检查各自是独立任务，重挂房期间 API 照常响应。
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from playwright.async_api import Error as PlaywrightError

from huya_ck.features.danmaku.handler import danmaku
from huya_ck.features.gift_thank.merger import merger
from huya_ck.features.novel.player import novel_player
from huya_ck.features.welcome import handler as welcome_handler
from huya_ck.log import get_logger
from huya_ck.platform.channel import channel_state
from huya_ck.platform.chat_state import chat_state
from huya_ck.platform.official_taf import attach_official_taf
from huya_ck.platform.session import HUYA_HOME, current_page, launch_persistent, room_url

log = get_logger()

CHANNEL_SILENCE_SECONDS = 120
CHANNEL_STARTUP_GRACE = 15
# 发送任务空闲睡眠上限：有消息立即醒，没消息最多睡这么久再检查一次轮播 tick
SEND_IDLE_SLEEP_SECONDS = 1.0
HEALTH_CHECK_INTERVAL = 5.0


def _is_target_closed(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "targetclosederror" in text or "target page, context or browser has been closed" in text


class RoomSupervisor:
    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._logged_in: bool | None = None
        self._headless: bool | None = None
        self._message = "先填房间、设好欢迎和感谢，再点启动。"
        self._room = ""
        self._started_at = 0.0
        self._task: asyncio.Task | None = None
        self._run_tasks: list[asyncio.Task] = []

    # ---------- 对外接口（事件循环里调用） ----------

    def ensure_started(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())
            log.info("房间监督任务已就绪（与 WebUI 同一事件循环）")

    def snapshot(self) -> dict[str, Any]:
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

    async def login(self) -> dict[str, Any]:
        return await self._ask("login", None, timeout=90)

    async def start(self, room: str, *, headless: bool = True) -> dict[str, Any]:
        room = (room or "").strip()
        if not room:
            self._set(message="请先填写房间号。")
            return {"ok": False, "status": self.snapshot(), "message": "请先填写房间号。"}
        try:
            url = room_url(room)
        except ValueError as exc:
            self._set(message=str(exc))
            return {"ok": False, "status": self.snapshot(), "message": str(exc)}
        return await self._ask("start", {"url": url, "headless": bool(headless)}, timeout=90)

    async def stop(self) -> dict[str, Any]:
        return await self._ask("stop", None, timeout=30)

    async def shutdown(self) -> None:
        try:
            await self._ask("quit", None, timeout=15)
        except Exception:
            pass
        self.cancel()

    def cancel(self) -> None:
        for task in self._run_tasks:
            task.cancel()
        self._run_tasks = []
        if self._task is not None:
            self._task.cancel()

    async def _ask(self, cmd: str, payload: Any, timeout: float) -> dict[str, Any]:
        self.ensure_started()
        reply: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put((cmd, payload, reply))
        try:
            result = await asyncio.wait_for(reply, timeout=timeout)
        except asyncio.TimeoutError:
            message = "操作超时。登录需要弹出窗口；启动场控默认在后台，可打开「显示直播间窗口」排查。"
            self._set(message=message)
            return {"ok": False, "status": self.snapshot(), "message": message}
        return result

    # ---------- 主循环 ----------

    async def _loop(self) -> None:
        pw = None
        context = None
        ctx_headless: bool | None = None
        while True:
            cmd, payload, reply = await self._queue.get()
            try:
                if cmd in ("stop", "quit"):
                    log.info("停止挂房，关闭后台浏览器")
                    await self._cancel_run_tasks()
                    danmaku.clear()
                    novel_player.pause(reason="已停止挂房")
                    welcome_handler.reset()
                    merger.reset(reason="停止挂房")
                    channel_state.reset()
                    chat_state.reset_connection()
                    pw, context = await self._close(pw, context)
                    ctx_headless = None
                    self._set(running=False, headless=None, room="", message="已停止挂房。命令行窗口仍在，可再次启动。")
                    self._reply(reply, {
                        "ok": True,
                        "status": self.snapshot(),
                        "message": "已停止挂房。关掉命令行窗口才会退出场控。",
                    })
                    if cmd == "quit":
                        log.info("场控进程退出")
                        return
                    continue

                want_headless = False if cmd == "login" else bool(payload.get("headless", True))
                if context is not None and ctx_headless != want_headless:
                    pw, context = await self._close(pw, context)
                    ctx_headless = None

                if context is None:
                    log.info("启动 Chromium（%s）", "无窗口" if want_headless else "显示窗口")
                    pw, context = await launch_persistent(headless=want_headless)
                    ctx_headless = want_headless
                    self._set(headless=want_headless)

                page = await current_page(context)
                if cmd == "login":
                    log.info("打开登录页 %s", HUYA_HOME)
                    await page.goto(HUYA_HOME, wait_until="domcontentloaded", timeout=30000)
                    self._set(message="已打开浏览器，请在窗口里完成登录。")
                    self._reply(reply, {
                        "ok": True,
                        "status": self.snapshot(),
                        "message": "已打开浏览器，请在窗口里完成登录。登录后再点启动场控，正式运行默认不弹出直播间窗口。",
                    })
                    continue

                if cmd == "start":
                    url = str(payload["url"])
                    log.info("进入直播间 %s", url)
                    channel_state.reset()
                    chat_state.reset_connection()
                    # 换房间：冷却表与未结算连击窗口属于上一场，全部清空
                    welcome_handler.reset()
                    merger.reset(reason="更换房间")
                    page = await self._open_room(context, url)
                    log.info("直播间已挂上（%s），持续监听弹幕、进场、礼物和开通", "后台无窗口" if want_headless else "有窗口")
                    if want_headless:
                        message = "已在后台进入直播间（无窗口）。场控页可点停止。"
                    else:
                        message = "已打开直播间窗口，将一直挂着。"
                    self._set(running=True, room=url, message=message)
                    self._started_at = time.monotonic()
                    await self._cancel_run_tasks()
                    self._spawn_run_tasks(page)
                    self._reply(reply, {"ok": True, "status": self.snapshot(), "message": message})
                    continue

                self._reply(reply, {
                    "ok": False,
                    "status": self.snapshot(),
                    "message": f"未知命令: {cmd}",
                })
            except Exception as exc:
                if _is_target_closed(exc):
                    await self._cancel_run_tasks()
                    pw, context = await self._close(pw, context)
                    ctx_headless = None
                    self._set(running=False, headless=None)
                message = f"启动失败: {exc}"
                log.exception("%s", message)
                self._set(message=message)
                self._reply(reply, {"ok": False, "status": self.snapshot(), "message": message})

    def _reply(self, reply: asyncio.Future, result: dict) -> None:
        if not reply.done():
            reply.set_result(result)

    # ---------- 运行期任务：发送 + 轮播 + 健康检查 ----------

    def _spawn_run_tasks(self, page) -> None:
        self._run_tasks = [
            asyncio.create_task(self._sender_loop(page)),
            asyncio.create_task(self._health_loop(page)),
        ]

    async def _cancel_run_tasks(self) -> None:
        tasks, self._run_tasks = self._run_tasks, []
        for task in tasks:
            task.cancel()
        for task in tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _sender_loop(self, page) -> None:
        """发送队列、轮播 tick 与礼物连击结算。空闲时等待唤醒事件；CD 未到时短暂等待。"""
        while True:
            await danmaku.pump(page)
            novel_player.tick()
            merger.tick()
            if danmaku.has_queued():
                # 队列有货但 CD 未到：保持原 200ms 节奏，不空转
                await asyncio.sleep(0.2)
            elif merger.busy():
                # 有未结算连击窗口：别睡满 1 秒，避免 3 秒静默被拖成 4 秒
                await asyncio.sleep(0.2)
            else:
                await danmaku.wait_work(SEND_IDLE_SLEEP_SECONDS)

    async def _health_loop(self, page) -> None:
        """TAF 通道存活检查。重挂房期间其他任务照常运行。"""
        while True:
            await asyncio.sleep(HEALTH_CHECK_INTERVAL)
            if not self._running:
                continue
            if time.monotonic() - self._started_at <= CHANNEL_STARTUP_GRACE:
                continue
            silent_for = time.monotonic() - channel_state.last_activity()
            if not channel_state.is_connected():
                if channel_state.ever_connected():
                    log.info("事件通道已断开（收到 close）")
                else:
                    log.info("事件通道从未连上（页面可能没加载或被验证码/登录挡住）")
                await self._rehang(page)
                continue
            if silent_for > CHANNEL_SILENCE_SECONDS:
                log.info("事件通道已静默 %d 秒，视为假死", int(silent_for))
                await self._rehang(page)

    async def _rehang(self, page) -> None:
        """TAF 通道断开：重新进直播间让页面重建订阅。"""
        room = self._room
        self._started_at = time.monotonic()
        if not room:
            return
        log.info("事件通道断开，重新进入直播间 %s", room)
        try:
            channel_state.reset()
            chat_state.reset_connection()
            await page.goto(room, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000)
            log.info("直播间已重新挂上")
        except Exception as exc:
            log.info("重新挂房失败：%s（稍后再试）", exc)

    async def _open_room(self, context, url: str):
        """登录可能切换页面；目标页在准备阶段关闭时，重新选择最新页面再试。"""
        last_error: PlaywrightError | None = None
        for attempt in range(2):
            page = await current_page(context)
            try:
                await attach_official_taf(page)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                await page.wait_for_timeout(2000)
                return page
            except PlaywrightError as exc:
                if not _is_target_closed(exc) or attempt == 1:
                    raise
                last_error = exc
                log.info("登录页面发生切换，自动改用新页面重新进入直播间")
        if last_error is not None:
            raise last_error
        raise RuntimeError("没有可用的直播间页面")

    async def _close(self, pw, context) -> tuple[None, None]:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
        if pw is not None:
            try:
                await pw.stop()
            except Exception:
                pass
        return None, None


worker = RoomSupervisor()
