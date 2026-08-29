"""页面 TAF 业务通道的存活状态。"""

from __future__ import annotations

import threading
import time


class ChannelState:
    """只记录页面 TAF 桥的连接和最后活动时间。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[int] = set()
        self._last_activity = 0.0
        self._ever_connected = False

    def mark_connected(self, ident: int) -> None:
        with self._lock:
            self._active.add(ident)
            self._last_activity = time.monotonic()
            self._ever_connected = True

    def mark_closed(self, ident: int) -> None:
        with self._lock:
            self._active.discard(ident)

    def mark_activity(self) -> None:
        with self._lock:
            self._last_activity = time.monotonic()

    def last_activity(self) -> float:
        with self._lock:
            return self._last_activity

    def reset(self) -> None:
        with self._lock:
            self._active.clear()
            self._last_activity = time.monotonic()
            self._ever_connected = False

    def is_connected(self) -> bool:
        with self._lock:
            return bool(self._active)

    def ever_connected(self) -> bool:
        with self._lock:
            return self._ever_connected


channel_state = ChannelState()
