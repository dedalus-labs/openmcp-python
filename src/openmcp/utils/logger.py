# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal logging utilities for OpenMCP.

The default setup uses only Python's standard library to stay lightweight and
dependency-free. You can enable structured JSON output and plug in a faster
serializer like orjson without increasing the base footprint

See examples/advanced/custom_logging for example usage.
"""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import os
from typing import Any, ClassVar, Final


# ANSI color codes for terminal output
RESET: Final[str] = "\033[0m"
BOLD: Final[str] = "\033[1m"
DIM: Final[str] = "\033[2m"

# Level colors (matches Python 3.13+ traceback style)
DEBUG_COLOR: Final[str] = "\033[36m"     # Cyan
INFO_COLOR: Final[str] = "\033[32m"      # Green
WARNING_COLOR: Final[str] = "\033[33m"   # Yellow
ERROR_COLOR: Final[str] = "\033[1;31m"   # Bold bright red (Python exception style)
CRITICAL_COLOR: Final[str] = "\033[1;35m"  # Bold bright magenta (Python error span style)

# Component colors
TIMESTAMP_COLOR: Final[str] = "\033[90m"  # Bright black (gray)
LOGGER_COLOR: Final[str] = "\033[94m"     # Bright blue

DEFAULT_LOGGER_NAME: Final[str] = "openmcp"
ENV_LOG_LEVEL: Final[str] = "OPENMCP_LOG_LEVEL"
ENV_LOG_JSON: Final[str] = "OPENMCP_LOG_JSON"
ENV_NO_COLOR: Final[str] = "NO_COLOR"  # Standard env var for disabling colors
DEFAULT_FORMAT: Final[str] = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_DATEFMT: Final[str] = "%Y-%m-%d %H:%M:%S"

JsonSerializer = Callable[[dict[str, Any]], str]
PayloadTransformer = Callable[[dict[str, Any]], dict[str, Any]]

_BUILTIN_RECORD_KEYS: set[str] = {
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
    "task",
    "taskName",
    "context",
    "message",
    "asctime",
}


class ColoredFormatter(logging.Formatter):
    """Formatter that adds ANSI colors to log output.

    Override LEVEL_COLORS to customize colors for each log level.
    """

    LEVEL_COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": DEBUG_COLOR,
        "INFO": INFO_COLOR,
        "WARNING": WARNING_COLOR,
        "ERROR": ERROR_COLOR,
        "CRITICAL": CRITICAL_COLOR,
    }

    def format(self, record: logging.LogRecord) -> str:
        # Apply colors to components
        levelname_color = self.LEVEL_COLORS.get(record.levelname, "")

        # Save original values
        orig_levelname = record.levelname
        orig_name = record.name

        # Colorize level and logger name
        record.levelname = f"{levelname_color}{record.levelname}{RESET}"
        record.name = f"{LOGGER_COLOR}{record.name}{RESET}"

        # Format with parent formatter
        result = super().format(record)

        # Restore original values
        record.levelname = orig_levelname
        record.name = orig_name

        return result


class OpenMCPHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """StreamHandler subclass managed by OpenMCP.

    Subclass this to customize behavior or override formatters.
    """


class StructuredJSONFormatter(logging.Formatter):
    """Serialize log records into JSON using a user-provided serializer."""

    def __init__(
        self,
        serializer: JsonSerializer,
        *,
        datefmt: str | None = None,
        payload_transformer: PayloadTransformer | None = None,
    ) -> None:
        super().__init__(datefmt=datefmt)
        self._serializer = serializer
        self._transformer = payload_transformer or _default_payload_transformer

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
            "process": record.process,
            "thread": record.thread,
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        extra = {}
        for key, value in record.__dict__.items():
            if key == "context" and isinstance(value, dict):
                extra.update(value)
                continue

            if key in _BUILTIN_RECORD_KEYS or key.startswith("_structured_"):
                continue

            if key not in extra:
                extra[key] = value
        if extra:
            payload["context"] = extra

        transformed = self._transformer(payload)
        return self._serializer(transformed)


def _default_json_serializer(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _default_payload_transformer(payload: dict[str, Any]) -> dict[str, Any]:
    return payload


def _has_openmcp_handler(root: logging.Logger) -> bool:
    return any(isinstance(handler, OpenMCPHandler) for handler in root.handlers)


def _read_bool_env(key: str) -> bool:
    value = os.getenv(key)
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_level(level: int | str | None) -> int:
    if level is None:
        override = os.getenv(ENV_LOG_LEVEL)
        if override:
            level = override
        else:
            return logging.INFO

    if isinstance(level, int):
        return level

    try:
        level_value: int = getattr(logging, str(level).upper())
    except AttributeError:
        return logging.INFO
    else:
        return level_value


def setup_logger(
    *,
    level: int | str | None = None,
    use_json: bool | None = None,
    use_color: bool | None = None,
    json_serializer: JsonSerializer | None = None,
    payload_transformer: PayloadTransformer | None = None,
    fmt: str | None = None,
    datefmt: str | None = DEFAULT_DATEFMT,
    force: bool = False,
) -> None:
    """Configure the root logger.

    Args:
        level: Override the log level. Falls back to ``OPENMCP_LOG_LEVEL`` then
            ``logging.INFO``.
        use_json: Enable JSON output. Defaults to ``OPENMCP_LOG_JSON`` when
            ``None``.
        use_color: Enable colored output. Defaults to ``True`` unless ``NO_COLOR``
            env var is set or ``use_json=True``. Set explicitly to override.
        json_serializer: Callable that converts the payload dict into a JSON
            string. Useful for integrating faster serializers like ``orjson``
            without adding dependencies.
        payload_transformer: Callable that mutates the payload before
            serialization, allowing structured models (e.g. Pydantic) to be
            adapted.
        fmt: Format string for plain-text logging.
        datefmt: Date format for plain-text logging.
        force: Reconfigure even if OpenMCP already attached its handler.

    Returns:
        None.

    """
    root = logging.getLogger()

    # Skip reconfig if OpenMCP has already attached its handler
    # unless caller explicitly requests a reset.
    if _has_openmcp_handler(root) and not force:
        return

    if force:
        for handler in list(root.handlers):
            if isinstance(handler, OpenMCPHandler):
                root.removeHandler(handler)
                handler.close()

    resolved_level = _resolve_level(level)
    root.setLevel(resolved_level)

    resolved_use_json = use_json if use_json is not None else _read_bool_env(ENV_LOG_JSON)

    # Determine color usage: explicit param > NO_COLOR env > default (True if not JSON)
    if use_color is not None:
        resolved_use_color = use_color
    elif os.getenv(ENV_NO_COLOR):
        resolved_use_color = False
    else:
        resolved_use_color = not resolved_use_json

    handler = OpenMCPHandler()
    handler.setLevel(resolved_level)

    formatter: logging.Formatter
    if resolved_use_json:
        serializer = json_serializer or _default_json_serializer
        formatter = StructuredJSONFormatter(serializer, datefmt=datefmt, payload_transformer=payload_transformer)
    elif resolved_use_color:
        formatter = ColoredFormatter(fmt or DEFAULT_FORMAT, datefmt=datefmt)
    else:
        formatter = logging.Formatter(fmt or DEFAULT_FORMAT, datefmt=datefmt)

    handler.setFormatter(formatter)
    root.addHandler(handler)


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a logger configured for OpenMCP usage.

    Args:
        name: Optional logger name. Defaults to ``DEFAULT_LOGGER_NAME``.

    Returns:
        ``logging.Logger`` configured with OpenMCP defaults.
    """
    root = logging.getLogger()
    if not _has_openmcp_handler(root):
        setup_logger()
    return logging.getLogger(name or DEFAULT_LOGGER_NAME)

__all__ = [
    "DEFAULT_LOGGER_NAME",
    "ColoredFormatter",
    "OpenMCPHandler",
    "StructuredJSONFormatter",
    "get_logger",
    "setup_logger",
]
