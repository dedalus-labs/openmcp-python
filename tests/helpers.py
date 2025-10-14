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


async def run_with_context(session: DummySession, func, *args):
    """Execute *func* with ``request_ctx`` bound to *session*."""

    ctx = RequestContext(
        request_id=next(_REQUEST_COUNTER),
        meta=None,
        session=session,  # type: ignore[arg-type]
        lifespan_context={},
    )
    token = request_ctx.set(ctx)
    try:
        return await func(*args)
    finally:  # pragma: no cover - exercised indirectly
        request_ctx.reset(token)
