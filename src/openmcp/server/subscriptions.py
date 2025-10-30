# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Subscription management for resource updates."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import contextlib
from typing import Any
import weakref

import anyio
from mcp.server.lowlevel.server import request_ctx


class SubscriptionManager:
    """Tracks resource subscriptions per URI and per session."""

    def __init__(self) -> None:
        self._lock = anyio.Lock()
        self._by_uri: dict[str, weakref.WeakSet[Any]] = defaultdict(weakref.WeakSet)
        self._by_session: weakref.WeakKeyDictionary[Any, set[str]] = weakref.WeakKeyDictionary()

    async def subscribe_current(self, uri: str) -> None:
        context = _require_context()
        async with self._lock:
            subscribers = self._by_uri[uri]
            subscribers.add(context.session)
            uris = self._by_session.setdefault(context.session, set())
            uris.add(uri)

    async def unsubscribe_current(self, uri: str) -> None:
        context = _require_context()
        async with self._lock:
            subscribers = self._by_uri.get(uri)
            if subscribers is not None:
                subscribers.discard(context.session)
                if not subscribers:
                    self._by_uri.pop(uri, None)

            uris = self._by_session.get(context.session)
            if uris is not None:
                uris.discard(uri)
                if not uris:
                    with contextlib.suppress(KeyError):
                        del self._by_session[context.session]

    async def prune_session(self, session: Any) -> None:
        async with self._lock:
            uris = self._by_session.pop(session, None)
            if not uris:
                return
            for uri in uris:
                subscribers = self._by_uri.get(uri)
                if subscribers is not None:
                    subscribers.discard(session)
                    if not subscribers:
                        self._by_uri.pop(uri, None)

    async def subscribers(self, uri: str) -> Iterable[Any]:
        async with self._lock:
            subscribers = self._by_uri.get(uri)
            if not subscribers:
                return []
            return list(subscribers)

    async def snapshot(self) -> tuple[dict[str, list[Any]], dict[Any, set[str]]]:
        """Return shallow copies for debugging/testing."""
        async with self._lock:
            by_uri = {uri: list(sessions) for uri, sessions in self._by_uri.items()}
            by_session = {session: set(uris) for session, uris in self._by_session.items()}
        return by_uri, by_session


def _require_context():
    try:
        return request_ctx.get()
    except LookupError as exc:  # pragma: no cover - invalid usage
        err_msg = "Subscription operations require an active request context."
        raise RuntimeError(err_msg) from exc
