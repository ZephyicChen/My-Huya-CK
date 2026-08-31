from __future__ import annotations

from fastapi import APIRouter, HTTPException

from huya_ck.features.registry import get_spec, public_catalog
from huya_ck.platform import config_store

router = APIRouter()


@router.get("/features")
def list_features() -> dict:
    return {"features": public_catalog()}


@router.get("/config")
def get_config() -> dict:
    doc = config_store.load()
    return {
        "platform": config_store.platform_config(doc),
        "features": {item["id"]: config_store.feature_config(item["id"], doc) for item in public_catalog()},
    }


@router.put("/config")
def put_platform(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    platform = body.get("platform", body)
    if not isinstance(platform, dict):
        raise HTTPException(status_code=400, detail="platform must be an object")
    doc = config_store.put_platform(platform)
    return {"platform": config_store.platform_config(doc)}


@router.get("/features/{feature_id}/config")
def get_feature_config(feature_id: str) -> dict:
    try:
        get_spec(feature_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown feature: {feature_id}") from exc
    return {"id": feature_id, "config": config_store.feature_config(feature_id)}


@router.put("/features/{feature_id}/config")
def put_feature_config(feature_id: str, body: dict) -> dict:
    try:
        get_spec(feature_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown feature: {feature_id}") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    patch = body.get("config", body)
    if not isinstance(patch, dict):
        raise HTTPException(status_code=400, detail="config must be an object")
    allowed = set(config_store.feature_config(feature_id))
    unknown = set(patch) - allowed
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown keys: {sorted(unknown)}")
    config = config_store.put_feature(feature_id, patch)
    return {"id": feature_id, "config": config}


@router.get("/nick-overrides")
def get_nick_overrides() -> dict:
    return {"nick_overrides": config_store.nick_overrides_config()}


@router.put("/nick-overrides")
def put_nick_overrides(body: dict) -> dict:
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="body must be an object")
    overrides = body.get("nick_overrides", body)
    if not isinstance(overrides, list):
        raise HTTPException(status_code=400, detail="nick_overrides must be an array")
    for item in overrides:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="nick_overrides items must be objects")
        unknown = set(item) - {"uid", "alias", "note", "enabled"}
        if unknown:
            raise HTTPException(status_code=400, detail=f"unknown keys: {sorted(unknown)}")
    saved = config_store.put_nick_overrides(overrides)
    return {"nick_overrides": saved}
