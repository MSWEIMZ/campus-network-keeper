"""
校园网保活工具 - 日志模块
支持控制台 + 文件双输出，文件自动轮转。
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import CONFIG, LOG_DIR

_INITIALIZED = False


def setup_logger() -> logging.Logger:
    """初始化并返回全局 logger"""
    global _INITIALIZED
    logger = logging.getLogger("campus_keeper")

    if _INITIALIZED:
        return logger

    logger.setLevel(getattr(logging, CONFIG.log_level.upper(), logging.INFO))

    # ---- 格式 ----
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- 控制台 ----
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    if hasattr(console.stream, 'reconfigure'):
        console.stream.reconfigure(encoding='utf-8')
    logger.addHandler(console)

    # ---- 文件（自动轮转）----
    log_file: Path = LOG_DIR / "campus_keeper.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=CONFIG.log_max_mb * 1024 * 1024,
        backupCount=CONFIG.log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    _INITIALIZED = True
    logger.info("日志模块初始化完成，日志文件: %s", log_file)
    return logger


# 便捷全局 logger
log = setup_logger()

