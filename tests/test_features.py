import unittest

from huya_ck.features.gift_thank.handler import consider as consider_gift
from huya_ck.features.gift_thank.merger import GiftMerger
from huya_ck.features.guard_thank.handler import consider as consider_guard
from huya_ck.features.noble_thank.handler import consider as consider_noble
from huya_ck.features.superfan_thank.handler import consider as consider_superfan
from huya_ck.features.welcome import handler as welcome_handler
from huya_ck.features.welcome.handler import consider as consider_welcome


class FakeDanmaku:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.submits: list[dict] = []

    def submit(self, text: str, *, source: str, event_id: str, reason: str, **kwargs) -> None:
        self.sent.append(text)
        self.submits.append({"text": text, "source": source, "event_id": event_id, "reason": reason})


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def enter_event(**overrides):
    event = {
        "type": "enter",
        "nick": "甲",
        "noble_name": "骑士",
        "noble_level": 2,
        "consume_level": 23,
        "has_guard": False,
        "guard_text": "",
        "guard_level": 0,
        "event_id": "a",
    }
    event.update(overrides)
    return event


def gift_event(**overrides):
    event = {
        "type": "gift",
        "sender_uid": "2002",
        "sender_nick": "乙",
        "item_id": "123",
        "item_name": "火箭",
        "count": 1,
        "value_fen": 500,
        "event_id": "e1",
    }
    event.update(overrides)
    return event


MERGE_CONFIG = {
    "enabled": True,
    "min_value_fen": 600,
    "min_unit_value_fen": 0,
    "template": "感谢{nick}送的{count}个{item_name}",
    "merge_quiet_ms": 3000,
    "merge_max_ms": 8000,
}


