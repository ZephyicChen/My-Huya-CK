"""FastAPI 入口：配置 API + 静态 WebUI。"""

from __future__ import annotations

import argparse
import mimetypes
import webbrowser

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from huya_ck import __version__
from huya_ck.api.config import router as config_router
from huya_ck.api.run import router as run_router
from huya_ck.log import get_logger, setup_logging
from huya_ck.paths import WEB_DIR
from huya_ck.platform.worker import worker

# Windows 常把 .js 标成 text/plain，ES module 会被浏览器拒绝，页面空白。
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("text/html", ".html")


def create_app() -> FastAPI:
    app = FastAPI(title="huya_ck", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(config_router, prefix="/api")
    app.include_router(run_router, prefix="/api/run")

    index = WEB_DIR / "index.html"
    assets = WEB_DIR / "assets"
    if index.exists():
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index_page() -> FileResponse:
            return FileResponse(index, media_type="text/html")
    else:

        @app.get("/")
        def missing_ui() -> dict:
            return {
                "ok": True,
                "ui": False,
                "hint": "WebUI 未构建。在 web-src 执行 npm install && npm run build",
            }

    return app


app = create_app()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="huya_ck")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    url = f"http://{args.host}:{args.port}/"
    log = setup_logging()
    log.info("========================================")
    log.info("  虎牙场控进程已启动")
    log.info("  网页控制台 %s", url)
    log.info("  本窗口持续打印日志")
    log.info("  关闭本窗口 = 退出场控")
    log.info("========================================")
    if not args.no_browser:
        webbrowser.open(url)

    import uvicorn

    try:
        uvicorn.run(
            "huya_ck.app:app",
            host=args.host,
            port=args.port,
            reload=False,
            log_level="info",
        )
    finally:
        worker.shutdown()
    return 0
