from fastapi import APIRouter

from huya_ck.log import get_logger
from huya_ck.platform import config_store
from huya_ck.platform.worker import worker

router = APIRouter()
log = get_logger()


@router.get("/status")
async def status() -> dict:
    return worker.snapshot()


@router.post("/login")
async def login() -> dict:
    log.info("网页点击：打开浏览器登录")
    return await worker.login()


@router.post("/start")
async def start() -> dict:
    platform = config_store.platform_config()
    log.info(
        "网页点击：启动场控 房间=%s 窗口=%s",
        platform["room"] or "(空)",
        "显示" if platform.get("show_browser") else "后台",
    )
    return await worker.start(platform["room"], headless=not platform.get("show_browser"))


@router.post("/stop")
async def stop() -> dict:
    log.info("网页点击：停止挂房")
    return await worker.stop()
