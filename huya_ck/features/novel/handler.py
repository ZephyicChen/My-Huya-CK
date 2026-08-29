"""LU 轮播指令：解析与授权执行。本质是文本轮播，小说只是内容之一。"""

from __future__ import annotations

import re
from typing import Any

from huya_ck.features.danmaku.handler import danmaku
from huya_ck.features.novel.library import NovelError
from huya_ck.features.novel.player import novel_player
from huya_ck.log import get_logger
from huya_ck.platform import config_store
from huya_ck.platform.chat_state import chat_state

log = get_logger()

NOVEL_ACTIONS = ("开始", "暂停", "继续", "停止", "下一段", "下一条", "状态")
_COMMAND = re.compile(r"^\s*LU\s*(?:小说|轮播)\s*(开始|暂停|继续|停止|下一段|下一条|状态)\s*[！!。.]?\s*$", re.IGNORECASE)


def parse_command(text: Any) -> dict | None:
    match = _COMMAND.fullmatch(str(text or ""))
    if match is None:
        return None
    return {"category": "novel", "action": match.group(1)}


def _run_action(action: str) -> dict:
    if action == "开始":
        return novel_player.start()
    if action == "暂停":
        return novel_player.pause()
    if action == "继续":
        return novel_player.resume()
    if action == "停止":
        return novel_player.stop()
    if action in ("下一段", "下一条"):
        return novel_player.next_segment()
    return _status_feedback()


def _status_feedback() -> dict:
    """「状态」需要弹幕反馈；其余指令第一版不回弹幕。"""
    snap = novel_player.snapshot()
    cfg = snap["config"]
    meta = snap.get("novel_meta")
    name = meta["name"] if meta else "未选择"
    state_labels = {
        "idle": "待机",
        "playing": "播放中",
        "paused": "已暂停",
        "completed": "已播完",
        "error": "异常",
    }
    state = state_labels.get(cfg["state"], cfg["state"])
    text = f"轮播「{name}」：{state}，进度 {snap['current_index']}/{snap['total_segments']}"
    if snap.get("last_error"):
        text += f"，{snap['last_error'][:40]}"
    danmaku.submit(
        text,
        source="remote_control",
        event_id=f"novel-status:{cfg['novel_id']}:{cfg['next_index']}",
        reason="轮播状态反馈",
        priority="high",
    )
    return {"ok": True, "state": cfg["state"]}


def execute(event: dict, queue: Any) -> dict | None:
    """返回 None 表示这条弹幕不是轮播指令。"""
    command = parse_command(event.get("content"))
    if command is None:
        return None
    authorization = config_store.chat_authorization(event.get("uid"))
    result = {
        **command,
        "ok": False,
        "changed_modules": [],
        "reason": "",
    }
    if authorization is None or "novel" not in authorization["allowed_interactions"]:
        log.info(
            "拒绝 LU 轮播指令（用户=%s，uid=%s，身份=%s，无轮播权限）",
            event.get("nick") or "未知",
            event.get("uid") or "未知",
            authorization["role"] if authorization else "普通观众",
        )
        result["reason"] = "unauthorized"
        chat_state.record_command(event, result)
        return result

    try:
        outcome = _run_action(command["action"])
    except NovelError as exc:
        log.info("LU 轮播指令未执行（用户=%s，动作=%s）：%s", event.get("nick"), command["action"], exc)
        result["reason"] = str(exc)
        chat_state.record_command(event, result)
        return result

    log.info(
        "已执行 LU 轮播指令（用户=%s，uid=%s，动作=%s）",
        event.get("nick") or "未知",
        event.get("uid") or "未知",
        command["action"],
    )
    result.update({"ok": bool(outcome.get("ok", True)), "reason": outcome.get("reason", "executed")})
    chat_state.record_command(event, result)
    return result
