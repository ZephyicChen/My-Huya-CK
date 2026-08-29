"""领域事件分给事件模块。"""

from __future__ import annotations

import hashlib
from collections import deque

from huya_ck.features.danmaku.handler import danmaku
from huya_ck.features.gift_thank.handler import consider as consider_gift
from huya_ck.features.guard_thank.handler import consider as consider_guard
from huya_ck.features.noble_thank.handler import consider as consider_noble
from huya_ck.features.superfan_thank.handler import consider as consider_superfan
from huya_ck.features.welcome.handler import consider as consider_welcome
from huya_ck.log import get_logger
from huya_ck.platform import config_store

log = get_logger()

_HANDLERS = {
    "enter": consider_welcome,
    "gift": consider_gift,
    "guard_open": consider_guard,
    "noble_open": consider_noble,
    "superfan_open": consider_superfan,
}

_recent: deque[str] = deque(maxlen=400)
_seen: set[str] = set()


def event_id_for(event: dict) -> str:
    if event.get("type") == "gift" and event.get("order_id"):
        detail = f"order:{event.get('order_id')}"
    else:
        detail = event.get("item_name") or event.get("banner_text")
    raw = f"{event.get('uri')}|{event.get('uid') or event.get('sender_uid')}|{event.get('nick') or event.get('sender_nick')}|{detail}"
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:16]


def emit(event: dict) -> None:
    if not event:
        return
    eid = event.get("event_id") or event_id_for(event)
    event["event_id"] = eid
    if eid in _seen:
        return
    if len(_recent) == _recent.maxlen:
        old = _recent.popleft()
        _seen.discard(old)
    _recent.append(eid)
    _seen.add(eid)

    kind = event.get("type")
    handler = _HANDLERS.get(kind)
    if handler is None:
        return
    feature_id = {
        "enter": "welcome",
        "gift": "gift_thank",
        "guard_open": "guard_thank",
        "noble_open": "noble_thank",
        "superfan_open": "superfan_thank",
    }[kind]
    cfg = config_store.feature_config(feature_id)
    try:
        handler(event, cfg, danmaku)
    except Exception:
        log.exception("模块 %s 处理失败", feature_id)
