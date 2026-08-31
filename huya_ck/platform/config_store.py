"""读写 config/app.json。平台项与各模块配置分开存。"""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from huya_ck.features.novel.schema import DEFAULT as NOVEL_DEFAULT
from huya_ck.features.novel.schema import clamp_config as clamp_novel_config
from huya_ck.features.registry import defaults as feature_defaults
from huya_ck.log import get_logger
from huya_ck.paths import CONFIG_PATH

log = get_logger()

PLATFORM_DEFAULT = {"room": "", "show_browser": False}
CHAT_CONTROL_DEFAULT = {"owner_uid": "", "owner_nick": "", "whitelist": []}
NICK_OVERRIDES_DEFAULT: list = []
INTERACTION_DEFAULT = {"enabled": False}
INTERACTION_MODULE_IDS = ("novel",)
CONTROL_MODULE_IDS = (
    "danmaku",
    "welcome",
    "gift_thank",
    "guard_thank",
    "superfan_thank",
    "noble_thank",
)
_lock = threading.RLock()


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
    doc["chat_control"] = deepcopy(CHAT_CONTROL_DEFAULT)
    doc["nick_overrides"] = deepcopy(NICK_OVERRIDES_DEFAULT)
    doc["interaction"] = deepcopy(INTERACTION_DEFAULT)
    doc["novel"] = deepcopy(NOVEL_DEFAULT)
    doc.update(deepcopy(feature_defaults()))
    return doc


def load(path: Path | None = None) -> dict:
    with _lock:
        target = path or CONFIG_PATH
        if not target.exists():
            return empty_document()
        with target.open(encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return empty_document()
        return _deep_merge(empty_document(), raw)


def save(doc: dict, path: Path | None = None) -> dict:
    with _lock:
        target = path or CONFIG_PATH
        target.parent.mkdir(parents=True, exist_ok=True)
        merged = _deep_merge(empty_document(), doc)
        merged["chat_control"] = chat_control_config(merged)
        merged["nick_overrides"] = nick_overrides_config(merged)
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
    with _lock:
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
    with _lock:
        doc = load(path)
        current = feature_config(feature_id, doc)
        doc[feature_id] = _deep_merge(current, patch)
        saved = save(doc, path)
        return feature_config(feature_id, saved)


def set_features_enabled(feature_ids: list[str] | tuple[str, ...], enabled: bool, path: Path | None = None) -> dict:
    known = feature_defaults()
    unknown = [feature_id for feature_id in feature_ids if feature_id not in known]
    if unknown:
        raise KeyError(unknown[0])
    with _lock:
        doc = load(path)
        changed = {}
        for feature_id in dict.fromkeys(feature_ids):
            current = feature_config(feature_id, doc)
            current["enabled"] = bool(enabled)
            doc[feature_id] = current
            changed[feature_id] = current
        save(doc, path)
        return changed


def interaction_config(doc: dict | None = None) -> dict:
    data = doc if doc is not None else load()
    raw = data.get("interaction")
    enabled = bool(raw.get("enabled")) if isinstance(raw, dict) else False
    return {"enabled": enabled}


def put_interaction(patch: dict, path: Path | None = None) -> dict:
    with _lock:
        doc = load(path)
        current = interaction_config(doc)
        if isinstance(patch, dict):
            if "enabled" in patch:
                current["enabled"] = bool(patch["enabled"])
        doc["interaction"] = current
        saved = save(doc, path)
        return interaction_config(saved)


def novel_config(doc: dict | None = None) -> dict:
    data = doc if doc is not None else load()
    raw = data.get("novel")
    return clamp_novel_config(raw if isinstance(raw, dict) else {})


def put_novel(patch: dict, path: Path | None = None) -> dict:
    with _lock:
        doc = load(path)
        current = novel_config(doc)
        reset_progress = False
        if isinstance(patch, dict):
            for key in ("enabled", "loop"):
                if key in patch:
                    current[key] = bool(patch[key])
            if "novel_id" in patch:
                new_id = str(patch["novel_id"] or "").strip()
                if new_id != current["novel_id"]:
                    reset_progress = True
                current["novel_id"] = new_id
            if "max_chars" in patch:
                value = int(patch["max_chars"])
                if value != current["max_chars"]:
                    # 段序号只对同一拆分配置有意义：改字数后进度归零重新开始
                    reset_progress = True
                current["max_chars"] = value
            if "interval_ms" in patch:
                current["interval_ms"] = int(patch["interval_ms"])
        if reset_progress:
            current["next_index"] = 0
        doc["novel"] = current
        saved = save(doc, path)
        return novel_config(saved)


def set_novel_state(state: str, *, next_index: int | None = None, path: Path | None = None) -> dict:
    """播放器持久化进度用：只改状态和段序号，不动其它配置。"""
    with _lock:
        doc = load(path)
        current = novel_config(doc)
        current["state"] = state
        if next_index is not None:
            current["next_index"] = max(0, int(next_index))
        doc["novel"] = current
        saved = save(doc, path)
        return novel_config(saved)


def chat_control_config(doc: dict | None = None) -> dict:
    data = doc if doc is not None else load()
    raw = data.get("chat_control")
    if not isinstance(raw, dict):
        raw = {}
    owner_uid = str(raw.get("owner_uid") or "").strip()
    owner_nick = str(raw.get("owner_nick") or "").strip()[:80]
    whitelist = []
    seen: set[str] = set()
    for item in raw.get("whitelist", []):
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or "").strip()
        if not uid or uid == owner_uid or uid in seen:
            continue
        seen.add(uid)
        modules = item.get("allowed_modules", [])
        if not isinstance(modules, list):
            modules = []
        interactions = item.get("allowed_interactions", [])
        if not isinstance(interactions, list):
            interactions = []
        # 旧字段 allow_interaction 不自动迁移成任何互动权限，要求用户重新明确授权
        whitelist.append(
            {
                "uid": uid,
                "nick": str(item.get("nick") or "").strip()[:80],
                "enabled": bool(item.get("enabled", True)),
                "allowed_modules": [module for module in CONTROL_MODULE_IDS if module in modules],
                "allowed_interactions": [iid for iid in INTERACTION_MODULE_IDS if iid in interactions],
            }
        )
    return {"owner_uid": owner_uid, "owner_nick": owner_nick, "whitelist": whitelist}


