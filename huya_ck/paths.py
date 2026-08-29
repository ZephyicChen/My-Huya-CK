from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
CONFIG_PATH = ROOT / "config" / "app.json"
WEB_DIR = ROOT / "web"
PROFILE_DIR = ROOT / "playwright-profile"
BROWSERS_DIR = ROOT / ".playwright-browsers"
NOVEL_DATA_DIR = ROOT / "data" / "novels"
