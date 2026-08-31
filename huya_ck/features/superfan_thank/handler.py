from __future__ import annotations

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.template import nick_values, render
from huya_ck.log import get_logger

log = get_logger()

DEFAULT_TEMPLATE = "感谢{nick}为主播开通{superfan_name}!"
SUPERFAN_NAMES = {"超粉", "超粉PLUS"}


def consider(event: dict, config: dict, danmaku: Danmaku) -> None:
    if event.get("type") != "superfan_open":
        return
    nick = str(event.get("nick") or "").strip()
    superfan_name = str(event.get("superfan_name") or "").strip()
    if not nick or superfan_name not in SUPERFAN_NAMES:
        log.info(
            "superfan_thank 关键字段不完整，忽略（用户=%s，类型=%s）",
            nick or "未知",
            superfan_name or "未知",
        )
        return
    if not config.get("enabled"):
        log.info("superfan_thank 关闭，忽略 %s", nick)
        return
    action = "开通"
    text = render(
        str(config.get("template") or ""),
        {
            "action": action,
            "superfan_name": superfan_name,
            **nick_values(event.get("uid"), nick),
        },
    ) or render(DEFAULT_TEMPLATE, {**nick_values(event.get("uid"), nick), "superfan_name": superfan_name})
    danmaku.submit(
        text,
        source="superfan_thank",
        event_id=str(event.get("event_id") or ""),
        reason=event.get("banner_text") or f"{action}{superfan_name}",
    )
