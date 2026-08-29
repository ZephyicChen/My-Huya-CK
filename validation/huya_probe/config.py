"""Load the probe config. Selectors are only used by send-test."""

import json
from pathlib import Path

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "probe_config.json"


def load_config(path: str | None = None) -> dict:
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    with open(config_path, encoding="utf-8") as f:
        return json.load(f)


def is_placeholder(selector: str | None) -> bool:
    return not selector or selector.startswith("TODO")
