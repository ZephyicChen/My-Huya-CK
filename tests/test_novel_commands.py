import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huya_ck.features.novel import handler as novel_handler
from huya_ck.features.novel.library import NovelLibrary
from huya_ck.features.novel.player import NovelPlayer
from huya_ck.platform import config_store

TEXT = "。".join(f"第{i}段的内容" for i in range(6)) + "。"


class _Recorder:
    def __init__(self) -> None:
        self.submitted = []

    def submit(self, text, *, source, event_id, reason, priority="normal", on_result=None):
        self.submitted.append({"text": text, "priority": priority, "on_result": on_result})


def _fake_feature_config(feature_id, doc=None):
    if feature_id == "danmaku":
        return {"enabled": True, "interval_ms": 0, "queue_max": 20}
    return {}


class NovelCommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path_patch = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp / "app.json")
        self.path_patch.start()
        self.library = NovelLibrary(self.tmp / "novels")
        for target in (
            "huya_ck.features.novel.player.library_module.library",
            "huya_ck.api.novels.library",
        ):
            patch(target, self.library).start()
        self.recorder = _Recorder()
        patch("huya_ck.features.novel.player.danmaku", self.recorder).start()
        patch("huya_ck.features.novel.handler.danmaku", self.recorder).start()
        patch("huya_ck.platform.config_store.feature_config", _fake_feature_config).start()
        config_store.put_interaction({"enabled": True})
        self.meta = self.library.upload("测试小说", TEXT.encode("utf-8"))
        config_store.put_novel(
            {"enabled": True, "novel_id": self.meta["id"], "max_chars": 7, "interval_ms": 3000}
        )
        self.player = NovelPlayer()
        patch("huya_ck.features.novel.handler.novel_player", self.player).start()
        config_store.put_chat_control(
            {
                "owner_uid": "1",
                "owner_nick": "本人",
                "whitelist": [
                    {
                        "uid": "2",
                        "nick": "小说助手",
                        "enabled": True,
                        "allowed_interactions": ["novel"],
                    },
                    {
                        "uid": "3",
                        "nick": "无互动权限",
                        "enabled": True,
                        "allowed_interactions": [],
                    },
                    {
                        "uid": "4",
                        "nick": "旧配置迁移",
                        "enabled": True,
                        "allow_interaction": True,
                    },
                ],
            }
        )

    def tearDown(self) -> None:
        patch.stopall()

    def _execute(self, content, uid=1):
        return novel_handler.execute({"uid": uid, "nick": "某人", "content": content}, None)

    def test_parser_is_strict(self) -> None:
        self.assertEqual(novel_handler.parse_command("lu轮播开始")["action"], "开始")
        self.assertEqual(novel_handler.parse_command(" LU 轮播 状态！")["action"], "状态")
        # 旧关键词「小说」保持兼容
        self.assertEqual(novel_handler.parse_command("LU小说下一条")["action"], "下一条")
        self.assertIsNone(novel_handler.parse_command("大家LU小说开始吧"))
        self.assertIsNone(novel_handler.parse_command("LU 轮播 快进"))

    def test_owner_starts_and_pauses(self) -> None:
        result = self._execute("LU 轮播 开始")
        self.assertTrue(result["ok"])
        self.assertEqual(config_store.novel_config()["state"], "playing")
        result = self._execute("LU 轮播 暂停")
        self.assertTrue(result["ok"])
        self.assertEqual(config_store.novel_config()["state"], "paused")

    def test_whitelist_with_novel_permission_can_execute(self) -> None:
        result = self._execute("LU 轮播 开始", uid=2)
        self.assertTrue(result["ok"])
        self.assertEqual(config_store.novel_config()["state"], "playing")

    def test_unauthorized_users_are_rejected(self) -> None:
        for uid in (3, 4, 999):
            result = self._execute("LU 轮播 开始", uid=uid)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "unauthorized")
        # 旧字段 allow_interaction=true 不自动授予小说权限
        self.assertEqual(config_store.novel_config()["state"], "paused")

    def test_status_sends_high_priority_feedback(self) -> None:
        self._execute("LU 轮播 开始")
        self.recorder.submitted.clear()
        result = self._execute("LU 轮播 状态")
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.recorder.submitted), 1)
        self.assertEqual(self.recorder.submitted[0]["priority"], "high")
        self.assertIn("测试小说", self.recorder.submitted[0]["text"])

    def test_command_rejected_when_module_disabled(self) -> None:
        config_store.put_novel({"enabled": False})
        result = self._execute("LU 轮播 开始")
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"])

    def test_command_rejected_when_interaction_disabled(self) -> None:
        config_store.put_interaction({"enabled": False})
        result = self._execute("LU 轮播 开始")
        self.assertFalse(result["ok"])
        self.assertTrue(result["reason"])


if __name__ == "__main__":
    unittest.main()
