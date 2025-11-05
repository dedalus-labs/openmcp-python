# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Roots capability support for MCP servers.

Implements the roots capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/client/roots
  (client-advertised filesystem roots with list-changed notifications)
- https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination
  (cursor-based pagination for roots/list)

Implements cache-aside pattern where each session maintains immutable snapshots
of client-advertised roots alongside RootGuard reference monitor for filesystem
access validation. Supports debounced refresh on list-changed notifications with
version-stable pagination cursors across snapshot updates.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlparse
import weakref

import json


if os.name == "nt":  # pragma: no cover - Windows specific
    from urllib.request import url2pathname

from mcp import types
from mcp.shared.exceptions import McpError


if TYPE_CHECKING:
    from mcp.server.session import ServerSession

Snapshot = tuple[types.Root, ...]


@dataclass(frozen=True)
class _CacheEntry:
    version: int
    snapshot: Snapshot
    guard: RootGuard


class RootGuard:
    """Reference monitor ensuring paths stay within allowed roots."""

    def __init__(self, roots: Snapshot) -> None:
        self._paths = tuple(self._canonicalize(root.uri) for root in roots)

    def within(self, candidate: Path | str) -> bool:
        if not self._paths:
            return False
        path = self._canonicalize(candidate)
        return any(path == root or root in path.parents for root in self._paths)

    @staticmethod
    def _canonicalize(value: Path | str) -> Path:
        if isinstance(value, Path):
            path = value
        else:
            value_str = str(value)
            parsed = urlparse(value_str)
            if parsed.scheme == "file":
                netloc = parsed.netloc
                raw_path = unquote(parsed.path or "/")

                if os.name == "nt":  # pragma: no cover - Windows specific
                    target = raw_path
                    if netloc and netloc.lower() != "localhost":
                        target = f"//{netloc}{raw_path}"
                    path = Path(url2pathname(target))
                else:
                    if not raw_path.startswith("/"):
                        raw_path = f"/{raw_path}"
                    if netloc and netloc.lower() != "localhost":
                        raw_path = f"/{netloc}{raw_path}"
                    path = Path(raw_path)
            else:
                path = Path(value_str)
        resolved = path.expanduser()
        try:
            resolved = resolved.resolve(strict=False)
        except RuntimeError:  # pragma: no cover - defensive (Windows path resolution quirks)
            pass
        if os.name == "nt":  # pragma: no cover - Windows specific normalization
            resolved = Path(os.path.normcase(str(resolved)))
        return resolved


def _finalize_session(
    service_ref: weakref.ReferenceType[RootsService],
    loop: asyncio.AbstractEventLoop,
    session_ref: weakref.ReferenceType[ServerSession],
) -> None:
    service = service_ref()
    session = session_ref()
    if service is None or session is None:
        return
    if loop.is_closed():  # pragma: no cover - shutdown race
        return
    try:
        loop.call_soon_threadsafe(service.remove, session)
    except RuntimeError:  # pragma: no cover - loop already shutting down
        pass


