"""Shared test helpers for MCP server tests."""

from __future__ import annotations

from itertools import count

import anyio

from openmcp import types
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext


_REQUEST_COUNTER = count(1)


class DummySession:
    """In-memory session used to capture server notifications."""

    def __init__(self, name: str = "session") -> None:
        self.name = name
        self.notifications: list[types.ServerNotification] = []

    async def send_notification(
        self,
        notification: types.ServerNotification,
        related_request_id: types.RequestId | None = None,
    ) -> None:  # pragma: no cover - exercised indirectly
        await anyio.lowlevel.checkpoint()
        self.notifications.append(notification)


class FailingSession(DummySession):
    """Session that raises when notified, used to test cleanup."""

    def __init__(self, name: str = "failing") -> None:
        super().__init__(name)
        self.failures = 0

    async def send_notification(
        self,
        notification: types.ServerNotification,
        related_request_id: types.RequestId | None = None,
    ) -> None:  # pragma: no cover - exercised indirectly
        self.failures += 1
        raise RuntimeError("notification failure")


class RecordingSession(DummySession):
    """Session used to capture log and progress traffic during tests."""

    def __init__(self, name: str = "recording") -> None:
        super().__init__(name)
        self.log_messages: list[tuple[str | None, dict[str, object], str | None]] = []
        self.progress_events: list[dict[str, object | None]] = []

    async def send_log_message(self, level, data, logger=None):
        await anyio.lowlevel.checkpoint()
        self.log_messages.append((level, dict(data), logger))

    async def send_progress_notification(
        self,
        progress_token,
        progress,
        *,
        total=None,
        message=None,
        related_request_id=None,
    ):
        await anyio.lowlevel.checkpoint()
        self.progress_events.append(
            {
                "token": progress_token,
                "progress": progress,
                "total": total,
                "message": message,
                "related_request_id": related_request_id,
            }
        )


async def run_with_context(session: DummySession, func, *args, meta=None):
    """Execute *func* with ``request_ctx`` bound to *session*."""
    ctx = RequestContext(
        request_id=next(_REQUEST_COUNTER),
        meta=meta,
        session=session,  # type: ignore[arg-type]
        lifespan_context={},
    )
    token = request_ctx.set(ctx)
    try:
        return await func(*args)
    finally:  # pragma: no cover - exercised indirectly
        request_ctx.reset(token)
