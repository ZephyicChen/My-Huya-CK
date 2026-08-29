"""Prepare a project-local Python env and Chromium.

Idempotent: only installs what is missing, unless --force is passed.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
REQ = ROOT / "requirements.txt"
BROWSERS = ROOT / ".playwright-browsers"
PIP_INDEX = os.environ.get("HUYA_CK_PIP_INDEX", "https://pypi.tuna.tsinghua.edu.cn/simple")
PLAYWRIGHT_MIRROR = os.environ.get("PLAYWRIGHT_DOWNLOAD_HOST", "https://npmmirror.com/mirrors/playwright")
MIN_VERSION = (3, 10)


def log(msg: str) -> None:
    print(f"[env] {msg}")


def run(cmd: list[str], env: dict[str, str] | None = None) -> None:
    subprocess.check_call(cmd, cwd=str(ROOT), env=env)


def check_version(executable: str | Path, label: str) -> None:
    code = "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
    result = subprocess.run([str(executable), "-c", code])
    if result.returncode != 0:
        raise SystemExit(f"{label} 不是 Python 3.10+，请安装 3.10 或更高版本后再运行 run.bat")


def playwright_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
    env["PLAYWRIGHT_DOWNLOAD_HOST"] = PLAYWRIGHT_MIRROR
    return env


def playwright_ok(py: Path) -> bool:
    if not package_ok(py) or not BROWSERS.exists():
        return False
    for exe in BROWSERS.glob("chromium-*/chrome-win64/chrome.exe"):
        if exe.is_file():
            return True
    for exe in BROWSERS.glob("chromium-*/chrome-win/chrome.exe"):
        if exe.is_file():
            return True
    return False


def package_ok(py: Path) -> bool:
    result = subprocess.run(
        [str(py), "-c", "import playwright, fastapi, uvicorn"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return result.returncode == 0


def ensure_venv() -> Path:
    if VENV_PY.exists():
        check_version(VENV_PY, "项目虚拟环境")
        return VENV_PY
    log("创建项目虚拟环境 .venv")
    check_version(sys.executable, "当前 Python")
    run([sys.executable, "-m", "venv", str(ROOT / ".venv")])
    if not VENV_PY.exists():
        raise SystemExit("虚拟环境创建失败：找不到 .venv\\Scripts\\python.exe")
    return VENV_PY


def ensure_packages(py: Path, force: bool) -> None:
    if not force and package_ok(py):
        return
    if not REQ.exists():
        raise SystemExit(f"缺少 {REQ.name}")
    log("安装 Python 依赖到 .venv")
    run([str(py), "-m", "pip", "install", "-U", "pip", "-i", PIP_INDEX])
    run([str(py), "-m", "pip", "install", "-r", str(REQ), "-i", PIP_INDEX])
    if not package_ok(py):
        raise SystemExit("依赖安装后仍无法 import playwright / fastapi / uvicorn")


def ensure_chromium(py: Path, force: bool) -> None:
    if not force and playwright_ok(py):
        return
    BROWSERS.mkdir(parents=True, exist_ok=True)
    log("下载 Chromium 到 .playwright-browsers")
    run([str(py), "-m", "playwright", "install", "chromium"], env=playwright_env())
    if not playwright_ok(py):
        raise SystemExit("Chromium 安装后仍不可用")


def main() -> int:
    parser = argparse.ArgumentParser(description="准备本项目本地运行环境")
    parser.add_argument("--force", action="store_true", help="重新安装依赖和 Chromium")
    args = parser.parse_args()

    if sys.version_info < MIN_VERSION:
        log(f"需要 Python 3.10+，当前是 {sys.version.split()[0]}")
        return 1

    py = ensure_venv()
    ensure_packages(py, args.force)
    ensure_chromium(py, args.force)
    log("项目环境就绪（.venv + 本地 Chromium）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as exc:
        log(f"命令失败: {' '.join(exc.cmd)}")
        raise SystemExit(1)
