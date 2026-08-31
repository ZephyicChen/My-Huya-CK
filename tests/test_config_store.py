import json
import tempfile
import unittest
from pathlib import Path

from huya_ck.platform import config_store


class ConfigStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"

    def test_missing_file_uses_defaults(self) -> None:
        doc = config_store.load(self.tmp)
        self.assertEqual(doc["room"], "")
        self.assertFalse(doc["show_browser"])
        self.assertFalse(doc["welcome"]["enabled"])
        self.assertFalse(doc["gift_thank"]["enabled"])
        self.assertFalse(doc["superfan_thank"]["enabled"])
        self.assertFalse(doc["noble_thank"]["enabled"])
        self.assertFalse(doc["guard_thank"]["enabled"])
        self.assertFalse(doc["danmaku"]["enabled"])
        self.assertEqual(doc["gift_thank"]["min_value_fen"], 600)
        self.assertEqual(doc["gift_thank"]["min_unit_value_fen"], 0)
        self.assertEqual(doc["chat_control"], {"owner_uid": "", "owner_nick": "", "whitelist": []})

    def test_put_feature_persists(self) -> None:
        config_store.put_platform({"room": "123456"}, self.tmp)
        config_store.put_feature("gift_thank", {"min_value_fen": 1000}, self.tmp)
        saved = json.loads(self.tmp.read_text(encoding="utf-8"))
        self.assertEqual(saved["room"], "123456")
        self.assertEqual(saved["gift_thank"]["min_value_fen"], 1000)
        self.assertEqual(
            saved["gift_thank"]["template"],
            "感谢{nick}送的{count}个{item_name}",
        )

    def test_unknown_feature(self) -> None:
        with self.assertRaises(KeyError):
            config_store.put_feature("nope", {}, self.tmp)

    def test_chat_control_normalizes_and_authorizes(self) -> None:
        config = config_store.put_chat_control(
            {
                "owner_uid": "9007199254740999",
                "owner_nick": "本人",
                "whitelist": [
                    {
                        "uid": "8",
                        "nick": "助手",
                        "enabled": True,
                        "allowed_modules": ["gift_thank", "unknown"],
                        "allow_interaction": False,
                    },
                    {"uid": "8", "nick": "重复"},
                    {"uid": "9007199254740999", "nick": "本人重复"},
                ],
            },
            self.tmp,
        )
        self.assertEqual(len(config["whitelist"]), 1)
        self.assertEqual(config["whitelist"][0]["allowed_modules"], ["gift_thank"])
        self.assertEqual(config_store.chat_authorization("9007199254740999", config_store.load(self.tmp))["role"], "owner")
        self.assertEqual(config_store.chat_authorization("8", config_store.load(self.tmp))["role"], "whitelist")
        self.assertIsNone(config_store.chat_authorization("9", config_store.load(self.tmp)))

    def test_nick_overrides_parse_and_display(self) -> None:
        config_store.put_nick_overrides(
            [
                {"uid": " 111 ", "alias": " 大哥 ", "note": "x" * 100, "enabled": True},
                {"uid": "222", "alias": "停用", "enabled": False},
                {"uid": "111", "alias": "重复"},
                {"uid": "", "alias": "无UID"},
                {"uid": "333", "alias": ""},
            ],
            self.tmp,
        )
        doc = config_store.load(self.tmp)
        overrides = config_store.nick_overrides_config(doc)
        self.assertEqual([item["uid"] for item in overrides], ["111", "222"])
        self.assertEqual(overrides[0]["alias"], "大哥")
        self.assertEqual(len(overrides[0]["note"]), 80)

        # display_nick：命中→alias；禁用条目→实时昵称；未命中→实时昵称
        self.assertEqual(config_store.display_nick("111", "abc", doc), "大哥")
        self.assertEqual(config_store.display_nick("222", "abc", doc), "abc")
        self.assertEqual(config_store.display_nick("999", "abc", doc), "abc")

    def test_display_nick_owner_fallback(self) -> None:
        config_store.put_chat_control({"owner_uid": "1", "owner_nick": "本人"}, self.tmp)
        doc = config_store.load(self.tmp)
        # 昵称映射优先于 owner 备注
        config_store.put_nick_overrides([{"uid": "1", "alias": "大哥"}], self.tmp)
        doc = config_store.load(self.tmp)
        self.assertEqual(config_store.display_nick("1", "abc", doc), "大哥")
        # 无映射时 owner 备注生效
        config_store.put_nick_overrides([], self.tmp)
        doc = config_store.load(self.tmp)
        self.assertEqual(config_store.display_nick("1", "abc", doc), "本人")
        # 其他人不受影响
        self.assertEqual(config_store.display_nick("2", "abc", doc), "abc")
