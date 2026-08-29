"""已注册功能模块。UI 只消费 schema，不写死字段名。"""

from __future__ import annotations

from copy import deepcopy

from huya_ck.features import danmaku, gift_thank, guard_thank, noble_thank, superfan_thank, welcome
from huya_ck.features.danmaku import schema as danmaku_schema
from huya_ck.features.gift_thank import schema as gift_schema
from huya_ck.features.guard_thank import schema as guard_schema
from huya_ck.features.noble_thank import schema as noble_schema
from huya_ck.features.superfan_thank import schema as superfan_schema
from huya_ck.features.welcome import schema as welcome_schema

_SPECS = (
    {
        "id": "welcome",
        "title": "进场欢迎",
        "kind": "event",
        "events": ("enter",),
        "fields": welcome_schema.FIELDS,
        "defaults": welcome_schema.DEFAULT,
        "package": welcome,
    },
    {
        "id": "gift_thank",
        "title": "礼物感谢",
        "kind": "event",
        "events": ("gift",),
        "fields": gift_schema.FIELDS,
        "defaults": gift_schema.DEFAULT,
        "package": gift_thank,
    },
    {
        "id": "guard_thank",
        "title": "守护",
        "kind": "event",
        "events": ("guard_open",),
        "fields": guard_schema.FIELDS,
        "defaults": guard_schema.DEFAULT,
        "package": guard_thank,
        "ui_group": {"id": "non_gift_thank", "title": "非礼物感谢"},
    },
    {
        "id": "superfan_thank",
        "title": "超粉",
        "kind": "event",
        "events": ("superfan_open",),
        "fields": superfan_schema.FIELDS,
        "defaults": superfan_schema.DEFAULT,
        "package": superfan_thank,
        "ui_group": {"id": "non_gift_thank", "title": "非礼物感谢"},
    },
    {
        "id": "noble_thank",
        "title": "贵族",
        "kind": "event",
        "events": ("noble_open",),
        "fields": noble_schema.FIELDS,
        "defaults": noble_schema.DEFAULT,
        "package": noble_thank,
        "ui_group": {"id": "non_gift_thank", "title": "非礼物感谢"},
    },
    {
        "id": "danmaku",
        "title": "弹幕发送",
        "kind": "capability",
        "events": (),
        "fields": danmaku_schema.FIELDS,
        "defaults": danmaku_schema.DEFAULT,
        "package": danmaku,
    },
)


def all_specs() -> list[dict]:
    return list(_SPECS)


def get_spec(feature_id: str) -> dict:
    for spec in _SPECS:
        if spec["id"] == feature_id:
            return spec
    raise KeyError(feature_id)


def defaults() -> dict[str, dict]:
    return {spec["id"]: deepcopy(spec["defaults"]) for spec in _SPECS}


def public_catalog() -> list[dict]:
    catalog = []
    for spec in _SPECS:
        item = {
            "id": spec["id"],
            "title": spec["title"],
            "kind": spec["kind"],
            "events": list(spec["events"]),
            "fields": spec["fields"],
        }
        if spec.get("ui_group"):
            item["ui_group"] = spec["ui_group"]
        catalog.append(item)
    return catalog
