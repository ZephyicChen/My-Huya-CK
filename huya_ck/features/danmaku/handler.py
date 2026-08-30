"""弹幕发送队列。其它模块只调用 submit；真正点输入框在工人线程的 pump 里。"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from huya_ck.log import get_logger
from huya_ck.platform import config_store
from huya_ck.platform.chat_state import chat_state

log = get_logger()

INPUT_SELECTORS = ("#pub_msg_input", "input[name='msg']", "textarea.chat-input")
SEND_SELECTORS = ("#msg_send_bt", "a.chat-send", "button.chat-send")

# 虎牙弹幕输入框上限约 30 字；超长只记日志提示，不拦截
MAX_TEXT_CHARS = 28


def _find_visible(page: Any, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                return selector
        except Exception:
            continue
    return None


def _notify(callback: Any, ok: bool) -> None:
    if callback is None:
        return
    try:
        callback(ok)
    except Exception:
        log.exception("发送结果回调失败")


def _type_into_page(page: Any, text: str) -> bool:
    input_selector = _find_visible(page, INPUT_SELECTORS)
    send_selector = _find_visible(page, SEND_SELECTORS)
    if not input_selector or not send_selector:
        return False
    page.fill(input_selector, text, timeout=2000)
    page.click(send_selector, timeout=2000)
    return True


PRIORITIES = {"low": 0, "normal": 1, "high": 2}


class Danmaku:
    def __init__(self) -> None:
        self._queue: deque[dict] = deque()
        self._lock = threading.Lock()
        self._last_sent_at: float | None = None

    def submit(
        self,
        text: str,
        *,
        source: str,
        event_id: str,
        reason: str,
        priority: str = "normal",
        on_result: Any = None,
    ) -> None:
        """on_result(ok: bool) 在发送尝试结束后被调用一次（工人线程）。"""
        text = (text or "").strip()
        if not text:
            return
        if len(text) > MAX_TEXT_CHARS:
            # 超长只提示，不拦截：虎牙输入框实际 30 字，是否放行由发送端决定
            log.info("弹幕超长（%d 字 > %d），仍尝试发送 [%s] %s", len(text), MAX_TEXT_CHARS, source, text)
        cfg = config_store.feature_config("danmaku")
        if not cfg.get("enabled"):
            log.info("danmaku 关闭，丢弃 [%s] %s", source, text)
            if on_result is not None:
                _notify(on_result, False)
            return
        queue_max = max(1, int(cfg.get("queue_max") or 1))
        level = PRIORITIES.get(priority, PRIORITIES["normal"])
        dropped = None
        with self._lock:
            if len(self._queue) >= queue_max:
                dropped = self._pick_drop_candidate()
                if dropped is not None:
                    self._queue.remove(dropped)
            self._queue.append(
                {
                    "priority": level,
                    "text": text,
                    "source": source,
                    "event_id": event_id,
                    "reason": reason,
                    "on_result": on_result,
                }
            )
        if dropped is not None:
            log.info("danmaku 队列已满，挤掉最旧的 [%s] %s", dropped["source"], dropped["text"])
            _notify(dropped.get("on_result"), False)
        log.info("入队 [%s] %s （%s / %s / %s）", source, text, reason, event_id, priority)

    def _pick_drop_candidate(self) -> dict | None:
        """队列满时优先挤掉最旧的一条低优先级消息。"""
        if not self._queue:
            return None
        for level in sorted({item["priority"] for item in self._queue}):
            for item in self._queue:
                if item["priority"] == level:
                    return item
        return None

    def pump(self, page: Any) -> None:
        """工人线程专用：到间隔取一条往输入框发。失败记日志，不重试。"""
        item = self._pop_due()
        if item is None or page is None:
            return
        ok = False
        try:
            ok = _type_into_page(page, item["text"])
        except Exception as exc:
            log.info("发送异常 [%s] %s：%s", item["source"], item["text"], exc)
        if ok:
            sent_at = self._mark_sent()
            chat_state.remember_outbound(item["text"], observed_at=sent_at)
            log.info("已发送 [%s] %s （%s / %s）", item["source"], item["text"], item["reason"], item["event_id"])
        else:
            log.info(
                "发送失败 [%s] %s：未找到可见输入框/发送按钮。无窗口看不到输入框时，可勾选「显示直播间窗口」再启动",
                item["source"],
                item["text"],
            )
        _notify(item.get("on_result"), ok)

    def clear(self) -> None:
        with self._lock:
            dropped = list(self._queue)
            self._queue.clear()
        if dropped:
            log.info("danmaku 队列已清空（%s 条）", len(dropped))
        for item in dropped:
            _notify(item.get("on_result"), False)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {"queue_size": len(self._queue)}

    def _pop_due(self) -> dict | None:
        with self._lock:
            if not self._queue:
                return None
            cfg = config_store.feature_config("danmaku")
            interval_ms = max(0, int(cfg.get("interval_ms") or 0))
            if (
                self._last_sent_at is not None
                and time.monotonic() - self._last_sent_at < interval_ms / 1000.0
            ):
                return None
            # 同优先级先进先出，高优先级先出；都不绕过全局发送 CD
            best_index = 0
            for index, item in enumerate(self._queue):
                if item["priority"] > self._queue[best_index]["priority"]:
                    best_index = index
            if best_index == 0:
                return self._queue.popleft()
            item = self._queue[best_index]
            del self._queue[best_index]
            return item

    def _mark_sent(self) -> float:
        """只有网页发送按钮成功点击后才开始计算下一条的 CD。"""
        sent_at = time.monotonic()
        with self._lock:
            self._last_sent_at = sent_at
        return sent_at


danmaku = Danmaku()
