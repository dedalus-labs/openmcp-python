"""High-level MCP client wrapper built on the reference SDK.

The implementation mirrors the behaviour described in:

* ``docs/mcp/core/understanding-mcp-clients/core-client-features.md``
* ``docs/mcp/core/cancellation/index.md``
* ``docs/mcp/core/transports/stdio.md`` and ``docs/mcp/core/transports/streamable-http.md``

`MCPClient` manages the initialization handshake, capability negotiation,
optional client-side features (sampling, elicitation, roots, logging), and
exposes convenience helpers for protocol operations.  It stays thin by
leveraging the official `ClientSession` class while providing ergonomic hooks
and safety checks for host applications.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, TypeVar

import anyio
from anyio import Lock
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

from .._sdk_loader import ensure_sdk_importable
from ..utils.coro import maybe_await_with_args

ensure_sdk_importable()

from mcp import types
from mcp.client.session import ClientSession

SamplingHandler = Callable[[Any, types.CreateMessageRequestParams], Awaitable[types.CreateMessageResult | types.ErrorData] | types.CreateMessageResult | types.ErrorData]
ElicitationHandler = Callable[[Any, types.ElicitRequestParams], Awaitable[types.ElicitResult | types.ErrorData] | types.ElicitResult | types.ErrorData]
LoggingHandler = Callable[[types.LoggingMessageNotificationParams], Awaitable[None] | None]

T_RequestResult = TypeVar("T_RequestResult")


@dataclass(slots=True)
class ClientCapabilitiesConfig:
    """Optional capability handlers for the client."""

    sampling: SamplingHandler | None = None
    elicitation: ElicitationHandler | None = None
    logging: LoggingHandler | None = None
    initial_roots: Iterable[types.Root | dict[str, Any]] | None = None
    enable_roots: bool = False


class MCPClient:
    """Lifecycle-aware wrapper around :class:`mcp.client.session.ClientSession`.

    Parameters correspond to the optional client features described in
    ``docs/mcp/core/understanding-mcp-clients/core-client-features.md``.  Hosts
    can provide handlers for sampling, elicitation, logging, and root discovery
    to negotiate those capabilities during initialization.

    """

    def __init__(
        self,
        read_stream: MemoryObjectReceiveStream[Any],
        write_stream: MemoryObjectSendStream[Any],
        *,
        capabilities: ClientCapabilitiesConfig | None = None,
        client_info: types.Implementation | None = None,
    ) -> None:
        self._read_stream = read_stream
        self._write_stream = write_stream
        self._client_info = client_info

        self._config = capabilities or ClientCapabilitiesConfig()
        self._supports_roots = self._config.enable_roots or self._config.initial_roots is not None

        initial_roots = list(self._config.initial_roots or []) if self._supports_roots else []
        self._root_lock = Lock()
        self._roots_version = 0
        self._roots: list[types.Root] = [self._normalise_root(root) for root in initial_roots]

        self._session: ClientSession | None = None
        self.initialize_result: types.InitializeResult | None = None

    # ---------------------------------------------------------------------
    # Async context manager
    # ---------------------------------------------------------------------

    async def __aenter__(self) -> "MCPClient":
        session = ClientSession(
            self._read_stream,
            self._write_stream,
            sampling_callback=self._build_sampling_handler(),
            elicitation_callback=self._build_elicitation_handler(),
            list_roots_callback=self._build_roots_handler(),
            logging_callback=self._build_logging_handler(),
            client_info=self._client_info,
        )

        self._session = await session.__aenter__()
        self.initialize_result = await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool | None:
        if self._session is None:
            return None
        try:
            return await self._session.__aexit__(exc_type, exc, tb)
        finally:
            self._session = None

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("Client session not started; use 'async with' before accessing it.")
        return self._session

    @property
    def supports_roots(self) -> bool:
        """Whether the client advertises the roots capability."""
        return self._supports_roots

    async def ping(self) -> types.EmptyResult:
        """Send ``ping`` to verify liveness (``docs/mcp/spec/schema-reference/ping.md``)."""
        return await self.send_request(types.ClientRequest(types.PingRequest()), types.EmptyResult)

    async def send_request(
        self,
        request: types.ClientRequest,
        result_type: type[T_RequestResult],
        *,
        progress_callback: Callable[[float, float | None, str | None], Awaitable[None] | None] | None = None,
    ) -> T_RequestResult:
        """Forward a request to the server and await the result."""
        return await self.session.send_request(
            request,
            result_type,
            progress_callback=progress_callback,
        )

    async def cancel_request(self, request_id: types.RequestId, *, reason: str | None = None) -> None:
        """Emit ``notifications/cancelled`` per ``docs/mcp/core/cancellation/index.md``."""
        params = types.CancelledNotificationParams(requestId=request_id, reason=reason)
        notification = types.ClientNotification(types.CancelledNotification(params=params))
        await self.session.send_notification(notification)

    async def update_roots(self, roots: Iterable[types.Root | dict[str, Any]], *, notify: bool = True) -> None:
        """Replace the advertised roots and optionally send ``roots/list_changed``.

        This fulfils the behaviour described in
        ``docs/mcp/core/understanding-mcp-clients/core-client-features.md``.

        """
        if not self._supports_roots:
            raise RuntimeError("Roots capability is not enabled for this client")

        normalised = [self._normalise_root(root) for root in roots]
        async with self._root_lock:
            self._roots_version += 1
            self._roots = normalised

        if notify and self._session is not None:
            await self._session.send_roots_list_changed()

    async def list_roots(self) -> list[types.Root]:
        """Return the current set of roots advertised to servers."""
        async with self._root_lock:
            return [root.model_copy(deep=True) for root in self._roots]

    def roots_version(self) -> int:
        return self._roots_version

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_sampling_handler(self) -> Callable[[Any, types.CreateMessageRequestParams], Awaitable[Any]] | None:
        handler = self._config.sampling
        if handler is None:
            return None

        async def wrapper(context: Any, params: types.CreateMessageRequestParams) -> Any:
            return await maybe_await_with_args(handler, context, params)

        return wrapper

    def _build_elicitation_handler(self) -> Callable[[Any, types.ElicitRequestParams], Awaitable[Any]] | None:
        handler = self._config.elicitation
        if handler is None:
            return None

        async def wrapper(context: Any, params: types.ElicitRequestParams) -> Any:
            return await maybe_await_with_args(handler, context, params)

        return wrapper

    def _build_logging_handler(self) -> Callable[[types.LoggingMessageNotificationParams], Awaitable[None]] | None:
        handler = self._config.logging
        if handler is None:
            return None

        async def wrapper(params: types.LoggingMessageNotificationParams) -> None:
            await maybe_await_with_args(handler, params)

        return wrapper

    def _build_roots_handler(self) -> Callable[[Any], Awaitable[types.ClientResult]] | None:
        if not self._supports_roots:
            return None

        async def list_roots_handler(_: Any) -> types.ListRootsResult:
            async with self._root_lock:
                roots_snapshot = [root.model_copy(deep=True) for root in self._roots]
            return types.ListRootsResult(roots=roots_snapshot)

        return list_roots_handler

    @staticmethod
    def _normalise_root(value: types.Root | dict[str, Any]) -> types.Root:
        if isinstance(value, types.Root):
            return value
        return types.Root.model_validate(value)


__all__ = ["MCPClient", "ClientCapabilitiesConfig"]
