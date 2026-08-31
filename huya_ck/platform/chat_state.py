"""弹幕识别的有界内存状态；未授权用户的正文不会保存。"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict, deque
from typing import Any

from huya_ck.platform import config_store


class ChatState:
    def __init__(self, *, speaker_limit: int = 100, record_limit: int = 200) -> None:
        self._lock = threading.Lock()
        self._speakers: OrderedDict[str, dict] = OrderedDict()
        self._records: deque[dict] = deque(maxlen=record_limit)
        self._outbound: deque[tuple[float, str]] = deque(maxlen=80)
        self._speaker_limit = speaker_limit
        self._attached = False
        self._last_message_at: float | None = None
        self._authorized_count = 0
        self._ignored_count = 0
        self._command_seq = 0
        self._last_command: dict | None = None

    def mark_attached(self) -> None:
        with self._lock:
            self._attached = True

    def reset_connection(self) -> None:
        with self._lock:
            self._attached = False

    def remember_outbound(self, text: str, *, observed_at: float | None = None) -> None:
        clean = str(text or "").strip()
        if not clean:
            return
        now = time.monotonic() if observed_at is None else observed_at
        with self._lock:
            self._prune_outbound(now)
            self._outbound.append((now, clean))

    def is_recent_outbound(self, text: str) -> bool:
        clean = str(text or "").strip()
        if not clean:
            return False
        with self._lock:
            self._prune_outbound(time.monotonic())
            return any(item == clean for _, item in self._outbound)

    def observe(self, event: dict, *, is_outbound: bool = False) -> dict | None:
        uid = str(event.get("uid") or "").strip()
        nick = str(event.get("nick") or "").strip()[:80]
        content = str(event.get("content") or "").strip()
        if not uid or not nick or not content:
            return None
        now = time.time()
        authorization = config_store.chat_authorization(uid)
        display = config_store.display_nick(uid, nick)
        with self._lock:
            self._last_message_at = now
            self._speakers.pop(uid, None)
            self._speakers[uid] = {"uid": uid, "nick": nick, "display_nick": display, "last_seen": now}
            while len(self._speakers) > self._speaker_limit:
                self._speakers.popitem(last=False)
            if is_outbound:
                self._ignored_count += 1
                return None
            if authorization is None:
                self._ignored_count += 1
                return None
            record = {
                "time": now,
                "uid": uid,
                "nick": nick,
                "display_nick": display,
                "content": content,
                "role": authorization["role"],
            }
            self._records.append(record)
            self._authorized_count += 1
            return {**authorization, "record": dict(record)}

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "attached": self._attached,
                "last_message_at": self._last_message_at,
                "authorized_count": self._authorized_count,
                "ignored_count": self._ignored_count,
                "command_seq": self._command_seq,
                "last_command": dict(self._last_command) if self._last_command else None,
                "recent_speakers": [dict(item) for item in reversed(self._speakers.values())],
                "records": [dict(item) for item in reversed(self._records)],
            }

    def clear(self) -> None:
        with self._lock:
            self._speakers.clear()
            self._records.clear()
            self._outbound.clear()
            self._last_message_at = None
            self._authorized_count = 0
            self._ignored_count = 0
            self._command_seq = 0
            self._last_command = None

    def record_command(self, event: dict, result: dict) -> None:
        with self._lock:
            self._command_seq += 1
            self._last_command = {
                "time": time.time(),
                "uid": str(event.get("uid") or ""),
                "nick": str(event.get("nick") or "")[:80],
                "action": str(result.get("action") or ""),
                "target": str(result.get("target") or ""),
                "ok": bool(result.get("ok")),
                "changed_modules": list(result.get("changed_modules") or []),
                "reason": str(result.get("reason") or ""),
            }

    def _prune_outbound(self, now: float) -> None:
        while self._outbound and now - self._outbound[0][0] > 15:
            self._outbound.popleft()


chat_state = ChatState()
