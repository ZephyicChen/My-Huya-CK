"""解析并执行严格的 LU 场控指令。"""

from __future__ import annotations

import re
from typing import Any

from huya_ck.log import get_logger
from huya_ck.platform import config_store
from huya_ck.platform.chat_state import chat_state

log = get_logger()

_COMMAND = re.compile(r"^\s*LU\s*(开启|关闭)\s*(发送|欢迎|感谢)\s*[！!。.]?\s*$", re.IGNORECASE)
_TARGET_MODULES = {
    "发送": ("danmaku",),
    "欢迎": ("welcome",),
    "感谢": ("gift_thank", "guard_thank", "superfan_thank", "noble_thank"),
}


def parse_command(text: Any) -> dict | None:
    match = _COMMAND.fullmatch(str(text or ""))
    if match is None:
        return None
    action, target = match.groups()
    return {
        "action": action,
        "target": target,
        "enabled": action == "开启",
        "modules": list(_TARGET_MODULES[target]),
    }


def execute(event: dict, queue: Any) -> dict | None:
    command = parse_command(event.get("content"))
    if command is None:
        return None
    authorization = config_store.chat_authorization(event.get("uid"))
    if authorization is None:
        return {**command, "ok": False, "changed_modules": [], "reason": "unauthorized"}

    allowed = set(authorization["allowed_modules"])
    changed_modules = [module for module in command["modules"] if module in allowed]
    if not changed_modules:
        log.info(
            "拒绝 LU 指令（用户=%s，uid=%s，身份=%s，无目标权限=%s）",
            event.get("nick") or "未知",
            event.get("uid") or "未知",
            authorization["role"],
            command["target"],
        )
        result = {**command, "ok": False, "changed_modules": [], "reason": "forbidden"}
        chat_state.record_command(event, result)
        return result

    config_store.set_features_enabled(changed_modules, command["enabled"])
    if "danmaku" in changed_modules and not command["enabled"]:
        queue.clear()
        # 关闭发送：小说暂停并清除在途段，保留已成功进度，重开后不自动恢复
        from huya_ck.features.novel.player import novel_player

        novel_player.pause(reason="LU 关闭 发送：允许发送已关闭")
    log.info(
        "已执行 LU 指令（用户=%s，uid=%s，动作=%s，目标=%s，模块=%s）",
        event.get("nick") or "未知",
        event.get("uid") or "未知",
        command["action"],
        command["target"],
        ",".join(changed_modules),
    )
    result = {**command, "ok": True, "changed_modules": changed_modules, "reason": "executed"}
    chat_state.record_command(event, result)
    return result
