import tempfile
import unittest
from pathlib import Path
from unittest import mock

from huya_ck.features.gift_thank.handler import consider as consider_gift
from huya_ck.features.guard_thank.handler import consider as consider_guard
from huya_ck.features.noble_thank.handler import consider as consider_noble
from huya_ck.features.superfan_thank.handler import consider as consider_superfan
from huya_ck.features.welcome.handler import consider as consider_welcome
from huya_ck.platform import config_store


class FakeDanmaku:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def submit(self, text: str, *, source: str, event_id: str, reason: str) -> None:
        self.sent.append(text)


class NickOverrideTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"
        patcher = mock.patch.object(config_store, "CONFIG_PATH", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        config_store.put_nick_overrides([{"uid": "111", "alias": "大哥"}], self.tmp)

    def test_welcome_uses_alias(self) -> None:
        danmaku = FakeDanmaku()
        event = {
            "type": "enter",
            "uid": "111",
            "nick": "abc123",
            "noble_name": "骑士",
            "noble_level": 2,
            "consume_level": 23,
            "has_guard": False,
            "guard_text": "",
            "guard_level": 0,
            "event_id": "a",
        }
        consider_welcome(event, {"enabled": True, "min_noble_level": 2, "min_consume_level": 0, "template": "欢迎{nick}哥进入直播间~"}, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎大哥哥进入直播间~"])

    def test_welcome_real_nick_variable(self) -> None:
        danmaku = FakeDanmaku()
        event = {
            "type": "enter",
            "uid": "111",
            "nick": "abc123",
            "noble_name": "骑士",
            "noble_level": 2,
            "consume_level": 23,
            "has_guard": False,
            "guard_text": "",
            "guard_level": 0,
            "event_id": "a",
        }
        consider_welcome(event, {"enabled": True, "min_noble_level": 2, "min_consume_level": 0, "template": "欢迎{nick}({real_nick})进入直播间~"}, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎大哥(abc123)进入直播间~"])

    def test_welcome_without_override_uses_real_nick(self) -> None:
        danmaku = FakeDanmaku()
        event = {
            "type": "enter",
            "uid": "999",
            "nick": "路人大哥",
            "noble_name": "骑士",
            "noble_level": 2,
            "consume_level": 23,
            "has_guard": False,
            "guard_text": "",
            "guard_level": 0,
            "event_id": "a",
        }
        consider_welcome(event, {"enabled": True, "min_noble_level": 2, "min_consume_level": 0, "template": "欢迎{nick}哥进入直播间~"}, danmaku)
        self.assertEqual(danmaku.sent, ["欢迎路人大哥哥进入直播间~"])

    def test_gift_uses_alias(self) -> None:
        danmaku = FakeDanmaku()
        event = {
            "type": "gift",
            "sender_uid": "111",
            "sender_nick": "abc123",
            "item_name": "虎牙一号",
            "count": 1,
            "value_fen": 1000,
            "event_id": "a",
        }
        consider_gift(event, {"enabled": True, "min_value_fen": 0, "min_unit_value_fen": 0, "template": ""}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢大哥送的1个虎牙一号"])

    def test_guard_uses_alias(self) -> None:
        danmaku = FakeDanmaku()
        event = {"type": "guard_open", "uid": "111", "nick": "abc123", "action": "开通", "guard_name": "超级守护", "event_id": "a"}
        consider_guard(event, {"enabled": True, "template": ""}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢大哥为主播开通超级守护!"])

    def test_superfan_uses_alias(self) -> None:
        danmaku = FakeDanmaku()
        event = {"type": "superfan_open", "uid": "111", "nick": "abc123", "superfan_name": "超粉PLUS", "event_id": "a"}
        consider_superfan(event, {"enabled": True, "template": ""}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢大哥为主播开通超粉PLUS!"])

    def test_noble_uses_alias(self) -> None:
        danmaku = FakeDanmaku()
        event = {"type": "noble_open", "uid": "111", "nick": "abc123", "action": "续费", "noble_name": "骑士", "months": 1, "event_id": "a"}
        consider_noble(event, {"enabled": True, "template": ""}, danmaku)
        self.assertEqual(danmaku.sent, ["感谢大哥为主播续费骑士1个月!"])


if __name__ == "__main__":
    unittest.main()
