"""读写 config/app.json。平台项与各模块配置分开存。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from huya_ck.features.registry import defaults as feature_defaults
from huya_ck.log import get_logger
from huya_ck.paths import CONFIG_PATH

log = get_logger()

PLATFORM_DEFAULT = {"room": "", "show_browser": False}


def _deep_merge(base: dict, overlay: dict) -> dict:
    out = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = deepcopy(value)
    return out


def empty_document() -> dict:
    doc = dict(PLATFORM_DEFAULT)
    doc.update(deepcopy(feature_defaults()))
    return doc


def load(path: Path | None = None) -> dict:
    target = path or CONFIG_PATH
    if not target.exists():
        return empty_document()
    with target.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        return empty_document()
    return _deep_merge(empty_document(), raw)


def save(doc: dict, path: Path | None = None) -> dict:
    target = path or CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    merged = _deep_merge(empty_document(), doc)
    tmp = target.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(merged, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(target)
    log.debug("已保存配置 %s 房间=%s", target.name, merged.get("room") or "(空)")
    return merged


def platform_config(doc: dict | None = None) -> dict:
    data = doc if doc is not None else load()
    return {
        "room": str(data.get("room") or ""),
        "show_browser": bool(data.get("show_browser")),
    }


def put_platform(patch: dict, path: Path | None = None) -> dict:
    doc = load(path)
    if "room" in patch:
        doc["room"] = str(patch["room"] or "")
    if "show_browser" in patch:
        doc["show_browser"] = bool(patch["show_browser"])
    return save(doc, path)


def feature_config(feature_id: str, doc: dict | None = None) -> dict:
    data = doc if doc is not None else load()
    defaults = feature_defaults().get(feature_id, {})
    current = data.get(feature_id)
    if not isinstance(current, dict):
        return deepcopy(defaults)
    return _deep_merge(defaults, current)


def put_feature(feature_id: str, patch: dict, path: Path | None = None) -> dict:
    if feature_id not in feature_defaults():
        raise KeyError(feature_id)
    doc = load(path)
    current = feature_config(feature_id, doc)
    doc[feature_id] = _deep_merge(current, patch)
    saved = save(doc, path)
    return feature_config(feature_id, saved)
