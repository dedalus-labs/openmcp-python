# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Shared ASGI transport primitives.

This module provides reusable building blocks for transports that expose an
``MCPServer`` over an ASGI-compatible surface.  Concrete subclasses supply the
session manager implementation and route configuration while this base class
handles lifecycle management, optional authorization wrapping, and startup of
the underlying ASGI server runtime.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable, Iterable  # noqa: TC003
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from starlette.applications import Starlette
from uvicorn import Config, Server

from .base import BaseTransport


if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send

    from ..app import MCPServer
    from ..authorization import AuthorizationManager


class SessionManagerProtocol(Protocol):
    """Minimal contract required of the reference SDK session managers."""

    async def handle_request(self, scope: Scope, receive: Receive, send: Send) -> None: ...

    def run(self) -> AbstractAsyncContextManager[None]: ...


@dataclass(slots=True)
class SessionManagerHandler:
    """ASGI adapter that connects the server session manager to the runtime."""

    session_manager: SessionManagerProtocol
    transport_label: str
    allowed_scopes: tuple[str, ...]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope_type = scope.get("type")
        if scope_type not in self.allowed_scopes:
            allowed = ", ".join(self.allowed_scopes)
            message = f"{self.transport_label} only handles ASGI scopes: {allowed} (got {scope_type!r})."
            raise TypeError(message)

        await self.session_manager.handle_request(scope, receive, send)

    def lifespan(self) -> Callable[[Starlette], AbstractAsyncContextManager[None]]:
        """Return an ASGI lifespan hook bound to the session manager."""

        @asynccontextmanager
        async def _lifespan(
            _app: Starlette,
        ) -> AsyncIterator[None]:  # pragma: no cover - exercised via integration tests
            async with self.session_manager.run():
                yield

        return _lifespan


class ASGITransportBase(BaseTransport, ABC):
    """Template for transports that present an :class:`MCPServer` via ASGI."""

    ALLOWED_SCOPES: tuple[str, ...] = ("http",)
    DEFAULT_HOST: str = "127.0.0.1"
    DEFAULT_PORT: int = 8000
    DEFAULT_PATH: str = "/mcp"
    DEFAULT_LOG_LEVEL: str = "info"

    def __init__(self, server: MCPServer, *, security_settings: object | None = None, stateless: bool = False) -> None:
        super().__init__(server)
        self._security_settings = security_settings
        self._stateless = stateless

    @property
    def security_settings(self) -> object | None:
        """Return the transport-specific security configuration, if any."""
        return self._security_settings

    @property
    def stateless(self) -> bool:
        """Return ``True`` when incoming requests should be treated statelessly."""
        return self._stateless

    async def run(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        path: str | None = None,
        log_level: str | None = None,
        **uvicorn_options: Any,
    ) -> None:
        host = host or self.DEFAULT_HOST
        port = port or self.DEFAULT_PORT
        path = path or self.DEFAULT_PATH
        log_level = log_level or self.DEFAULT_LOG_LEVEL

        await self._serve(host, port, path, log_level, uvicorn_options)

    async def _serve(self, host: str, port: int, path: str, log_level: str, uvicorn_options: dict[str, Any]) -> None:
        manager = self._build_session_manager()
        handler = self._build_handler(manager)
        routes = list(self._build_routes(path=path, handler=handler))

        authorization: AuthorizationManager | None = getattr(self.server, "authorization_manager", None)
        if authorization and authorization.enabled:
            routes.append(authorization.starlette_route())

        lifespan = handler.lifespan()
        asgi_app = Starlette(routes=routes, lifespan=lifespan)

        app = self._to_asgi(asgi_app)
        if authorization and authorization.enabled:
            app = authorization.wrap_asgi(app)

        config = Config(app=app, host=host, port=port, log_level=log_level, **uvicorn_options)
        server_instance = Server(config)
        await server_instance.serve()

    def _build_handler(self, manager: SessionManagerProtocol) -> SessionManagerHandler:
        """Construct the default ASGI handler for the provided session manager."""
        return SessionManagerHandler(
            session_manager=manager,
            transport_label=self.transport_display_name,
            allowed_scopes=self.ALLOWED_SCOPES,
        )

    def _to_asgi(self, app: Starlette) -> Starlette:
        """Allow subclasses to wrap the ASGI app before serving.

        For example, a transport could override this method to inject
        instrumentation middleware before handing control to the ASGI server
        runtime.
        """
        return app

    @abstractmethod
    def _build_session_manager(self) -> SessionManagerProtocol: ...

    @abstractmethod
    def _build_routes(self, *, path: str, handler: SessionManagerHandler) -> Iterable[object]: ...


__all__ = ["ASGITransportBase", "SessionManagerHandler"]
