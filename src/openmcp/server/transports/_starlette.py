# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Shared Starlette transport primitives."""

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
    """Protocol for the base session manager surface."""

    async def handle_request(self, scope: Scope, receive: Receive, send: Send) -> None: ...

    def run(self) -> AbstractAsyncContextManager[None]: ...


@dataclass(slots=True)
class SessionManagerHandler:
    """ASGI adapter that connects Starlette to a session manager."""

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
        """Return a Starlette lifespan hook bound to the session manager."""

        @asynccontextmanager
        async def _lifespan(
            _app: Starlette,
        ) -> AsyncIterator[None]:  # pragma: no cover - exercised via integration tests
            async with self.session_manager.run():
                yield

        return _lifespan


class StarletteTransportBase(BaseTransport, ABC):
    """Abstract base for transports hosted on Starlette."""

    ALLOWED_SCOPES: tuple[str, ...] = ("http",)
    DEFAULT_HOST = "127.0.0.1"
    DEFAULT_PORT = 8000
    DEFAULT_PATH = "/mcp"
    DEFAULT_LOG_LEVEL = "info"

    def __init__(self, server: MCPServer, *, security_settings: object | None = None, stateless: bool = False) -> None:
        super().__init__(server)
        self._security_settings = security_settings
        self._stateless = stateless

    @property
    def security_settings(self) -> object | None:
        return self._security_settings

    @property
    def stateless(self) -> bool:
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
        server = Starlette(routes=routes, lifespan=lifespan)

        app = self._to_asgi(server)
        if authorization and authorization.enabled:
            app = authorization.wrap_asgi(app)

        config = Config(app=app, host=host, port=port, log_level=log_level, **uvicorn_options)
        server = Server(config)
        await server.serve()

    def _build_handler(self, manager: SessionManagerProtocol) -> SessionManagerHandler:
        return SessionManagerHandler(
            session_manager=manager, transport_label=self.transport_display_name, allowed_scopes=self.ALLOWED_SCOPES
        )

    def _to_asgi(self, app: Starlette) -> Starlette:
        return app

    @abstractmethod
    def _build_session_manager(self) -> SessionManagerProtocol: ...

    @abstractmethod
    def _build_routes(self, *, path: str, handler: SessionManagerHandler) -> Iterable[object]: ...


__all__ = ["SessionManagerHandler", "StarletteTransportBase"]
