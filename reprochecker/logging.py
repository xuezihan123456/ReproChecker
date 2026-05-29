"""统一日志系统"""

from __future__ import annotations

import logging
import sys

from reprochecker.config import get_config

_initialized = False


def setup_logging(level: str = "INFO") -> None:
    """初始化日志系统"""
    global _initialized
    if _initialized:
        return
    _initialized = True

    config = get_config()
    log_file = config.data_dir / "reprochecker.log"

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件 handler（UTF-8 编码）
    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    # 控制台 handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch.setFormatter(fmt)

    root = logging.getLogger("reprochecker")
    root.setLevel(logging.DEBUG)
    root.addHandler(fh)
    root.addHandler(ch)


def get_logger(name: str) -> logging.Logger:
    """获取子 logger"""
    setup_logging()
    return logging.getLogger(f"reprochecker.{name}")
