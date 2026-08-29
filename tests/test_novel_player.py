import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from huya_ck.features.danmaku.handler import Danmaku
from huya_ck.features.novel.library import NovelLibrary
from huya_ck.features.novel.player import NovelPlayer, downgrade_on_restart
from huya_ck.platform import config_store

TEXT = "。".join(f"这是第{i}段的正文内容，稍微长一点" for i in range(6)) + "。"


class _Recorder:
    """替身弹幕队列：记录 submit 并允许手动触发发送结果。"""

    def __init__(self, enabled=True) -> None:
        self.enabled = enabled
        self.submitted = []

    def submit(self, text, *, source, event_id, reason, priority="normal", on_result=None):
        self.submitted.append(
            {"text": text, "source": source, "event_id": event_id, "reason": reason, "priority": priority, "on_result": on_result}
        )


def _fake_feature_config(feature_id, doc=None):
    if feature_id == "danmaku":
        return {"enabled": True, "interval_ms": 0, "queue_max": 20}
    return {}


class NovelPlayerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path_patch = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp / "app.json")
        self.path_patch.start()
        self.library = NovelLibrary(self.tmp / "novels")
        self.library_patch = patch(
            "huya_ck.features.novel.player.library_module.library", self.library
        )
        self.library_patch.start()
        self.recorder = _Recorder()
        self.danmaku_patch = patch(
            "huya_ck.features.novel.player.danmaku", self.recorder
        )
        self.danmaku_patch.start()
        self.feature_patch = patch(
            "huya_ck.platform.config_store.feature_config", _fake_feature_config
        )
        self.feature_patch.start()
        config_store.put_interaction({"enabled": True})
        self.meta = self.library.upload("测试小说", TEXT.encode("utf-8"))
        config_store.put_novel({"enabled": True, "novel_id": self.meta["id"], "interval_ms": 3000, "max_chars": 15})
        self.player = NovelPlayer()

    def tearDown(self) -> None:
        self.feature_patch.stop()
        self.danmaku_patch.stop()
        self.library_patch.stop()
        self.path_patch.stop()

    def _start(self) -> None:
        result = self.player.start()
        self.assertTrue(result["ok"])

    def test_success_advances_progress(self) -> None:
        self._start()
        self.player.tick()
        self.assertEqual(len(self.recorder.submitted), 1)
        item = self.recorder.submitted[0]
        self.assertEqual(item["priority"], "low")
        self.assertLessEqual(len(item["text"]), 15)
        self.recorder.submitted[0]["on_result"](True)
        cfg = config_store.novel_config()
        self.assertEqual(cfg["next_index"], 1)
        self.assertEqual(cfg["state"], "playing")

    def test_failure_drops_segment_and_advances(self) -> None:
        self._start()
        self.player.tick()
        first = self.recorder.submitted[0]["text"]
        self.recorder.submitted[0]["on_result"](False)
        cfg = config_store.novel_config()
        # 失败不重试、不暂停：丢弃本段，顺序推进
        self.assertEqual(cfg["state"], "playing")
        self.assertEqual(cfg["next_index"], 1)
        self.player._last_result_at = None
        self.player.tick()
        self.assertEqual(len(self.recorder.submitted), 2)
        self.assertNotEqual(self.recorder.submitted[1]["text"], first)

    def test_single_segment_in_flight(self) -> None:
        self._start()
        self.player.tick()
        self.player.tick()
        self.player.tick()
        self.assertEqual(len(self.recorder.submitted), 1)
        self.recorder.submitted[0]["on_result"](True)
        # 成功后要等自身间隔才发下一段
        self.player.tick()
        self.assertEqual(len(self.recorder.submitted), 1)

    def test_last_segment_completes(self) -> None:
        self._start()
        config_store.put_novel({"loop": False})
        total = len(self.player._load_segments(config_store.novel_config()))
        for _ in range(total):
            self.player.tick()
            self.recorder.submitted[-1]["on_result"](True)
            # 抹掉间隔等待
            self.player._last_result_at = None
        cfg = config_store.novel_config()
        self.assertEqual(cfg["state"], "completed")
        self.assertEqual(cfg["next_index"], total)

    def test_loop_rewinds_after_last_segment(self) -> None:
        """循环模式：播完最后一段回卷到第一段继续。"""
        self._start()
        config_store.put_novel({"loop": True})
        total = len(self.player._load_segments(config_store.novel_config()))
        for _ in range(total):
            self.player.tick()
            self.recorder.submitted[-1]["on_result"](True)
            self.player._last_result_at = None
        cfg = config_store.novel_config()
        self.assertEqual(cfg["state"], "playing")
        self.assertEqual(cfg["next_index"], 0)
        # 下一轮从第一段重新开始
        self.player.tick()
        self.assertEqual(self.recorder.submitted[-1]["text"], self.recorder.submitted[0]["text"])

    def test_tick_ignores_global_send_switch(self) -> None:
        """分层：播放器不读 danmaku 配置。全局关发送由队列拒绝入队、失败回调触发丢弃推进。"""
        self._start()
        self.feature_patch.stop()
        disabled_patch = patch(
            "huya_ck.platform.config_store.feature_config",
            lambda feature_id, doc=None: {"enabled": False, "interval_ms": 0, "queue_max": 20},
        )
        disabled_patch.start()
        try:
            self.player.tick()  # 不应因发送关闭而暂停
        finally:
            disabled_patch.stop()
        self.assertEqual(config_store.novel_config()["state"], "playing")
        # 发送失败的结果：丢弃本段并继续
        self.player.tick()
        self.recorder.submitted[-1]["on_result"](False)
        self.assertEqual(config_store.novel_config()["state"], "playing")

    def test_tick_pauses_when_interaction_disabled(self) -> None:
        self._start()
        config_store.put_interaction({"enabled": False})
        self.player.tick()
        self.assertEqual(config_store.novel_config()["state"], "paused")

    def test_restart_downgrades_playing_to_paused(self) -> None:
        self._start()
        self.assertEqual(config_store.novel_config()["state"], "playing")
        downgrade_on_restart()
        cfg = config_store.novel_config()
        self.assertEqual(cfg["state"], "paused")
        self.assertEqual(cfg["next_index"], 0)

    def test_restart_while_result_pending_does_not_rewind(self) -> None:
        """点「开始」重播时，旧播放的迟到发送结果不能再把进度拉回去。"""
        self._start()
        self.player.tick()
        self.recorder.submitted[0]["on_result"](True)
        self.assertEqual(config_store.novel_config()["next_index"], 1)
        # 新一段在途时再次点「开始」：旧结果迟到到达
        self.player.tick()
        stale = self.recorder.submitted[-1]
        self._start()
        self.assertEqual(config_store.novel_config()["next_index"], 0)
        stale["on_result"](True)
        self.assertEqual(config_store.novel_config()["next_index"], 0)

    def test_stop_resets_progress(self) -> None:
        self._start()
        self.player.tick()
        self.recorder.submitted[0]["on_result"](True)
        result = self.player.stop()
        self.assertTrue(result["ok"])
        cfg = config_store.novel_config()
        self.assertEqual(cfg["state"], "idle")
        self.assertEqual(cfg["next_index"], 0)

    def test_changing_max_chars_resets_progress(self) -> None:
        """段序号只对同一拆分配置有意义：改字数 = 进度归零。"""
        self._start()
        self.player.tick()
        self.recorder.submitted[0]["on_result"](True)
        self.assertEqual(config_store.novel_config()["next_index"], 1)
        config_store.put_novel({"max_chars": 10})
        cfg = config_store.novel_config()
        self.assertEqual(cfg["next_index"], 0)


class DanmakuLimitTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.path_patch = patch("huya_ck.platform.config_store.CONFIG_PATH", self.tmp / "app.json")
        self.path_patch.start()
        config_store.set_features_enabled(["danmaku"], True)
        config_store.put_feature("danmaku", {"interval_ms": 0})

    def tearDown(self) -> None:
        self.path_patch.stop()

    def test_overlong_text_is_rejected(self) -> None:
        queue = Danmaku()
        results = []
        queue.submit("一" * 29, source="t", event_id="1", reason="r", on_result=lambda ok: results.append(ok))
        queue.submit("一" * 28, source="t", event_id="2", reason="r")
        # 超长的被拒（回调失败），28 字正常入队
        self.assertEqual(results, [False])
        self.assertEqual(queue.snapshot()["queue_size"], 1)

    def test_priority_pops_first_and_keeps_fifo(self) -> None:
        queue = Danmaku()
        queue.submit("低1", source="t", event_id="1", reason="r", priority="low")
        queue.submit("普1", source="t", event_id="2", reason="r")
        queue.submit("高1", source="t", event_id="3", reason="r", priority="high")
        queue.submit("高2", source="t", event_id="4", reason="r", priority="high")
        self.assertEqual(queue._pop_due()["text"], "高1")
        self.assertEqual(queue._pop_due()["text"], "高2")
        self.assertEqual(queue._pop_due()["text"], "普1")
        self.assertEqual(queue._pop_due()["text"], "低1")

    def test_pump_notifies_result_callback(self) -> None:
        queue = Danmaku()
        results = []
        queue.submit("失败条", source="t", event_id="1", reason="r", on_result=lambda ok: results.append(ok))
        with patch("huya_ck.features.danmaku.handler._type_into_page", return_value=False):
            queue.pump(object())
        self.assertEqual(results, [False])
        self.assertEqual(queue.snapshot()["queue_size"], 0)

    def test_clear_notifies_dropped_items(self) -> None:
        queue = Danmaku()
        results = []
        queue.submit("在途", source="t", event_id="1", reason="r", on_result=lambda ok: results.append(ok))
        queue.clear()
        self.assertEqual(results, [False])


if __name__ == "__main__":
    unittest.main()
