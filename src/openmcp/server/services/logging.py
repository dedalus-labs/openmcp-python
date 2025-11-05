# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Logging capability service.

Implements the logging capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging
  (logging capability, setLevel request, message notifications)

Bridges Python's logging system to MCP message notifications with per-session
level filtering and automatic handler installation.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
import logging
from typing import Any
import weakref

import anyio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.exceptions import McpError

from ..notifications import NotificationSink
from ... import types


_LOGGING_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "notice": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
    "alert": logging.CRITICAL,
    "emergency": logging.CRITICAL,
}


class LoggingService:
    def __init__(self, logger, *, notification_sink: NotificationSink) -> None:
        self._logger = logger
        self._sink = notification_sink
        self._lock = anyio.Lock()
        self._session_levels: weakref.WeakKeyDictionary[Any, int] = weakref.WeakKeyDictionary()
        self._handler = _NotificationHandler(self)
        self._install_handler()

    async def set_level(self, level: types.LoggingLevel) -> None:
        numeric = self._resolve(level)
        logging.getLogger().setLevel(numeric)
        self._logger.setLevel(numeric)

        try:
            context = request_ctx.get()
        except LookupError:  # pragma: no cover - called outside request context
            return

        async with self._lock:
            self._session_levels[context.session] = numeric

    async def emit(self, level: types.LoggingLevel, data: Any, logger_name: str | None = None) -> None:
        numeric = self._resolve(level)
        await self._broadcast(level, numeric, data, logger_name)

    async def handle_log_record(self, record: logging.LogRecord) -> None:
        level_name = self._coerce_level_name(record.levelno)
        data: dict[str, Any] = {"message": record.getMessage()}
        if record.exc_info:
            formatter = logging.Formatter()
            data["exception"] = formatter.formatException(record.exc_info)
        await self._broadcast(level_name, record.levelno, data, self._coerce_logger_name(record.name))

    def _resolve(self, level: str) -> int:
        try:
            return _LOGGING_LEVEL_MAP[level]
        except KeyError as exc:  # pragma: no cover - defensive
            raise McpError(
                types.ErrorData(code=types.INVALID_PARAMS, message=f"Unsupported logging level '{level}'")
            ) from exc

    def _coerce_level_name(self, numeric: int) -> types.LoggingLevel:
        if numeric >= logging.CRITICAL:
            return "critical"
        if numeric >= logging.ERROR:
            return "error"
        if numeric >= logging.WARNING:
            return "warning"
        if numeric >= logging.INFO:
            return "info"
        return "debug"

    def _coerce_logger_name(self, name: str | None) -> str | None:
        if not name or name == "root":
            return None
        return name

    def _install_handler(self) -> None:
        root = logging.getLogger()
        existing: Iterable[logging.Handler] = getattr(root, "handlers", [])
        for handler in existing:
            if isinstance(handler, _NotificationHandler) and handler.service is self:
                return
        root.addHandler(self._handler)

    async def _broadcast(
        self, level: types.LoggingLevel, numeric_level: int, data: Any, logger_name: str | None
    ) -> None:
        async with self._lock:
            targets = list(self._session_levels.items())

        if not targets:
            return

        params = types.LoggingMessageNotificationParams(level=level, logger=logger_name, data=data)
        notification = types.ServerNotification(types.LoggingMessageNotification(params=params))

        stale: list[Any] = []
        for session, threshold in targets:
            if numeric_level < threshold:
                continue
            try:
                await self._sink.send_notification(session, notification)
            except Exception:  # pragma: no cover - defensive cleanup
                stale.append(session)

        if not stale:
            return

        async with self._lock:
            for session in stale:
                self._session_levels.pop(session, None)


class _NotificationHandler(logging.Handler):
    def __init__(self, service: LoggingService) -> None:
        super().__init__(level=logging.NOTSET)
        self.service = service

    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - indirectly tested
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                anyio.from_thread.run(self.service.handle_log_record, record)
            except RuntimeError:
                return
        else:
            loop.create_task(self.service.handle_log_record(record))