class FeatureTest(unittest.TestCase):
    def test_welcome_filters_noble(self) -> None:
        danmaku = FakeDanmaku()
        event = enter_event()
        consider_welcome(event, {"enabled": True, "min_noble_level": 4, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}, danmaku)
        self.assertEqual(danmaku.sent, [])
        consider_welcome(event, {"enabled": True, "min_noble_level": 2, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎甲哥进入直播间~"])

    def test_welcome_requires_both_noble_and_consume(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 2, "min_consume_level": 30, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        consider_welcome(enter_event(consume_level=23), cfg, danmaku)
        self.assertEqual(danmaku.sent, [])
        consider_welcome(enter_event(consume_level=32), cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎甲哥进入直播间~"])

    def test_welcome_guard_bypasses_thresholds(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 4, "min_consume_level": 30, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        event = enter_event(
            noble_level=None,
            noble_name="",
            consume_level=None,
            has_guard=True,
            guard_text="至尊守护V4圣剑",
            guard_level=4,
        )
        consider_welcome(event, cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎至尊守护甲哥进入直播间~"])

    def test_welcome_guard_tier_from_text(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 0, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        consider_welcome(enter_event(has_guard=True, guard_text="超级守护坐骑"), cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎超级守护甲哥进入直播间~"])
        danmaku.sent.clear()
        consider_welcome(enter_event(has_guard=True, guard_text="初爱守护V1"), cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎守护甲哥进入直播间~"])

    def test_welcome_guard_tier_from_level(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 0, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        consider_welcome(enter_event(has_guard=True, guard_text="", guard_level=4), cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎至尊守护甲哥进入直播间~"])
        danmaku.sent.clear()
        consider_welcome(enter_event(has_guard=True, guard_text="", guard_level=9), cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎守护甲哥进入直播间~"])

    def test_welcome_noble_prefix_for_duke_and_above(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 2, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        consider_welcome(enter_event(noble_name="公爵", noble_level=4), cfg, danmaku)
        consider_welcome(enter_event(noble_name="君王", noble_level=5), cfg, danmaku)
        consider_welcome(enter_event(noble_name="帝皇", noble_level=6), cfg, danmaku)
        consider_welcome(enter_event(noble_name="骑士", noble_level=2), cfg, danmaku)
        self.assertEqual(
            danmaku.sent,
            [
                "欢迎公爵甲哥进入直播间~",
                "欢迎君王甲哥进入直播间~",
                "欢迎帝皇甲哥进入直播间~",
                "欢迎甲哥进入直播间~",
            ],
        )

    def test_welcome_guard_prefix_wins_over_noble(self) -> None:
        danmaku = FakeDanmaku()
        cfg = {"enabled": True, "min_noble_level": 0, "min_consume_level": 0, "template": "欢迎{guard_prefix|noble_prefix}{nick}哥进入直播间~"}
        event = enter_event(noble_name="公爵", noble_level=4, has_guard=True, guard_text="至尊守护V4圣剑", guard_level=4)
        consider_welcome(event, cfg, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎至尊守护甲哥进入直播间~"])

    def test_gift_threshold(self) -> None:
        danmaku = FakeDanmaku()
        cheap = {"type": "gift", "sender_nick": "乙", "item_name": "磁铁", "count": 1, "value_fen": 100, "value_yuan": 1, "event_id": "b"}
        consider_gift(cheap, {"enabled": True, "min_value_fen": 600, "template": "谢谢{nick}的{item_name}"}, danmaku)
        self.assertEqual(danmaku.sent, [])
        rich = dict(cheap, value_fen=1000, value_yuan=10, item_name="火箭")
        consider_gift(rich, {"enabled": True, "min_value_fen": 600, "template": "谢谢{nick}的{item_name}"}, danmaku)
        self.assertEqual(danmaku.sent, ["谢谢乙的火箭"])

    def test_gift_unit_value_threshold(self) -> None:
        danmaku = FakeDanmaku()
        config = {
            "enabled": True,
            "min_value_fen": 600,
            "min_unit_value_fen": 200,
            "template": "感谢{nick}送的{count}个{item_name}",
        }
        cheap_bundle = {
            "type": "gift",
            "sender_nick": "乙",
            "item_name": "守护磁铁",
            "count": 10,
            "value_fen": 1000,
            "value_yuan": 10,
            "event_id": "bundle",
        }
        consider_gift(cheap_bundle, config, danmaku)
        self.assertEqual(danmaku.sent, [])

        expensive_single = dict(
            cheap_bundle,
            item_name="高价礼物",
            count=1,
            value_fen=1000,
            event_id="single",
        )
        consider_gift(expensive_single, config, danmaku)
        self.assertEqual(danmaku.sent, ["感谢乙送的1个高价礼物"])

    def test_guard_is_independent_from_gift_value(self) -> None:
        danmaku = FakeDanmaku()
        event = {
            "type": "guard_open",
            "nick": "丙",
            "action": "开通",
            "guard_name": "初爱守护",
            "banner_text": "在本直播间开通初爱守护V1",
            "event_id": "guard-1",
        }
        consider_guard(event, {"enabled": True, "template": "感谢{nick}为主播{action}{guard_name}!"}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢丙为主播开通初爱守护!"])

        malformed = {"type": "guard_open", "nick": "误判", "banner_text": "虎牙营收祝你发财"}
        consider_guard(malformed, {"enabled": True, "template": "感谢{nick}为主播{action}{guard_name}!"}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢丙为主播开通初爱守护!"])

    def test_superfan_always_uses_open_wording(self) -> None:
        danmaku = FakeDanmaku()
        config = {
            "enabled": True,
            "template": "感谢{nick}为主播{action}{superfan_name}!",
        }
        consider_superfan(
            {
                "type": "superfan_open",
                "nick": "甲",
                "action": "开通",
                "superfan_name": "超粉",
                "event_id": "sf-1",
            },
            config,
            danmaku,
        )
        consider_superfan(
            {
                "type": "superfan_open",
                "nick": "乙",
                "action": "续费",
                "superfan_name": "超粉PLUS",
                "event_id": "sf-2",
            },
            config,
            danmaku,
        )
        self.assertEqual(
            danmaku.sent,
            ["感谢甲为主播开通超粉!", "感谢乙为主播开通超粉PLUS!"],
        )

    def test_noble_open_and_renew_templates(self) -> None:
        danmaku = FakeDanmaku()
        config = {
            "enabled": True,
            "template": "感谢{nick}为主播{action}{noble_name}{months}个月!",
        }
        consider_noble(
            {
                "type": "noble_open",
                "nick": "甲",
                "action": "开通/升级",
                "noble_name": "骑士",
                "months": 1,
                "event_id": "noble-1",
            },
            config,
            danmaku,
        )
        consider_noble(
            {
                "type": "noble_open",
                "nick": "乙",
                "action": "续费",
                "noble_name": "剑士",
                "months": 3,
                "event_id": "noble-2",
            },
            config,
            danmaku,
        )
        self.assertEqual(
            danmaku.sent,
            ["感谢甲为主播开通/升级骑士1个月!", "感谢乙为主播续费剑士3个月!"],
        )


class WelcomeCooldownTest(unittest.TestCase):
    def setUp(self) -> None:
        welcome_handler.reset()
        self.clock = FakeClock()
        self._orig_clock = welcome_handler._clock
        welcome_handler._clock = self.clock
        self.addCleanup(setattr, welcome_handler, "_clock", self._orig_clock)
        self.danmaku = FakeDanmaku()
        self.cfg = {
            "enabled": True,
            "min_noble_level": 2,
            "min_consume_level": 0,
            "template": "欢迎{nick}哥进入直播间~",
            "cooldown_ms": 30000,
        }

    def test_cooldown_blocks_second_visit(self) -> None:
        consider_welcome(enter_event(uid="1001", event_id="a"), self.cfg, self.danmaku)
        consider_welcome(enter_event(uid="1001", event_id="b"), self.cfg, self.danmaku)
        self.assertEqual(self.danmaku.sent, ["欢迎甲哥进入直播间~"])

    def test_cooldown_expires(self) -> None:
        consider_welcome(enter_event(uid="1001", event_id="a"), self.cfg, self.danmaku)
        self.clock.advance(31)
        consider_welcome(enter_event(uid="1001", event_id="b"), self.cfg, self.danmaku)
        self.assertEqual(self.danmaku.sent, ["欢迎甲哥进入直播间~", "欢迎甲哥进入直播间~"])

    def test_zero_cooldown_welcomes_every_visit(self) -> None:
        cfg = dict(self.cfg, cooldown_ms=0)
        consider_welcome(enter_event(uid="1001", event_id="a"), cfg, self.danmaku)
        consider_welcome(enter_event(uid="1001", event_id="b"), cfg, self.danmaku)
        self.assertEqual(len(self.danmaku.sent), 2)

    def test_different_uids_independent(self) -> None:
        consider_welcome(enter_event(uid="1001", event_id="a"), self.cfg, self.danmaku)
        consider_welcome(enter_event(uid="1002", nick="丙", event_id="b"), self.cfg, self.danmaku)
        self.assertEqual(self.danmaku.sent, ["欢迎甲哥进入直播间~", "欢迎丙哥进入直播间~"])

    def test_no_uid_skips_cooldown(self) -> None:
        consider_welcome(enter_event(event_id="a"), self.cfg, self.danmaku)
        consider_welcome(enter_event(event_id="b"), self.cfg, self.danmaku)
        self.assertEqual(len(self.danmaku.sent), 2)

    def test_guard_bypasses_thresholds_but_not_cooldown(self) -> None:
        cfg = dict(self.cfg, min_noble_level=4, min_consume_level=30)
        event = enter_event(
            uid="1001",
            noble_level=None,
            noble_name="",
            consume_level=None,
            has_guard=True,
            guard_text="超级守护坐骑",
        )
        consider_welcome(event, cfg, self.danmaku)
        consider_welcome(event, cfg, self.danmaku)
        self.assertEqual(self.danmaku.sent, ["欢迎甲哥进入直播间~"])

    def test_below_threshold_does_not_start_cooldown(self) -> None:
        cfg = dict(self.cfg, min_noble_level=4)
        consider_welcome(enter_event(uid="1001", event_id="a"), cfg, self.danmaku)
        consider_welcome(enter_event(uid="1001", event_id="b"), self.cfg, self.danmaku)
        self.assertEqual(self.danmaku.sent, ["欢迎甲哥进入直播间~"])


class GiftMergeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = FakeClock()
        self.merger = GiftMerger(clock=self.clock)
        self.danmaku = FakeDanmaku()

    def consider(self, **overrides) -> None:
        self.merger.consider(gift_event(**overrides), MERGE_CONFIG, self.danmaku)

    def tick(self, config=None) -> None:
        self.merger.tick(config=config if config is not None else MERGE_CONFIG, send_enabled=True)

    def test_combo_merges_within_quiet(self) -> None:
        self.consider(event_id="e1")
        self.clock.advance(1)
        self.consider(event_id="e2", count=2, value_fen=1000)
        self.assertEqual(self.danmaku.sent, [])
        self.clock.advance(3.1)
        self.tick()
        self.assertEqual(self.danmaku.sent, ["感谢乙送的3个火箭"])
        self.assertEqual(self.danmaku.submits[0]["event_id"], "merge:2002:123:e1")

    def test_different_item_or_uid_not_merged(self) -> None:
        self.consider(event_id="e1")
        self.clock.advance(0.5)
        self.consider(event_id="e2", item_id="999", item_name="飞机")
        self.clock.advance(0.5)
        self.consider(event_id="e3", sender_uid="2003", sender_nick="丁")
        self.clock.advance(3.5)
        self.tick()
        self.assertEqual(len(self.danmaku.sent), 0)  # 各窗口单独都低于门槛

    def test_combined_passes_threshold(self) -> None:
        self.consider(event_id="e1", value_fen=300)
        self.clock.advance(1)
        self.consider(event_id="e2", value_fen=400)
        self.clock.advance(3.1)
        self.tick()
        self.assertEqual(self.danmaku.sent, ["感谢乙送的2个火箭"])

    def test_combined_below_threshold_dropped(self) -> None:
        self.consider(event_id="e1", value_fen=100)
        self.clock.advance(1)
        self.consider(event_id="e2", value_fen=200)
        self.clock.advance(3.1)
        self.tick()
        self.assertEqual(self.danmaku.sent, [])

    def test_zero_value_not_queued(self) -> None:
        self.consider(event_id="e1", value_fen=0)
        self.clock.advance(5)
        self.tick()
        self.assertEqual(self.danmaku.sent, [])
        self.assertFalse(self.merger.busy())

    def test_quiet_zero_disables_merge(self) -> None:
        config = dict(MERGE_CONFIG, merge_quiet_ms=0)
        self.merger.consider(gift_event(event_id="e1", value_fen=700), config, self.danmaku)
        self.merger.consider(gift_event(event_id="e2", value_fen=700), config, self.danmaku)
        self.assertEqual(len(self.danmaku.sent), 2)

    def test_max_wait_forces_settlement(self) -> None:
        self.consider(event_id="e1", value_fen=700)
        for i in range(1, 8):
            self.clock.advance(1)
            self.consider(event_id=f"e{i+1}", value_fen=700)
        # 静默一直没到 3 秒，但窗口已满 8 秒：强制结算
        self.clock.advance(1)
        self.tick()
        self.assertEqual(self.danmaku.sent, ["感谢乙送的8个火箭"])
        # 之后的包开新窗口
        self.consider(event_id="e9", value_fen=700)
        self.assertEqual(len(self.danmaku.sent), 1)

    def test_reset_drops_windows(self) -> None:
        self.consider(event_id="e1", value_fen=700)
        self.merger.reset(reason="测试")
        self.clock.advance(5)
        self.tick()
        self.assertEqual(self.danmaku.sent, [])

    def test_tick_drops_windows_when_disabled(self) -> None:
        self.consider(event_id="e1", value_fen=700)
        self.merger.tick(config=dict(MERGE_CONFIG, enabled=False), send_enabled=True)
        self.assertFalse(self.merger.busy())
        self.clock.advance(5)
        self.tick()
        self.assertEqual(self.danmaku.sent, [])
