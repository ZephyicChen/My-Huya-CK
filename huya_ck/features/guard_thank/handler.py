from __future__ import annotations

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.template import nick_values, render
from huya_ck.log import get_logger

log = get_logger()

DEFAULT_TEMPLATE = "感谢{nick}为主播{action}{guard_name}!"
GUARD_NAMES = {"初爱守护", "超级守护", "至尊守护"}
GUARD_ACTIONS = {"开通", "升级"}


def consider(event: dict, config: dict, danmaku: Danmaku) -> None:
    if event.get("type") != "guard_open":
        return
    nick = str(event.get("nick") or "").strip()
    action = str(event.get("action") or "").strip()
    guard_name = str(event.get("guard_name") or "").strip()
    if not nick or action not in GUARD_ACTIONS or guard_name not in GUARD_NAMES:
        log.info(
            "guard_thank 关键字段不完整，忽略（用户=%s，动作=%s，守护=%s）",
            nick or "未知",
            action or "未知",
            guard_name or "未知",
        )
        return
    if not config.get("enabled"):
        log.info("guard_thank 关闭，忽略 %s", nick)
        return
    values = {"action": action, "guard_name": guard_name, **nick_values(event.get("uid"), nick)}
    text = render(str(config.get("template") or ""), values) or render(DEFAULT_TEMPLATE, values)
    danmaku.submit(
        text,
        source="guard_thank",
        event_id=str(event.get("event_id") or ""),
        reason=event.get("banner_text") or f"{action}{guard_name}",
    )