class RootsService:
    """Manages per-session root snapshots and guards."""

    def __init__(
        self,
        rpc_call: Callable[[ServerSession, Mapping[str, Any] | None], Awaitable[Mapping[str, Any]]],
        *,
        debounce_delay: float = 0.25,
    ) -> None:
        self._rpc_list = rpc_call
        self._debounce_delay = debounce_delay
        self._entries: weakref.WeakKeyDictionary[ServerSession, _CacheEntry] = weakref.WeakKeyDictionary()
        self._debouncers: weakref.WeakKeyDictionary[ServerSession, asyncio.Task] = weakref.WeakKeyDictionary()
        self._finalizers: weakref.WeakKeyDictionary[ServerSession, Any] = weakref.WeakKeyDictionary()

    def guard(self, session: ServerSession) -> RootGuard:
        entry = self._entries.get(session)
        return entry.guard if entry else RootGuard(())

    def snapshot(self, session: ServerSession) -> Snapshot:
        entry = self._entries.get(session)
        return entry.snapshot if entry else ()

    def version(self, session: ServerSession) -> int:
        entry = self._entries.get(session)
        return entry.version if entry else 0

    async def on_session_open(self, session: ServerSession) -> Snapshot:
        snapshot = await self.refresh(session)
        if session not in self._finalizers:
            loop = asyncio.get_running_loop()
            self_ref: weakref.ReferenceType[RootsService] = weakref.ref(self)
            session_ref: weakref.ReferenceType[ServerSession] = weakref.ref(session)
            finalizer = weakref.finalize(session, _finalize_session, self_ref, loop, session_ref)
            self._finalizers[session] = finalizer
        return snapshot

    async def on_list_changed(self, session: ServerSession) -> None:
        if task := self._debouncers.get(session):
            task.cancel()

        async def _run() -> None:
            try:
                await asyncio.sleep(self._debounce_delay)
                await self.refresh(session)
            except asyncio.CancelledError:  # pragma: no cover - debounce cancellation expected
                pass

        self._debouncers[session] = asyncio.create_task(_run())

    async def refresh(self, session: ServerSession) -> Snapshot:
        previous = self._entries.get(session)
        snapshot = await self._fetch_snapshot(session)

        if previous and previous.snapshot == snapshot:
            return previous.snapshot

        version = previous.version + 1 if previous else 1
        self._entries[session] = _CacheEntry(version=version, snapshot=snapshot, guard=RootGuard(snapshot))
        return snapshot

    def remove(self, session: ServerSession) -> None:
        if finalizer := self._finalizers.pop(session, None):
            finalizer.detach()

        task = self._debouncers.get(session)
        if task:
            task.cancel()
            try:
                del self._debouncers[session]
            except KeyError:  # pragma: no cover - defensive cleanup
                pass
        try:
            del self._entries[session]
        except KeyError:  # pragma: no cover - defensive cleanup
            pass

    def encode_cursor(self, session: ServerSession, offset: int) -> str:
        entry = self._entries.get(session)
        version = entry.version if entry else 0
        payload = json.dumps({"v": version, "o": offset}, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(payload).decode()

    def decode_cursor(self, session: ServerSession, cursor: str | None) -> tuple[int, int]:
        entry = self._entries.get(session)
        expected_version = entry.version if entry else 0
        if not cursor:
            return expected_version, 0

        try:
            raw = base64.urlsafe_b64decode(cursor.encode())
            parsed = json.loads(raw.decode())
            version = int(parsed["v"])
            offset = int(parsed["o"])
        except Exception as exc:  # pragma: no cover - defensive
            raise McpError(
                types.ErrorData(code=types.INVALID_PARAMS, message="Invalid cursor for roots/list", data=str(exc))
            ) from exc

        if version != expected_version:
            raise McpError(
                types.ErrorData(
                    code=types.INVALID_PARAMS,
                    message="Stale cursor for roots/list; please restart pagination",
                    data={"expected": expected_version, "received": version},
                )
            )

        if offset < 0:
            raise McpError(
                types.ErrorData(code=types.INVALID_PARAMS, message="Cursor offset must be non-negative", data=offset)
            )

        return version, offset

    async def _fetch_snapshot(self, session: ServerSession) -> Snapshot:
        roots: list[types.Root] = []
        cursor: str | None = None

        while True:
            params = {"cursor": cursor} if cursor else None
            result = await self._rpc_list(session, params)

            payload = result.get("roots")
            if payload is None:
                raise McpError(types.ErrorData(code=types.INTERNAL_ERROR, message="Client response missing 'roots'"))

            roots.extend(types.Root.model_validate(root) for root in payload)
            cursor = result.get("nextCursor")
            if not cursor:
                break

        dedup: dict[str, types.Root] = {}
        for root in roots:
            dedup[root.uri] = root

        return tuple(sorted(dedup.values(), key=lambda r: r.uri))


__all__ = ["RootsService", "RootGuard"]
