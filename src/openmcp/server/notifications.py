"""Utilities for tracking observers and broadcasting notifications."""

from __future__ import annotations

import weakref
from typing import Any, Protocol, TYPE_CHECKING

import anyio

from mcp.server.lowlevel.server import request_ctx

if TYPE_CHECKING:  # pragma: no cover - typing helpers
    from .. import types


class NotificationSink(Protocol):
    """Abstract destination for server-initiated notifications."""

    async def send_notification(
        self,
        session: Any,
        notification: "types.ServerNotification",
    ) -> None:
        ...


class DefaultNotificationSink:
    """Fallback sink that sends notifications directly via the session object."""

    async def send_notification(
        self,
        session: Any,
        notification: "types.ServerNotification",
    ) -> None:
        await session.send_notification(notification)


class ObserverRegistry:
    """Tracks sessions interested in list change notifications."""

    def __init__(self, sink: NotificationSink) -> None:
        self._observers: weakref.WeakSet[Any] = weakref.WeakSet()
        self._sink = sink

    def remember_current_session(self) -> None:
        try:
            context = request_ctx.get()
        except LookupError:  # pragma: no cover - no active request
            return
        self._observers.add(context.session)

    async def broadcast(self, notification, logger) -> None:
        if not self._observers:
            return

        stale: list[Any] = []
        for session in list(self._observers):
            try:
                await self._sink.send_notification(session, notification)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(
                    "Failed to notify observer %s: %s",
                    getattr(session, "name", repr(session)),
                    exc,
                )
                stale.append(session)
                await anyio.lowlevel.checkpoint()

        for session in stale:
            self._observers.discard(session)

    def clear(self) -> None:
        self._observers.clear()
