# -*- coding: utf-8 -*-
"""
core/logging_config.py – PipeAgent
===================================
Industrial-grade, high-performance logging setup supporting:
- Console coloring for local development
- Rotating file logging (Size & Time based)
- JSON structured logging for log collectors (ELK, Grafana Loki)
- Thread-safe context binding (pipeline_id, agent_name, etc.)
- Deep integration with PipeAgentError
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Implementation note.
try:
    from config import (
        LOG_FILE,
        LOG_FORMAT,
        LOG_LEVEL,
        LOG_MAX_BYTES,
        LOG_BACKUP_COUNT,
        LOG_AS_JSON,
        LOG_TO_CONSOLE,
    )
except ImportError:
    LOG_LEVEL = "INFO"
    LOG_FILE = "logs/pipeagent.log"
    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(name)s:%(funcName)s:%(lineno)d] - %(message)s"
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
    LOG_BACKUP_COUNT = 5
    LOG_AS_JSON = False
    LOG_TO_CONSOLE = True


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class ColoredConsoleFormatter(logging.Formatter):
    """فرمت‌دهنده رنگی برای ترمینال‌های توسعه."""
    
    # Implementation note.
    GREY = "\x1b[38;20m"
    CYAN = "\x1b[36;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    LEVEL_COLORS = {
        logging.DEBUG: CYAN,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, self.GREY)
        # Implementation note.
        record.levelname = f"{color}{record.levelname:<8}{self.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """
    فرمت‌دهنده ساختاریافته JSON برای سرورها و سیستم‌های لاگ‌گیری متمرکز.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "location": {
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "path": record.pathname,
            },
            "process_id": record.process,
            "thread_id": record.thread,
        }

        # Implementation note.
        if hasattr(record, "context") and isinstance(record.context, dict):
            log_payload["context"] = record.context

        # Implementation note.
        if record.exc_info and record.exc_info[1]:
            exc = record.exc_info[1]
            if hasattr(exc, "to_dict"):  # Implementation note.
                log_payload["exception"] = exc.to_dict()
            else:
                log_payload["exception"] = {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                }

        return json.dumps(log_payload, ensure_ascii=False)


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

class PipeAgentLoggerAdapter(logging.LoggerAdapter):
    """
    ادپتری برای تزریق فیلدهای پویای ایجنت، پایپ‌لاین و کاربر به هر لاگ.
    """
    def process(self, msg: Any, kwargs: Dict[str, Any]) -> tuple[Any, Dict[str, Any]]:
        extra = kwargs.setdefault("extra", {})
        context = extra.setdefault("context", {})
        
        # Implementation note.
        if self.extra:
            context.update(self.extra)
        
        return msg, kwargs

    def bind(self, **kwargs: Any) -> PipeAgentLoggerAdapter:
        """ایجاد یک نسخه جدید از ادپتر با فیلدهای جدید (Immutable Style)."""
        new_extra = (self.extra or {}).copy()
        new_extra.update(kwargs)
        return PipeAgentLoggerAdapter(self.logger, new_extra)


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

_INITIALIZED = False

def init_logging(
    level: Optional[Union[str, int]] = None,
    log_file: Optional[Union[str, Path]] = None,
    as_json: bool = LOG_AS_JSON,
    to_console: bool = LOG_TO_CONSOLE,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT,
) -> None:
    """
    پیکربندی سراسری Root Logger پروژه.
    این متد تنها یک بار در ابتدای اجرای نرم‌افزار باید اجرا شود.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    resolved_level = getattr(logging, str(level or LOG_LEVEL).upper(), logging.INFO)
    root_logger = logging.getLogger()
    root_logger.setLevel(resolved_level)

    # Implementation note.
    root_logger.handlers.clear()

    # Implementation note.
    if to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(resolved_level)
        
        if as_json:
            console_handler.setFormatter(JSONFormatter())
        else:
            console_handler.setFormatter(
                ColoredConsoleFormatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
            )
        root_logger.addHandler(console_handler)

    # Implementation note.
    target_file = log_file or LOG_FILE
    if target_file:
        file_path = Path(target_file)
        try:
            # Implementation note.
            file_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = RotatingFileHandler(
                filename=str(file_path),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
                delay=True,  # Implementation note.
            )
            file_handler.setLevel(resolved_level)

            if as_json:
                file_handler.setFormatter(JSONFormatter())
            else:
                file_handler.setFormatter(
                    logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
                )
            
            root_logger.addHandler(file_handler)
        except Exception as err:
            # Implementation note.
            sys.stderr.write(f"WARNING: Could not configure file logger: {err}\n")

    _INITIALIZED = True


# ──────────────────────────────────────────────
# Implementation note.
# ──────────────────────────────────────────────

def get_logger(name: str, **context: Any) -> PipeAgentLoggerAdapter:
    """
    دریافت لاگر استاندارد با قابلیت بایند کردن Context اختصاصی.

    Example:
        logger = get_logger(__name__, agent_id="Agent-007")
        logger.info("Task started")
    """
    if not _INITIALIZED:
        init_logging()
        
    base_logger = logging.getLogger(name)
    return PipeAgentLoggerAdapter(base_logger, extra=context)


def setup_logger(name: str) -> logging.Logger:
    """
    سازگاری با کدهای قدیمی (Backward Compatibility).
    """
    if not _INITIALIZED:
        init_logging()
    return logging.getLogger(name)