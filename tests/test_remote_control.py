import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huya_ck.features.remote_control.handler import execute, parse_command
from huya_ck.platform import config_store


class _Queue:
    def __init__(self) -> None:
        self.clear_count = 0

    def clear(self) -> None:
        self.clear_count += 1


class RemoteControlTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"
        self.path_patch = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp)
        self.record_patch = patch("huya_ck.features.remote_control.handler.chat_state.record_command")
        self.path_patch.start()
        self.record_command = self.record_patch.start()
        config_store.put_chat_control(
            {
                "owner_uid": "1",
                "owner_nick": "本人",
                "whitelist": [
                    {
                        "uid": "2",
                        "nick": "礼物助手",
                        "enabled": True,
                        "allowed_modules": ["gift_thank"],
                    },
                    {
                        "uid": "3",
                        "nick": "无权限助手",
                        "enabled": True,
                        "allowed_modules": [],
                    },
                ],
            }
        )
        self.queue = _Queue()

    def tearDown(self) -> None:
        self.record_patch.stop()
        self.path_patch.stop()

    def test_parser_is_strict_but_allows_spacing_and_case(self) -> None:
        self.assertEqual(parse_command("lu开启欢迎")["target"], "欢迎")
        self.assertFalse(parse_command(" LU 关闭 感谢！ ")["enabled"])
        self.assertIsNone(parse_command("大家LU开启欢迎吧"))
        self.assertIsNone(parse_command("LU 开启 未知"))

    def test_owner_controls_all_thank_modules(self) -> None:
        result = execute({"uid": 1, "nick": "本人", "content": "LU 开启 感谢"}, self.queue)
        self.assertTrue(result["ok"])
        self.assertEqual(
            result["changed_modules"],
            ["gift_thank", "guard_thank", "superfan_thank", "noble_thank"],
        )
        for feature_id in result["changed_modules"]:
            self.assertTrue(config_store.feature_config(feature_id)["enabled"])

    def test_whitelist_thank_only_changes_permitted_subset(self) -> None:
        config_store.set_features_enabled(
            ["gift_thank", "guard_thank", "superfan_thank", "noble_thank"], True
        )
        result = execute({"uid": 2, "nick": "礼物助手", "content": "LU关闭感谢"}, self.queue)
        self.assertEqual(result["changed_modules"], ["gift_thank"])
        self.assertFalse(config_store.feature_config("gift_thank")["enabled"])
        self.assertTrue(config_store.feature_config("guard_thank")["enabled"])

    def test_disabling_send_clears_queue(self) -> None:
        config_store.set_features_enabled(["danmaku"], True)
        result = execute({"uid": 1, "nick": "本人", "content": "LU 关闭 发送"}, self.queue)
        self.assertTrue(result["ok"])
        self.assertFalse(config_store.feature_config("danmaku")["enabled"])
        self.assertEqual(self.queue.clear_count, 1)

    def test_whitelist_without_target_permission_is_rejected(self) -> None:
        result = execute({"uid": 3, "nick": "无权限助手", "content": "LU开启欢迎"}, self.queue)
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "forbidden")
        self.assertFalse(config_store.feature_config("welcome")["enabled"])


if __name__ == "__main__":
    unittest.main()
