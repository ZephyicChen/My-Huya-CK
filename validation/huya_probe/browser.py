"""Browser session and login.

Playwright starts a visible Chromium with a persistent profile. First
login, captcha and security checks are done by the user.
"""

from playwright.sync_api import BrowserContext, Page, sync_playwright

HUYA_HOME = "https://www.huya.com"

LOGIN_HINT_SELECTORS = [".nav-user", "img#yy-avater", ".user-avatar", ".nav-avatar"]
LOGOUT_HINT_SELECTORS = [".nav-login", ".nav-login-href"]


def launch_persistent_browser(profile_dir: str):
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        profile_dir,
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )
    return pw, context


def check_login_status(context: BrowserContext, page: Page):
    """Return (status, detail): True logged in / False logged out / None unknown."""
    try:
        page.goto(HUYA_HOME, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
    except Exception as exc:
        return None, f"打开虎牙首页失败: {exc}"

    for selector in LOGIN_HINT_SELECTORS:
        try:
            if page.locator(selector).first.is_visible():
                return True, f"检测到已登录标识元素 {selector}"
        except Exception:
            continue

    for selector in LOGOUT_HINT_SELECTORS:
        try:
            if page.locator(selector).first.is_visible():
                return False, f"检测到未登录标识元素 {selector}"
        except Exception:
            continue

    return None, "无法自动判断登录状态，请在浏览器窗口中人工确认"


def get_or_new_page(context: BrowserContext) -> Page:
    return context.pages[0] if context.pages else context.new_page()


def open_room(context: BrowserContext, room_url: str, config: dict) -> Page:
    page = get_or_new_page(context)
    print(f"[browser] 打开直播间: {room_url}")
    page.goto(room_url, wait_until="domcontentloaded", timeout=60000)
    wait_seconds = config.get("page_stabilize_wait_seconds", 10)
    print(f"[browser] 等待页面稳定 {wait_seconds} 秒...")
    page.wait_for_timeout(wait_seconds * 1000)
    return page


def run_login_mode(args) -> None:
    pw, context = launch_persistent_browser(args.profile_dir)
    page = get_or_new_page(context)
    try:
        page.goto(HUYA_HOME, wait_until="domcontentloaded", timeout=30000)
        print()
        print("=" * 50)
        print("请在打开的浏览器窗口中手工完成登录。")
        print("验证码、安全验证等均由您手工处理，程序不会干预。")
        print("=" * 50)
        input("完成登录后，回到此终端按回车键继续...")

        status, detail = check_login_status(context, page)
        if status is True:
            print(f"[login] 登录状态有效（{detail}），Profile 已保存到 {args.profile_dir}")
        elif status is False:
            print(f"[login] 登录状态无效（{detail}），请重新运行登录模式")
        else:
            print(f"[login] {detail}")
            print("[login] 请在浏览器窗口中人工确认是否已登录")
    finally:
        context.close()
        pw.stop()
        print("[login] 浏览器已关闭，Profile 保存完成")
