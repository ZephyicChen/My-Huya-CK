"""礼物连击合并：同人同礼物按静默窗口聚合，结算时用合计判断门槛。

不改变事件来源与总线去重：bus 仍按 order_id 挡官方重复回调；
连击是多个新订单，由本模块在 handler 之上合并。
窗口只存在内存，停止挂房 / 关闭发送 / 关闭感谢 / 更换房间时丢弃，不补发。
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from huya_ck.log import get_logger
from huya_ck.platform import config_store

log = get_logger()

FEATURE_ID = "gift_thank"


class GiftMerger:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self._pending: dict[tuple[str, str], dict[str, Any]] = {}

    # ---------- 事件入口（handler.consider 委托到这里） ----------

    def consider(self, event: dict, config: dict, danmaku_obj) -> None:
        if event.get("type") != "gift":
            return
        nick = event.get("sender_nick") or "?"
        name = event.get("item_name") or "?"
        fen = int(event.get("value_fen") or 0)
        count = max(1, int(event.get("count") or 1))
        if not config.get("enabled"):
            log.info("gift_thank 关闭，忽略 %s %s", nick, name)
            return
        if fen <= 0:
            log.info("gift_thank 0 元，忽略 %s %s", nick, name)
            return
        quiet_ms = int(config.get("merge_quiet_ms") or 0)
        uid = str(event.get("sender_uid") or "")
        item_key = str(event.get("item_id") or event.get("item_name") or "")
        if quiet_ms <= 0 or not uid or not item_key:
            self._consider_direct(event, config, danmaku_obj)
            return
        self._add(event, config, danmaku_obj, uid, item_key)

    # ---------- 调度（发送循环 tick） ----------

    def tick(self, config: dict | None = None, send_enabled: bool | None = None) -> None:
        """结算到期窗口。参数留空时读当前配置；单测可直接注入配置。"""
        if config is None:
            config = config_store.feature_config(FEATURE_ID)
        if send_enabled is None:
            send_enabled = bool(config_store.feature_config("danmaku").get("enabled"))
        if not config.get("enabled") or not send_enabled:
            self.reset(reason="模块或发送已关闭")
            return
        quiet_ms = int(config.get("merge_quiet_ms") or 0)
        with self._lock:
            if not self._pending:
                return
            now = self._clock()
            quiet_s = quiet_ms / 1000.0
            # 最长等待不短于静默时间
            max_s = (quiet_ms if int(config.get("merge_max_ms") or 0) <= 0
                     else max(quiet_ms, int(config.get("merge_max_ms") or 0))) / 1000.0
            due = []
            for key, win in list(self._pending.items()):
                quiet_due = quiet_s <= 0 or now - win["last_at"] >= quiet_s
                max_due = now - win["first_at"] >= max_s
                if quiet_due or max_due:
                    due.append(key)
            for key in due:
                win = self._pending.pop(key)
                self._settle(win, config)

    def busy(self) -> bool:
        with self._lock:
            return bool(self._pending)

    def reset(self, reason: str = "") -> None:
        with self._lock:
            count = len(self._pending)
            self._pending.clear()
        if count:
            log.info("gift_thank 丢弃 %d 个连击窗口（%s）", count, reason or "reset")

    # ---------- 内部 ----------

    def _add(self, event: dict, config: dict, danmaku_obj, uid: str, item_key: str) -> None:
        fen = int(event.get("value_fen") or 0)
        count = max(1, int(event.get("count") or 1))
        now = self._clock()
        with self._lock:
            win = self._pending.get((uid, item_key))
            if win is None:
                self._pending[(uid, item_key)] = {
                    "uid": uid,
                    "item_key": item_key,
                    "danmaku": danmaku_obj,
                    "nick": event.get("sender_nick") or "?",
                    "item_name": event.get("item_name") or "?",
                    "count": count,
                    "value_fen": fen,
                    "first_at": now,
                    "last_at": now,
                    "first_event_id": str(event.get("event_id") or ""),
                }
            else:
                win["nick"] = event.get("sender_nick") or win["nick"]
                win["item_name"] = event.get("item_name") or win["item_name"]
                win["count"] += count
                win["value_fen"] += fen
                win["last_at"] = now
            win = self._pending[(uid, item_key)]
            log.info(
                "gift_thank 暂存连击 %s %s，合计 %d 个 %d 分",
                win["nick"],
                win["item_name"],
                win["count"],
                win["value_fen"],
            )

    def _settle(self, win: dict, config: dict) -> None:
        nick = win["nick"]
        name = win["item_name"]
        count = max(1, int(win["count"]))
        fen = int(win["value_fen"])
        min_fen = int(config.get("min_value_fen") or 0)
        if fen < min_fen:
            log.info("gift_thank 连击合计低于门槛 %s<%s，忽略 %s %s", fen, min_fen, nick, name)
            return
        min_unit_fen = max(0, int(config.get("min_unit_value_fen") or 0))
        if fen < min_unit_fen * count:
            log.info(
                "gift_thank 连击单价低于门槛 %.2f<%s分，忽略 %s %s x%s",
                fen / count,
                min_unit_fen,
                nick,
                name,
                count,
            )
            return
        # 延迟导入避免 handler -> merger -> handler 循环
        from huya_ck.features.gift_thank import handler as handler_module

        text = handler_module._fill(
            str(config.get("template") or ""),
            {
                "sender_uid": win["uid"],
                "sender_nick": win["nick"],
                "item_name": win["item_name"],
                "count": count,
                "value_yuan": round(fen / 100, 2),
            },
        )
        danmaku_obj = win["danmaku"]
        danmaku_obj.submit(
            text,
            source="gift_thank",
            event_id=f"merge:{win['uid']}:{win['item_key']}:{win['first_event_id']}",
            reason=f"礼物(连击合并) {name} {count}个 {fen}分",
        )
        log.info("gift_thank 连击结算 %s %s x%s %d分", nick, name, count, fen)

    def _consider_direct(self, event: dict, config: dict, danmaku_obj) -> None:
        """关闭合并（或无法构成合并键）时，沿用单包立刻判断。"""
        # 延迟导入避免 handler -> merger -> handler 循环
        from huya_ck.features.gift_thank import handler as handler_module

        handler_module._consider_direct(event, config, danmaku_obj)


merger = GiftMerger()
