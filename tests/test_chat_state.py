import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huya_ck.platform import config_store
from huya_ck.platform.chat_state import ChatState


class ChatStateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()) / "app.json"
        self.patcher = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp)
        self.patcher.start()
        config_store.put_chat_control(
            {
                "owner_uid": "1",
                "owner_nick": "本人",
                "whitelist": [
                    {
                        "uid": "2",
                        "nick": "助手",
                        "enabled": True,
                        "allowed_modules": ["welcome"],
                        "allow_interaction": False,
                    },
                    {"uid": "4", "nick": "禁用", "enabled": False},
                ],
            }
        )
        self.state = ChatState(speaker_limit=2, record_limit=2)

    def tearDown(self) -> None:
        self.patcher.stop()

    def test_unauthorized_content_is_not_stored(self) -> None:
        result = self.state.observe({"uid": 3, "nick": "普通观众", "content": "不应保存"})
        self.assertIsNone(result)
        snapshot = self.state.snapshot()
        self.assertEqual(snapshot["records"], [])
        self.assertEqual(snapshot["recent_speakers"][0]["uid"], "3")
        self.assertNotIn("content", snapshot["recent_speakers"][0])

    def test_owner_and_enabled_whitelist_are_recorded(self) -> None:
        owner = self.state.observe({"uid": 1, "nick": "本人", "content": "测试一"})
        helper = self.state.observe({"uid": 2, "nick": "助手", "content": "测试二"})
        self.assertEqual(owner["role"], "owner")
        self.assertEqual(helper["allowed_modules"], ["welcome"])
        self.assertEqual([item["content"] for item in self.state.snapshot()["records"]], ["测试二", "测试一"])

    def test_disabled_and_outbound_messages_are_ignored(self) -> None:
        self.assertIsNone(self.state.observe({"uid": 4, "nick": "禁用", "content": "内容"}))
        self.state.remember_outbound("自动回复", observed_at=100.0)
        with patch("huya_ck.platform.chat_state.time.monotonic", return_value=101.0):
            self.assertTrue(self.state.is_recent_outbound("自动回复"))
        self.assertIsNone(self.state.observe({"uid": 1, "nick": "本人", "content": "自动回复"}, is_outbound=True))
        self.assertEqual(self.state.snapshot()["records"], [])

    def test_state_is_bounded(self) -> None:
        self.state.observe({"uid": 1, "nick": "本人", "content": "一"})
        self.state.observe({"uid": 2, "nick": "助手", "content": "二"})
        self.state.observe({"uid": 3, "nick": "普通", "content": "三"})
        self.assertEqual(len(self.state.snapshot()["recent_speakers"]), 2)


if __name__ == "__main__":
    unittest.main()
