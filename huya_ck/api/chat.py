from __future__ import annotations

from fastapi import APIRouter, HTTPException

from huya_ck.platform import config_store
from huya_ck.platform.chat_state import chat_state

router = APIRouter()


@router.get("/control")
def get_control() -> dict:
    return {"config": config_store.chat_control_config(), "state": chat_state.snapshot()}


@router.put("/control")
def put_control(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    config = body.get("config", body)
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config must be an object")
    unknown = set(config) - {"owner_uid", "owner_nick", "whitelist"}
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown keys: {sorted(unknown)}")
    if "whitelist" in config and not isinstance(config["whitelist"], list):
        raise HTTPException(status_code=400, detail="whitelist must be an array")
    saved = config_store.put_chat_control(config)
    return {"config": saved, "state": chat_state.snapshot()}


@router.get("/state")
def get_state() -> dict:
    return {"state": chat_state.snapshot()}
