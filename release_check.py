"""发布前的只读仓库检查，由 release-check.bat 调用。"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config" / "app.example.json"
WEB_INDEX = ROOT / "web" / "index.html"
WEB_ASSETS = ROOT / "web" / "assets"
SENSITIVE_PREFIXES = (
    "config/app.json",
    "data/",
    "logs/",
    "playwright-profile/",
    "validation/event-captures/",
    "validation/ws-dumps/",
    "validation/decode-dumps/",
    ".venv/",
    ".playwright-browsers/",
)


def web_asset_errors() -> list[str]:
    """确认提交的 WebUI 入口只引用存在的当前构建产物。"""
    try:
        html = WEB_INDEX.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"无法读取 web/index.html：{exc}"]

    references = set(re.findall(r'/assets/(index-[^"\']+\.(?:js|css))', html))
    suffixes = {Path(name).suffix for name in references}
    errors = []
    if suffixes != {".js", ".css"}:
        errors.append("web/index.html 必须各引用一个 index-*.js 和 index-*.css")
    for name in sorted(references):
        if not (WEB_ASSETS / name).is_file():
            errors.append(f"WebUI 构建产物不存在：web/assets/{name}")

    actual = {path.name for path in WEB_ASSETS.glob("index-*.*") if path.is_file()}
    for name in sorted(actual - references):
        errors.append(f"WebUI 存在未被入口引用的旧产物：web/assets/{name}")
    return errors


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )


def main() -> int:
    errors: list[str] = []

    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"无法读取公开示例配置：{exc}")
        config = {}

    if config.get("room"):
        errors.append("config/app.example.json 的 room 必须为空")
    chat_control = config.get("chat_control")
    if not isinstance(chat_control, dict):
        errors.append("config/app.example.json 必须包含空的 chat_control")
    elif chat_control.get("owner_uid") or chat_control.get("owner_nick") or chat_control.get("whitelist"):
        errors.append("config/app.example.json 的当前账号和白名单必须为空")
    for feature_id in ("welcome", "gift_thank", "superfan_thank", "noble_thank", "guard_thank", "danmaku"):
        feature = config.get(feature_id)
        if not isinstance(feature, dict) or feature.get("enabled") is not False:
            errors.append(f"config/app.example.json 的 {feature_id}.enabled 必须为 false")
    interaction = config.get("interaction")
    if not isinstance(interaction, dict) or interaction.get("enabled") is not False:
        errors.append("config/app.example.json 必须包含 interaction.enabled=false")
    novel = config.get("novel")
    if not isinstance(novel, dict) or novel.get("enabled") is not False or novel.get("novel_id"):
        errors.append("config/app.example.json 必须包含未启用且未选择小说的 novel 段")
    if config.get("nick_overrides") != []:
        errors.append("config/app.example.json 必须包含空的 nick_overrides")

    tracked = git("ls-files")
    if tracked.returncode != 0:
        errors.append(f"git ls-files 失败：{tracked.stderr.strip()}")
    else:
        for path in tracked.stdout.splitlines():
            normalized = path.replace("\\", "/")
            if normalized.startswith(SENSITIVE_PREFIXES):
                errors.append(f"敏感或本地目录被 Git 跟踪：{path}")

    for diff_args in (("diff", "--check"), ("diff", "--cached", "--check")):
        whitespace = git(*diff_args)
        if whitespace.returncode != 0:
            errors.append(whitespace.stdout.strip() or whitespace.stderr.strip() or f"git {' '.join(diff_args)} 失败")

    errors.extend(web_asset_errors())

    if errors:
        print("[release] 发布检查失败：")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("[release] 默认配置、WebUI 构建产物与 Git 敏感目录检查通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
