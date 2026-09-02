from __future__ import annotations

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.template import nick_values, render
from huya_ck.log import get_logger

log = get_logger()

DEFAULT_TEMPLATE = "感谢{nick}送的{count}个{item_name}"


def _fill(template: str, event: dict) -> str:
    return render(
        template or DEFAULT_TEMPLATE,
        {
            **nick_values(event.get("sender_uid"), event.get("sender_nick") or ""),
            "item_name": event.get("item_name") or "",
            "count": event.get("count") or 1,
            "value_yuan": event.get("value_yuan") if event.get("value_yuan") is not None else "",
        },
    )


def consider(event: dict, config: dict, danmaku: Danmaku) -> None:
    # 委托给连击合并器：关闭合并（merge_quiet_ms=0）或无法构成合并键时，
    # merger 内部回退到 _consider_direct 单包立刻判断。
    from huya_ck.features.gift_thank.merger import merger

    merger.consider(event, config, danmaku)


def _consider_direct(event: dict, config: dict, danmaku: Danmaku) -> None:
    """单包立刻判断（关闭合并时的现行逻辑）。"""
    nick = event.get("sender_nick") or "?"
    name = event.get("item_name") or "?"
    fen = int(event.get("value_fen") or 0)
    count = max(1, int(event.get("count") or 1))
    min_fen = int(config.get("min_value_fen") or 0)
    if fen < min_fen:
        log.info("gift_thank 低于门槛 %s<%s，忽略 %s %s", fen, min_fen, nick, name)
        return
    min_unit_fen = max(0, int(config.get("min_unit_value_fen") or 0))
    if fen < min_unit_fen * count:
        unit_fen = fen / count
        log.info(
            "gift_thank 单价低于门槛 %.2f<%s分，忽略 %s %s x%s",
            unit_fen,
            min_unit_fen,
            nick,
            name,
            count,
        )
        return
    text = _fill(str(config.get("template") or ""), event)
    danmaku.submit(
        text,
        source="gift_thank",
        event_id=str(event.get("event_id") or ""),
        reason=f"礼物 {name} {fen}分",
    )
