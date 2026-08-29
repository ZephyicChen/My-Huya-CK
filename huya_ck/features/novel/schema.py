"""文本轮播模块配置字段与默认值。不在 registry 注册：趣味互动分页用专用 API 管理配置。"""

from __future__ import annotations

MAX_CHARS_MIN = 15
MAX_CHARS_MAX = 28
INTERVAL_MS_MIN = 3000

DEFAULT = {
    "enabled": False,
    "novel_id": "",
    "max_chars": 28,
    "interval_ms": 10000,
    "loop": True,
    "next_index": 0,
    "state": "paused",
}

FIELDS = [
    {
        "key": "enabled",
        "label": "轮播模块开关",
        "type": "bool",
        "hint": "关闭后不产生新的轮播弹幕。",
    },
    {
        "key": "max_chars",
        "label": "每条最大字数",
        "type": "int",
        "min": MAX_CHARS_MIN,
        "max": MAX_CHARS_MAX,
        "hint": "单条弹幕长度上限（虎牙输入框 30 字）。",
    },
    {
        "key": "interval_ms",
        "label": "发送间隔（秒）",
        "type": "seconds",
        "min": INTERVAL_MS_MIN / 1000,
        "hint": "实际间隔取它与全局发送 CD 的较大值。",
    },
    {
        "key": "loop",
        "label": "循环播放",
        "type": "bool",
        "hint": "播完最后一段后从第一段继续；适合话术库轮播。",
    },
]


def clamp_config(config: dict) -> dict:
    """读取时兜底：开关归一、数值夹到合法区间。"""
    out = dict(DEFAULT)
    if isinstance(config, dict):
        out.update({key: value for key, value in config.items() if key in DEFAULT})
    out["enabled"] = bool(out["enabled"])
    out["loop"] = bool(out["loop"])
    out["novel_id"] = str(out["novel_id"] or "").strip()
    out["max_chars"] = min(MAX_CHARS_MAX, max(MAX_CHARS_MIN, int(out["max_chars"] or DEFAULT["max_chars"])))
    out["interval_ms"] = max(INTERVAL_MS_MIN, int(out["interval_ms"] or DEFAULT["interval_ms"]))
    out["next_index"] = max(0, int(out.get("next_index") or 0))
    if out["state"] not in ("idle", "playing", "paused", "completed", "error"):
        out["state"] = "paused"
    return out
