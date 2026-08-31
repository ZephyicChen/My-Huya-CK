import asyncio
import unittest

from huya_ck.platform.session import current_page


class _Page:
    def __init__(self, closed: bool = False) -> None:
        self.closed = closed

    def is_closed(self) -> bool:
        return self.closed


class _Context:
    def __init__(self, pages) -> None:
        self.pages = pages
        self.created = None

    async def new_page(self):
        self.created = _Page()
        return self.created


class SessionTest(unittest.TestCase):
    def test_uses_latest_open_page_after_login_switch(self) -> None:
        old = _Page(closed=True)
        middle = _Page()
        latest = _Page()
        context = _Context([old, middle, latest])
        self.assertIs(asyncio.run(current_page(context)), latest)

    def test_creates_page_when_all_are_closed(self) -> None:
        context = _Context([_Page(closed=True)])
        self.assertIs(asyncio.run(current_page(context)), context.created)


if __name__ == "__main__":
    unittest.main()
