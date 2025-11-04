# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

# TODO: structlog or keep lightweight?

"""Logging utilities for OpenMCP.

This mirrors the richer logger used in ``api-final`` while keeping the surface
area minimal.  It supports Rich-based console output, optional JSON logging, and
is idempotent by default.

Environment variables:
* ``OPENMCP_LOG_LEVEL`` – override log level (default: INFO)
* ``OPENMCP_LOG_JSON`` – emit JSON logs when set
* ``OPENMCP_LOG_DISABLE_RICH`` – disable Rich console handler
"""

from __future__ import annotations

import logging
import os
from typing import Any, Final

import orjson as oj
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install as rich_install


DEFAULT_LOGGER_NAME: Final[str] = "openmcp"
ENV_LOG_LEVEL: Final[str] = "OPENMCP_LOG_LEVEL"
ENV_LOG_JSON: Final[str] = "OPENMCP_LOG_JSON"
ENV_DISABLE_RICH: Final[str] = "OPENMCP_LOG_DISABLE_RICH"
_LOGGER_CONFIGURED: bool = False

rich_install(show_locals=False)


class StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "pid": record.process,
            "thread": record.thread,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        builtin = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "process",
            "processName",
            "message",
            "asctime",
        }
        context = {
            key: value
            for key, value in record.__dict__.items()
            if key not in builtin and not key.startswith("_structured_")
        }
        if context:
            payload["context"] = context

        return oj.dumps(payload, default=self._default).decode("utf-8")

    @staticmethod
    def _default(value: Any) -> Any:
        if isinstance(value, set):
            return sorted(value)
        if isinstance(value, (bytes, bytearray)):
            return value.decode(errors="replace")
        return value


class _ConsoleSingleton:
    _console: Console | None = None

    @classmethod
    def get(cls) -> Console:
        if cls._console is None:
            cls._console = Console()
        return cls._console


def _read_bool_env(key: str) -> bool:
    value = os.getenv(key)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_log_level() -> int:
    override = os.getenv(ENV_LOG_LEVEL)
    if not override:
        return logging.INFO
    try:
        return getattr(logging, override.upper())
    except AttributeError:
        return logging.INFO


def _rich_handler(level: int) -> RichHandler:
    handler = RichHandler(
        console=_ConsoleSingleton.get(),
        rich_tracebacks=True,
        show_time=True,
        show_path=True,
        show_level=True,
        markup=True,
        log_time_format="%Y-%m-%d %H:%M:%S",
    )
    handler.setLevel(level)
    return handler


def _json_handler(level: int) -> logging.Handler:
    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.setFormatter(StructuredFormatter())
    return handler


def configure_logging(*, force: bool = False) -> None:
    """Configure root logging with Rich + JSON handlers as needed."""
    global _LOGGER_CONFIGURED
    root = logging.getLogger()

    if root.handlers and not force:
        return

    if force and root.handlers:
        for handler in list(root.handlers):
            root.removeHandler(handler)
            handler.close()

    level = _resolve_log_level()
    root.setLevel(level)

    use_json = _read_bool_env(ENV_LOG_JSON)
    disable_rich = _read_bool_env(ENV_DISABLE_RICH)

    if not use_json and not disable_rich:
        root.addHandler(_rich_handler(level))
    if use_json:
        root.addHandler(_json_handler(level))
    if not root.handlers:
        root.addHandler(_rich_handler(level))

    _LOGGER_CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    if not _LOGGER_CONFIGURED:
        configure_logging()
    return logging.getLogger(name or DEFAULT_LOGGER_NAME)


__all__ = ["configure_logging", "get_logger", "DEFAULT_LOGGER_NAME"]
