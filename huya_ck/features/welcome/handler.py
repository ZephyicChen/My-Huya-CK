from __future__ import annotations

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.template import nick_values, render
from huya_ck.log import get_logger

log = get_logger()

GUARD_TIERS = ("至尊守护", "超级守护", "初爱守护")
GUARD_TEXT_NAMES = {"至尊守护": "至尊守护", "超级守护": "超级守护", "初爱守护": "守护"}
GUARD_LEVEL_NAMES = {4: "至尊守护"}
HIGH_NOBLE_NAMES = ("公爵", "君王", "帝皇")
HIGH_NOBLE_LEVEL = 4

DEFAULT_TEMPLATE = "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"


def guard_prefix(event: dict) -> str:
    guard_text = str(event.get("guard_text") or "")
    for tier in GUARD_TIERS:
        if tier in guard_text:
            return GUARD_TEXT_NAMES[tier]
    level = event.get("guard_level")
    if level is not None:
        return GUARD_LEVEL_NAMES.get(int(level), "守护")
    return "守护"


def noble_prefix(event: dict) -> str:
    noble_name = str(event.get("noble_name") or "")
    if noble_name in HIGH_NOBLE_NAMES:
        return noble_name
    level = event.get("noble_level")
    if level is not None and int(level) >= HIGH_NOBLE_LEVEL:
        return noble_name
    return ""


def _fill(template: str, event: dict) -> str:
    return render(
        template or DEFAULT_TEMPLATE,
        {
            "guard_prefix": guard_prefix(event) if event.get("has_guard") else "",
            "noble_prefix": noble_prefix(event),
            **nick_values(event.get("uid"), event.get("nick") or ""),
            "noble_name": event.get("noble_name") or "",
            "noble_level": event.get("noble_level") if event.get("noble_level") is not None else "",
            "consume_level": event.get("consume_level") if event.get("consume_level") is not None else "",
            "has_guard": "yes" if event.get("has_guard") else "",
        },
    )


def _passes_thresholds(event: dict, config: dict) -> bool:
    min_noble = int(config.get("min_noble_level") or 0)
    noble_level = event.get("noble_level")
    if min_noble and (noble_level is None or int(noble_level) < min_noble):
        return False
    min_consume = int(config.get("min_consume_level") or 0)
    consume = event.get("consume_level")
    if min_consume and (consume is None or int(consume) < min_consume):
        return False
    return True


def consider(event: dict, config: dict, danmaku: Danmaku) -> None:
    if event.get("type") != "enter":
        return
    nick = event.get("nick") or "?"
    if not config.get("enabled"):
        log.info("welcome 关闭，忽略 %s", nick)
        return
    if event.get("has_guard"):
        log.info("welcome 有守护，欢迎 %s", nick)
    elif _passes_thresholds(event, config):
        log.info("welcome 贵族/消费达标，欢迎 %s", nick)
    else:
        log.info("welcome 贵族/消费不够且无守护，忽略 %s（%s / 消费%s）", nick, event.get("noble_name"), event.get("consume_level"))
        return
    text = _fill(str(config.get("template") or ""), event)
    danmaku.submit(
        text,
        source="welcome",
        event_id=str(event.get("event_id") or ""),
        reason=f"贵族进场 {event.get('noble_name') or ''}",
    )
