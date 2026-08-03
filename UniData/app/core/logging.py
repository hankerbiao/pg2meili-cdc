"""应用日志初始化模块。"""

from pathlib import Path
import sys
from typing import Optional

from loguru import logger

from app.core.config import Settings


_configured = False


def init_logging(settings: Optional[Settings] = None) -> None:
    """初始化 Loguru 日志配置。

    只应在进程启动时调用一次，避免重复配置导致日志格式混乱。
    """
    global _configured
    if _configured:
        return
    if settings is None:
        settings = Settings()

    logger.remove()

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>"
    )

    logger.add(
        sink=sys.stdout,
        level=settings.log_level,
        backtrace=settings.log_backtrace,
        diagnose=settings.log_diagnose,
        serialize=settings.log_json,
        format=fmt if not settings.log_json else None,
    )

    if settings.log_file_enabled:
        log_dir = Path(settings.log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / "unidata.log",
            level=settings.log_level,
            rotation=settings.log_rotation,
            retention=settings.log_retention,
            backtrace=settings.log_backtrace,
            diagnose=settings.log_diagnose,
            serialize=settings.log_json,
            format=fmt if not settings.log_json else None,
            enqueue=True,
        )
    _configured = True