def put_chat_control(config: dict, path: Path | None = None) -> dict:
    with _lock:
        doc = load(path)
        doc["chat_control"] = chat_control_config({"chat_control": config})
        saved = save(doc, path)
        return chat_control_config(saved)


def chat_authorization(uid: Any, doc: dict | None = None) -> dict | None:
    user_uid = str(uid or "").strip()
    if not user_uid:
        return None
    config = chat_control_config(doc)
    if user_uid == config["owner_uid"]:
        return {
            "role": "owner",
            "allowed_modules": list(CONTROL_MODULE_IDS),
            "allowed_interactions": list(INTERACTION_MODULE_IDS),
        }
    for item in config["whitelist"]:
        if item["uid"] == user_uid and item["enabled"]:
            return {
                "role": "whitelist",
                "allowed_modules": list(item["allowed_modules"]),
                "allowed_interactions": list(item["allowed_interactions"]),
            }
    return None


def nick_overrides_config(doc: dict | None = None) -> list[dict]:
    """昵称映射：UID -> 自定义称呼。与白名单（权限）完全独立。"""
    data = doc if doc is not None else load()
    raw = data.get("nick_overrides")
    if not isinstance(raw, list):
        return []
    overrides: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or "").strip()
        alias = str(item.get("alias") or "").strip()[:80]
        if not uid or not alias or uid in seen:
            continue
        seen.add(uid)
        overrides.append(
            {
                "uid": uid,
                "alias": alias,
                "note": str(item.get("note") or "").strip()[:80],
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return overrides


def put_nick_overrides(overrides: list, path: Path | None = None) -> list[dict]:
    with _lock:
        doc = load(path)
        doc["nick_overrides"] = nick_overrides_config({"nick_overrides": overrides})
        saved = save(doc, path)
        return nick_overrides_config(saved)


def display_nick(uid: Any, fallback: str = "", doc: dict | None = None) -> str:
    """实际输出到弹幕的称呼：昵称映射优先，其次当前账号备注，否则实时昵称。"""
    user_uid = str(uid or "").strip()
    fallback = str(fallback or "")
    if not user_uid:
        return fallback
    data = doc if doc is not None else load()
    for item in nick_overrides_config(data):
        if item["uid"] == user_uid and item["enabled"]:
            return item["alias"]
    chat_control = chat_control_config(data)
    if user_uid == chat_control["owner_uid"] and chat_control["owner_nick"]:
        return chat_control["owner_nick"]
    return fallback
