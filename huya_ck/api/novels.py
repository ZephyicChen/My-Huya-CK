from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from huya_ck.features.novel import library as library_module
from huya_ck.features.novel.library import NovelError
from huya_ck.features.novel.player import novel_player
from huya_ck.features.novel.schema import MAX_CHARS_MAX, MAX_CHARS_MIN
from huya_ck.platform import config_store

library = library_module.library

router = APIRouter()

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
PLAYER_ACTIONS = ("start", "pause", "resume", "stop", "next")


@router.get("/novels")
def list_novels() -> dict:
    return {"novels": library.list()}


@router.post("/novels")
async def upload_novel(request: Request) -> dict:
    """正文放请求体，显示名放查询参数 name。避免引入 multipart 依赖。"""
    name = str(request.query_params.get("name") or "").strip()
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="文件超过 5 MiB 上限")
    try:
        meta = library.upload(name, data)
    except NovelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"novel": meta}


@router.get("/novels/{novel_id}/preview")
def preview_novel(novel_id: str) -> dict:
    cfg = config_store.novel_config()
    try:
        return library.preview(novel_id, head_chars=200, max_chars_segment=cfg["max_chars"])
    except NovelError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/novels/{novel_id}")
def delete_novel(novel_id: str) -> dict:
    cfg = config_store.novel_config()
    if cfg["novel_id"] == novel_id and cfg["state"] == "playing":
        raise HTTPException(status_code=409, detail="该小说正在播放，请先停止再删除")
    try:
        library.delete(novel_id)
    except NovelError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if cfg["novel_id"] == novel_id:
        # 当前小说被删：清引用并把播放器复位
        config_store.put_novel({"novel_id": "", "next_index": 0})
        novel_player.stop()
    return {"ok": True}


@router.get("/novels/player")
def player_state() -> dict:
    return {"player": novel_player.snapshot()}


@router.get("/interaction")
def get_interaction() -> dict:
    return {"interaction": config_store.interaction_config(), "player": novel_player.snapshot()}


@router.put("/interaction")
def put_interaction(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    patch = body.get("interaction", body)
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="interaction must be an object")
    unknown = set(patch) - {"enabled"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown keys: {sorted(unknown)}")
    saved = config_store.put_interaction(patch)
    if not saved["enabled"]:
        novel_player.pause(reason="趣味互动总开关已关闭")
    return {"interaction": saved, "player": novel_player.snapshot()}


@router.get("/novels/settings")
def get_settings() -> dict:
    return {"config": config_store.novel_config()}


@router.put("/novels/settings")
def put_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    patch = body.get("config", body)
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="config must be an object")
    allowed = {"enabled", "novel_id", "max_chars", "interval_ms", "loop"}
    unknown = set(patch) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown keys: {sorted(unknown)}")
    if "max_chars" in patch:
        try:
            value = int(patch["max_chars"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="max_chars must be an integer")
        if not MAX_CHARS_MIN <= value <= MAX_CHARS_MAX:
            raise HTTPException(
                status_code=400, detail=f"max_chars must be {MAX_CHARS_MIN}~{MAX_CHARS_MAX}"
            )
    saved = config_store.put_novel(patch)
    if not saved["enabled"]:
        novel_player.pause(reason="小说模块开关已关闭")
    return {"config": saved, "player": novel_player.snapshot()}


@router.post("/novels/player/{action}")
def player_action(action: str) -> dict:
    if action not in PLAYER_ACTIONS:
        raise HTTPException(status_code=404, detail=f"unknown action: {action}")
    try:
        if action == "start":
            result = novel_player.start()
        elif action == "pause":
            result = novel_player.pause()
        elif action == "resume":
            result = novel_player.resume()
        elif action == "stop":
            result = novel_player.stop()
        else:
            result = novel_player.next_segment()
    except NovelError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not result.get("ok"):
        detail = result.get("reason") or "操作被拒绝"
        raise HTTPException(status_code=409, detail=detail)
    return {"ok": True, "player": novel_player.snapshot()}
