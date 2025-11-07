# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Shared test helpers for MCP server tests."""

from __future__ import annotations

from itertools import count
from types import SimpleNamespace

import anyio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from openmcp import types


_REQUEST_COUNTER = count(1)


class DummySession:
    """In-memory session used to capture server notifications."""

    def __init__(self, name: str = "session") -> None:
        self.name = name
        self.notifications: list[types.ServerNotification] = []

    async def send_notification(
        self, notification: types.ServerNotification, related_request_id: types.RequestId | None = None
    ) -> None:
        await anyio.lowlevel.checkpoint()
        self.notifications.append(notification)


class FailingSession(DummySession):
    """Session that raises when notified, used to test cleanup."""

    def __init__(self, name: str = "failing") -> None:
        super().__init__(name)
        self.failures = 0

    async def send_notification(
        self, notification: types.ServerNotification, related_request_id: types.RequestId | None = None
    ) -> None:
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
        self, progress_token, progress, *, total=None, message=None, related_request_id=None
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


async def run_with_context(
    session: DummySession,
    func,
    *args,
    meta=None,
    request_scope: dict[str, object] | None = None,
    lifespan_context: dict[str, object] | None = None,
):
    """Execute *func* with ``request_ctx`` bound to *session*."""
    ctx = RequestContext(
        request_id=next(_REQUEST_COUNTER),
        meta=meta,
        session=session,  # type: ignore[arg-type]
        lifespan_context=lifespan_context or {},
        request=SimpleNamespace(scope=request_scope) if request_scope is not None else None,
    )
    token = request_ctx.set(ctx)
    try:
        return await func(*args)
    finally:
        request_ctx.reset(token)
