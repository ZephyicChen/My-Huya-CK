import unittest
from huya_ck.platform.official_taf import (
    OFFICIAL_TAF_BRIDGE_SCRIPT,
    attach_official_taf,
    normalize_official_6110,
    normalize_official_6501,
    normalize_official_6540,
    normalize_official_1001,
    normalize_official_10079,
)


class _FakePage:
    def __init__(self) -> None:
        self.functions = {}
        self.scripts = []

    def expose_function(self, name, callback) -> None:
        self.functions[name] = callback

    def add_init_script(self, *, script) -> None:
        self.scripts.append(script)


def _badge(level: int) -> list[int]:
    if not -128 <= level <= 127:
        raise ValueError("测试徽章等级必须能用 int8 表示")
    return [0x10, level & 0xFF]


class OfficialTafTest(unittest.TestCase):
    def test_normalizes_official_event_and_badge(self) -> None:
        event = normalize_official_6110(
            {
                "uid": "9007199254740999",
                "nick": "神罗天征",
                "room_uid": "123",
                "noble_name": "骑士",
                "noble_level": "2",
                "guard_uid": "0",
                "guard_level": "0",
                "guard_text": "",
                "decoration_prefix": [{"app_id": 11200, "data": _badge(24)}],
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["uid"], 9007199254740999)
        self.assertEqual(event["nick"], "神罗天征")
        self.assertEqual(event["consume_level"], 24)
        self.assertEqual(event["noble_level"], 2)
        self.assertFalse(event["has_guard"])

    def test_attach_exposes_bridge_once(self) -> None:
        page = _FakePage()
        seen = []
        attach_official_taf(page, seen.append)
        attach_official_taf(page, seen.append)
        self.assertEqual(
            set(page.functions),
            {
                "__huya_ck_on_6110",
                "__huya_ck_on_6501",
                "__huya_ck_on_6540",
                "__huya_ck_on_1001",
                "__huya_ck_on_10079",
                "__huya_ck_taf_status",
            },
        )
        self.assertEqual(len(page.scripts), 1)
        page.functions["__huya_ck_on_6110"](
            {"uid": "7", "nick": "测试", "room_uid": "123", "noble_level": "1", "decoration_prefix": []}
        )
        self.assertEqual(seen[0]["nick"], "测试")
        page.functions["__huya_ck_on_6540"](
            {
                "uid": "8",
                "nick": "守护测试",
                "banner_text": "在本直播间开通初爱守护V1",
            }
        )
        self.assertEqual(seen[1]["type"], "guard_open")
        self.assertEqual(seen[1]["nick"], "守护测试")
        page.functions["__huya_ck_on_1001"](
            {
                "uid": "9",
                "nick": "贵族测试",
                "noble_name": "剑士",
                "room_id": "123",
                "open_flag": "2",
                "pay_month": "3",
            }
        )
        self.assertEqual(seen[2]["type"], "noble_open")
        self.assertEqual(seen[2]["months"], 3)
        page.functions["__huya_ck_on_1001"](
            {
                "nick": "其他房间贵族",
                "noble_name": "公爵",
                "room_id": "999",
                "open_flag": "1",
                "pay_month": "1",
            }
        )
        self.assertEqual(len(seen), 3)
        page.functions["__huya_ck_on_10079"](
            {
                "nick": "超粉测试",
                "action_text": "开通了超粉!",
                "event_time_ms": "1000",
                "event_seq": "1",
            }
        )
        self.assertEqual(seen[3]["type"], "superfan_open")
        self.assertEqual(seen[3]["action"], "开通")

    def test_bridge_subscribes_all_business_uris(self) -> None:
        for uri in (1001, 6110, 6501, 6540, 10079, 2001231):
            self.assertIn(f'signal.addTafListener("{uri}"', OFFICIAL_TAF_BRIDGE_SCRIPT)

    def test_normalizes_superfan_to_open_wording(self) -> None:
        opened = normalize_official_10079(
            {
                "nick": "甲",
                "action_text": "开通了超粉!",
                "event_time_ms": "1000",
                "event_seq": "1",
            }
        )
        self.assertIsNotNone(opened)
        assert opened is not None
        self.assertEqual(opened["action"], "开通")
        self.assertEqual(opened["superfan_name"], "超粉")

        renewed = normalize_official_10079(
            {
                "uri": "2001231",
                "nick": "乙",
                "action_text": "超粉Plus续费富文本曝光",
                "text_values": ["乙", '{"barrage_name":"超粉Plus续费富文本曝光"}'],
            }
        )
        self.assertIsNotNone(renewed)
        assert renewed is not None
        self.assertEqual(renewed["action"], "开通")
        self.assertEqual(renewed["superfan_name"], "超粉PLUS")
        self.assertEqual(renewed["uri"], 2001231)
        self.assertIsNone(normalize_official_10079({"nick": "丙", "action_text": "其他通知"}))

    def test_normalizes_noble_open_flag_and_months(self) -> None:
        opened = normalize_official_1001(
            {
                "uid": "1185944472",
                "nick": "贵族用户A",
                "noble_name": "骑士",
                "noble_level": "2",
                "open_flag": "1",
                "pay_month": "1",
            }
        )
        self.assertIsNotNone(opened)
        assert opened is not None
        self.assertEqual(opened["action"], "开通/升级")
        self.assertEqual(opened["months"], 1)

        renewed = normalize_official_1001(
            {
                "nick": "贵族用户B",
                "noble_name": "剑士",
                "open_flag": "2",
                "open_days": "90",
            }
        )
        self.assertIsNotNone(renewed)
        assert renewed is not None
        self.assertEqual(renewed["action"], "续费")
        self.assertEqual(renewed["months"], 3)
        self.assertIsNone(normalize_official_1001({"nick": "缺字段", "noble_name": "剑士"}))

    def test_normalizes_official_gift(self) -> None:
        event = normalize_official_6501(
            {
                "item_id": "35",
                "order_id": "pay-123",
                "count": "1",
                "value_fen": "100",
                "sender_uid": "9007199254740999",
                "sender_nick": "送礼用户",
                "anchor_nick": "主播",
                "item_name": "守护磁铁",
                "room_id": "12345678",
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["sender_nick"], "送礼用户")
        self.assertEqual(event["item_name"], "守护磁铁")
        self.assertEqual(event["value_fen"], 100)
        self.assertEqual(event["value_yuan"], 1)
        self.assertEqual(event["order_id"], "pay-123")

    def test_normalizes_guard_with_taf_fields(self) -> None:
        event = normalize_official_6540(
            {
                "uid": "9007199254740999",
                "nick": "守护用户",
                "room_id": "12345678",
                "banner_text": "在本直播间升级初爱守护 1次，荣升为初爱守护V4",
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["type"], "guard_open")
        self.assertEqual(event["uri"], 6540)
        self.assertEqual(event["nick"], "守护用户")
        self.assertEqual(event["action"], "升级")
        self.assertEqual(event["guard_name"], "初爱守护")

    def test_guard_accepts_union_id_but_rejects_missing_identity(self) -> None:
        event = normalize_official_6540(
            {
                "union_id": "union-user",
                "nick": "超粉用户",
                "banner_text": "在本直播间开通超级守护V1",
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["union_id"], "union-user")
        self.assertEqual(event["action"], "开通")
        self.assertEqual(event["guard_name"], "超级守护")
        self.assertIsNone(
            normalize_official_6540(
                {"nick": "没有标识", "banner_text": "在本直播间开通初爱守护V1"}
            )
        )
        self.assertIsNone(normalize_official_6540({"uid": "7", "banner_text": "在本直播间开通初爱守护V1"}))
        self.assertIsNone(normalize_official_6540({"uid": "7", "nick": "误判", "banner_text": "虎牙营收祝你发财"}))


if __name__ == "__main__":
    unittest.main()
