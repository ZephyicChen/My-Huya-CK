"""场控进程日志：打到启动它的那个命令行窗口。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from huya_ck.paths import ROOT

LOGGER_NAME = "huya_ck"
LOG_DIR = ROOT / "logs"
LOG_PATH = LOG_DIR / "huya_ck.log"


def setup_logging() -> logging.Logger:
    log = logging.getLogger(LOGGER_NAME)
    if log.handlers:
        return log
    formatter = logging.Formatter("[%(asctime)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    log.addHandler(console_handler)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=2 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    log.addHandler(file_handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    log.info("日志文件 %s", LOG_PATH)
    return log


def get_logger() -> logging.Logger:
    log = logging.getLogger(LOGGER_NAME)
    if not log.handlers:
        return setup_logging()
    return log
