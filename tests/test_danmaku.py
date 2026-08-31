import asyncio
import unittest
from unittest import mock

from huya_ck.features.danmaku import handler as danmaku_handler


def run(coro):
    return asyncio.run(coro)


def cfg(enabled=True, interval_ms=0, queue_max=5):
    return {"enabled": enabled, "interval_ms": interval_ms, "queue_max": queue_max}


class FakeLocator:
    def __init__(self, visible: bool) -> None:
        self._visible = visible

    @property
    def first(self) -> "FakeLocator":
        return self

    async def is_visible(self, timeout: int = 0) -> bool:
        return self._visible


class FakePage:
    def __init__(self, visible: bool = True) -> None:
        self._visible = visible
        self.filled: list[tuple[str, str]] = []
        self.clicked: list[str] = []

    def locator(self, selector: str) -> FakeLocator:
        return FakeLocator(self._visible)

    async def fill(self, selector: str, text: str, timeout: int = 0) -> None:
        self.filled.append((selector, text))

    async def click(self, selector: str, timeout: int = 0) -> None:
        self.clicked.append(selector)


class DanmakuTest(unittest.TestCase):
    def setUp(self) -> None:
        self.danmaku = danmaku_handler.Danmaku()
        patcher = mock.patch.object(
            danmaku_handler.config_store, "feature_config", return_value=cfg()
        )
        self.mock_cfg = patcher.start()
        self.addCleanup(patcher.stop)

    def pump(self, page) -> None:
        run(self.danmaku.pump(page))

    def test_sends_when_due(self) -> None:
        page = FakePage()
        self.danmaku.submit("欢迎甲", source="welcome", event_id="a", reason="贵族进场")
        self.pump(page)
        self.assertEqual(page.filled, [("#pub_msg_input", "欢迎甲")])
        self.assertEqual(page.clicked, ["#msg_send_bt"])

    def test_disabled_drops(self) -> None:
        self.mock_cfg.return_value = cfg(enabled=False)
        page = FakePage()
        self.danmaku.submit("欢迎甲", source="welcome", event_id="a", reason="r")
        self.pump(page)
        self.assertEqual(page.filled, [])

    def test_empty_text_ignored(self) -> None:
        page = FakePage()
        self.danmaku.submit("   ", source="welcome", event_id="a", reason="r")
        self.pump(page)
        self.assertEqual(page.filled, [])

    def test_interval_blocks_second(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        page = FakePage()
        self.danmaku.submit("一条", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("二条", source="welcome", event_id="b", reason="r")
        self.pump(page)
        self.assertEqual(len(page.filled), 1)
        self.pump(page)
        self.assertEqual(len(page.filled), 1)

    def test_queue_max_drops_oldest(self) -> None:
        self.mock_cfg.return_value = cfg(queue_max=1)
        page = FakePage()
        self.danmaku.submit("旧", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("新", source="welcome", event_id="b", reason="r")
        self.pump(page)
        self.assertEqual(page.filled, [("#pub_msg_input", "新")])

    def test_failure_not_retried_and_does_not_start_cooldown(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        bad_page = FakePage(visible=False)
        self.danmaku.submit("第一条", source="welcome", event_id="a", reason="r")
        self.pump(bad_page)
        self.assertEqual(bad_page.filled, [])
        good_page = FakePage()
        self.danmaku.submit("第二条", source="welcome", event_id="b", reason="r")
        self.pump(good_page)
        self.assertEqual(good_page.filled, [("#pub_msg_input", "第二条")])

    def test_cooldown_starts_after_success(self) -> None:
        self.mock_cfg.return_value = cfg(interval_ms=3000)
        page = FakePage()
        self.danmaku.submit("第一条", source="welcome", event_id="a", reason="r")
        self.danmaku.submit("第二条", source="welcome", event_id="b", reason="r")

        # 只替换 handler 命名空间里的 time 绑定；patch 真模块会连 asyncio 的时钟一起改
        clock = mock.Mock()
        clock.monotonic = mock.Mock(side_effect=[100.0, 102.9, 103.0, 103.0, 103.0])
        with mock.patch.object(danmaku_handler, "time", clock):
            self.pump(page)
            self.pump(page)
            self.assertEqual(page.filled, [("#pub_msg_input", "第一条")])
            self.pump(page)

        self.assertEqual(
            page.filled,
            [("#pub_msg_input", "第一条"), ("#pub_msg_input", "第二条")],
        )

    def test_clear_empties_queue(self) -> None:
        page = FakePage()
        self.danmaku.submit("待发", source="welcome", event_id="a", reason="r")
        self.danmaku.clear()
        self.pump(page)
        self.assertEqual(page.filled, [])

    def test_wait_work_returns_when_idle(self) -> None:
        # 队列空时等待最多 0.05 秒即返回，不抛异常
        run(self.danmaku.wait_work(0.05))

    def test_wait_work_wakes_on_submit(self) -> None:
        async def scenario() -> None:
            async def submit_later() -> None:
                await asyncio.sleep(0.01)
                self.danmaku.submit("唤醒", source="t", event_id="1", reason="r")

            task = asyncio.create_task(submit_later())
            await asyncio.wait_for(self.danmaku.wait_work(5), timeout=1)
            await task
            self.assertTrue(self.danmaku.has_queued())

        run(scenario())


if __name__ == "__main__":
    unittest.main()
