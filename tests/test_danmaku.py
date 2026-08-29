import unittest
from unittest import mock

from huya_ck.features.danmaku import handler as danmaku_handler


def cfg(enabled=True, interval_ms=0, queue_max=5):
    return {"enabled": enabled, "interval_ms": interval_ms, "queue_max": queue_max}


class FakeLocator:
    def __init__(self, visible: bool) -> None:
        self._visible = visible

    @property
    def first(self) -> "FakeLocator":
        return self

    def is_visible(self, timeout: int = 0) -> bool:
        return self._visible


class FakePage:
    def __init__(self, visible: bool = True) -> None:
        self._visible = visible
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._visible)

    def fill(self, selector: str, text: str, timeout: int = 0) -> None:
        self.filled.append((selector, text))

    def click(self, selector: str, timeout: int = 0) -> None:
        self.clicked.append(selector)


class DanmakuTest(unittest.TestCase):
    def setUp(self) -> None:
        self.danmaku = danmaku_handler.Danmaku()
        patcher = mock.patch.object(
            danmaku_handler.config_store, "feature_config", return_value=cfg()
        )
        self.mock_cfg = patcher.start()
        self.addCleanup(patcher.stop)

    def test_sends_when_due(self) -> None:
        page = FakePage()
        self.danmaku.submit("欢迎甲", source="welcome", event_id="a", reason="贵族进场")
        self.danmaku.pump(page)
        self.assertEqual(page.filled, [("#pub_msg_input", "欢迎甲")])
        self.assertEqual(page.clicked, ["#msg_send_bt"])

    def test_disabled_drops(self) -> None:
        self.mock_cfg.return_value = cfg(enabled=False)
        page = FakePage()
        self.danmaku.submit("欢迎甲", source="welcome", event_id="a", reason="r")
        self.danmaku.pump(page)
        self.assertEqual(page.filled, [])

    def test_empty_text_ignored(self) -> None:
        page = FakePage()
        self.danmaku.submit("   ", source="welcome", event_id="a", reason="r")
        self.danmaku.pump(page)
        self.assertEqual(page.filled, [])

    def test_interval_blocks_second(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        page = FakePage()
        self.danmaku.submit("一条", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("二条", source="welcome", event_id="b", reason="r")
        self.danmaku.pump(page)
        self.assertEqual(len(page.filled), 1)
        self.danmaku.pump(page)
        self.assertEqual(len(page.filled), 1)

    def test_queue_max_drops_oldest(self) -> None:
        self.mock_cfg.return_value = cfg(queue_max=1)
        page = FakePage()
        self.danmaku.submit("旧", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("新", source="welcome", event_id="b", reason="r")
        self.danmaku.pump(page)
        self.assertEqual(page.filled, [("#pub_msg_input", "新")])

    def test_failure_not_retried_and_does_not_start_cooldown(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        bad_page = FakePage(visible=False)
        self.danmaku.submit("第一条", source="welcome", event_id="a", reason="r")
        self.danmaku.pump(bad_page)
        self.assertEqual(bad_page.filled, [])
        good_page = FakePage()
        self.danmaku.submit("第二条", source="welcome", event_id="b", reason="r")
        self.danmaku.pump(good_page)
        self.assertEqual(good_page.filled, [("#pub_msg_input", "第二条")])

    def test_cooldown_starts_after_success(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        page = FakePage()
        self.danmaku.submit("第一条", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("第二条", source="welcome", event_id="b", reason="r")

        with mock.patch.object(
            danmaku_handler.time,
            "monotonic",
            side_effect=[100.0, 102.9, 103.0, 103.0],
        ):
            self.danmaku.pump(page)
            self.danmaku.pump(page)
            self.assertEqual(page.filled, [("#pub_msg_input", "第一条")])
            self.danmaku.pump(page)

        self.assertEqual(
            page.filled,
            [("#pub_msg_input", "第一条"), ("#pub_msg_input", "第二条")],
        )

    def test_clear_empties_queue(self) -> None:
        page = FakePage()
        self.danmaku.submit("待发", source="welcome", event_id="a", reason="r")
        self.danmaku.clear()
        self.danmaku.pump(page)
        self.assertEqual(page.filled, [])


if __name__ == "__main__":
    unittest.main()
