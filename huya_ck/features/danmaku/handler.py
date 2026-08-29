"""弹幕发送队列。其它模块只调用 submit；真正点输入框在工人线程的 pump 里。"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from huya_ck.log import get_logger
from huya_ck.platform import config_store

log = get_logger()

INPUT_SELECTORS = ("#pub_msg_input", "input[name='msg']", "textarea.chat-input")
SEND_SELECTORS = ("#msg_send_bt", "a.chat-send", "button.chat-send")


def _find_visible(page: Any, selectors: tuple[str, ...]) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible(timeout=500):
                return selector
        except Exception:
            continue
    return None


def _type_into_page(page: Any, text: str) -> bool:
    input_selector = _find_visible(page, INPUT_SELECTORS)
    send_selector = _find_visible(page, SEND_SELECTORS)
    if not input_selector or not send_selector:
        return False
    page.fill(input_selector, text, timeout=2000)
    page.click(send_selector, timeout=2000)
    return True


class Danmaku:
    def __init__(self) -> None:
        self._queue: deque[tuple[str, str, str, str]] = deque()
        self._lock = threading.Lock()
        self._last_sent_at: float | None = None

    def submit(self, text: str, *, source: str, event_id: str, reason: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        cfg = config_store.feature_config("danmaku")
        if not cfg.get("enabled"):
            log.info("danmaku 关闭，丢弃 [%s] %s", source, text)
            return
        queue_max = max(1, int(cfg.get("queue_max") or 1))
        dropped = None
        with self._lock:
            if len(self._queue) >= queue_max:
                dropped = self._queue.popleft()
            self._queue.append((text, source, event_id, reason))
        if dropped is not None:
            log.info("danmaku 队列已满，挤掉最旧的 [%s] %s", dropped[1], dropped[0])
        log.info("入队 [%s] %s （%s / %s）", source, text, reason, event_id)

    def pump(self, page: Any) -> None:
        """工人线程专用：到间隔取一条往输入框发。失败记日志，不重试。"""
        item = self._pop_due()
        if item is None or page is None:
            return
        text, source, event_id, reason = item
        try:
            ok = _type_into_page(page, text)
        except Exception as exc:
            log.info("发送异常 [%s] %s：%s", source, text, exc)
            return
        if ok:
            self._mark_sent()
            log.info("已发送 [%s] %s （%s / %s）", source, text, reason, event_id)
        else:
            log.info(
                "发送失败 [%s] %s：未找到可见输入框/发送按钮。无窗口看不到输入框时，可勾选「显示直播间窗口」再启动",
                source,
                text,
            )

    def clear(self) -> None:
        with self._lock:
            dropped = len(self._queue)
            self._queue.clear()
        if dropped:
            log.info("danmaku 队列已清空（%s 条）", dropped)

    def _pop_due(self) -> tuple[str, str, str, str] | None:
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
            return self._queue.popleft()

    def _mark_sent(self) -> None:
        """只有网页发送按钮成功点击后才开始计算下一条的 CD。"""
        with self._lock:
            self._last_sent_at = time.monotonic()


danmaku = Danmaku()
