"""Test danmaku send. Requires explicit user confirmation. Not driven by events."""

from pathlib import Path

from playwright.sync_api import Page

from .browser import check_login_status, get_or_new_page, launch_persistent_browser, open_room
from .config import is_placeholder, load_config
from .event_logger import now_iso

TEST_MESSAGE = "探针测试弹幕"

INPUT_FALLBACK_SELECTORS = ["#pub_msg_input", "input[name='msg']", "textarea.chat-input"]
SEND_FALLBACK_SELECTORS = ["#msg_send_bt", "a.chat-send", "button.chat-send"]


def _find_visible(page: Page, selectors: list) -> str | None:
    for selector in selectors:
        try:
            if page.locator(selector).first.is_visible():
                return selector
        except Exception:
            continue
    return None


def _save_failure_artifacts(page: Page, log_dir: str, reason: str) -> None:
    """保存错误信息和页面状态，供人工诊断（需求文档 4.5）。"""
    out_dir = Path(log_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = now_iso().replace(":", "").replace("+", "_")
    base = out_dir / f"send-failure-{stamp}"
    try:
        page.screenshot(path=str(base) + ".png", full_page=False)
        base_html = base.with_suffix(".html")
        base_html.write_text(page.content(), encoding="utf-8")
        print(f"[send-test] 页面状态已保存: {base}.png / {base_html.name}")
    except Exception as exc:
        print(f"[send-test] 保存页面状态失败: {exc}")
    print(f"[send-test] 失败原因: {reason}")


def confirm_with_user(prompt: str) -> bool:
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    return answer in ("y", "yes")


def send_danmaku(page: Page, text: str, config: dict, log_dir: str) -> bool:
    """通过正常输入框发送一条弹幕，成功返回 True。失败不自动重试。"""
    selectors = config.get("selectors", {})
    input_selectors = (
        [selectors["danmaku_input"]]
        if not is_placeholder(selectors.get("danmaku_input"))
        else INPUT_FALLBACK_SELECTORS
    )
    send_selectors = (
        [selectors["danmaku_send_button"]]
        if not is_placeholder(selectors.get("danmaku_send_button"))
        else SEND_FALLBACK_SELECTORS
    )

    input_selector = _find_visible(page, input_selectors)
    if not input_selector:
        _save_failure_artifacts(page, log_dir, f"未找到可见弹幕输入框，尝试过: {input_selectors}")
        return False
    send_selector = _find_visible(page, send_selectors)
    if not send_selector:
        _save_failure_artifacts(page, log_dir, f"未找到可见发送按钮，尝试过: {send_selectors}")
        return False

    page.fill(input_selector, text)
    page.click(send_selector)
    page.wait_for_timeout(3000)

    # 验证消息是否出现在聊天区
    try:
        appears = page.locator(f"text={text}").first.is_visible()
    except Exception:
        appears = False
    if not appears:
        _save_failure_artifacts(
            page, log_dir, "已点击发送，但页面未显示该消息（可能被吞或发送失败）"
        )
        return False
    return True


def run_send_test_mode(args, room_url: str) -> None:
    """发送测试模式：人工确认后发送一条测试弹幕。"""
    config = load_config()
    pw, context = launch_persistent_browser(args.profile_dir)
    try:
        page = get_or_new_page(context)
        status, detail = check_login_status(context, page)
        if status is not True:
            print(f"[send-test] 登录状态未确认（{detail}），停止发送操作")
            return

        page = open_room(context, room_url, config)
        print(f"[send-test] 测试消息内容: 「{TEST_MESSAGE}」")
        if not confirm_with_user("确认发送这条测试弹幕？"):
            print("[send-test] 用户取消，未发送")
            return

        if send_danmaku(page, TEST_MESSAGE, config, args.log_dir):
            print("[send-test] 发送成功，页面已显示该消息")
        else:
            print("[send-test] 发送失败，已保存诊断信息，不自动重试")
    finally:
        context.close()
        pw.stop()
