from __future__ import annotations

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.template import render
from huya_ck.log import get_logger

log = get_logger()

DEFAULT_TEMPLATE = "感谢{nick}为主播{action}{noble_name}{months}个月!"
NOBLE_NAMES = {"剑士", "骑士", "领主", "公爵", "君王", "帝皇"}
NOBLE_ACTIONS = {"开通/升级", "续费"}


def consider(event: dict, config: dict, danmaku: Danmaku) -> None:
    if event.get("type") != "noble_open":
        return
    nick = str(event.get("nick") or "").strip()
    action = str(event.get("action") or "").strip()
    noble_name = str(event.get("noble_name") or "").strip()
    try:
        months = int(event.get("months"))
    except (TypeError, ValueError):
        months = 0
    if not nick or action not in NOBLE_ACTIONS or noble_name not in NOBLE_NAMES or months <= 0:
        log.info(
            "noble_thank 关键字段不完整，忽略（用户=%s，动作=%s，贵族=%s，月份=%s）",
            nick or "未知",
            action or "未知",
            noble_name or "未知",
            months or "未知",
        )
        return
    if not config.get("enabled"):
        log.info("noble_thank 关闭，忽略 %s", nick)
        return
    values = {
        "nick": nick,
        "action": action,
        "noble_name": noble_name,
        "months": months,
    }
    text = render(str(config.get("template") or ""), values) or render(DEFAULT_TEMPLATE, values)
    danmaku.submit(
        text,
        source="noble_thank",
        event_id=str(event.get("event_id") or ""),
        reason=event.get("banner_text") or f"{values['action']}{values['noble_name']}",
    )
