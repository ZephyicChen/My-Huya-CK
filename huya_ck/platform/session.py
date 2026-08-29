"""Playwright 持久化会话：登录页与进房。必须在工人线程里调用。"""

from __future__ import annotations

import os

from playwright.sync_api import BrowserContext, Page, sync_playwright

from huya_ck.paths import BROWSERS_DIR, PROFILE_DIR

HUYA_HOME = "https://www.huya.com"


def ensure_browsers_env() -> None:
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS_DIR))


def room_url(room: str) -> str:
    text = (room or "").strip()
    if not text:
        raise ValueError("请填写房间号")
    if text.startswith("http://") or text.startswith("https://"):
        return text
    return f"https://www.huya.com/{text}"


def launch_persistent(*, headless: bool):
    ensure_browsers_env()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, context


def current_page(context: BrowserContext) -> Page:
    # 登录流程可能新开页面并关闭最初的 about:blank/登录页。优先使用最新仍存活的
    # 页面，避免拿到即将关闭的旧页后在 expose_function/goto 处报 TargetClosedError。
    pages = [page for page in context.pages if not page.is_closed()]
    return pages[-1] if pages else context.new_page()
