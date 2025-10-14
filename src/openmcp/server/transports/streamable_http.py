"""Streamable HTTP transport adapter.

This mirrors the lifecycle described in ``docs/mcp/core/transports/streamable-http.md``
by using the reference SDK's :class:`StreamableHTTPSessionManager`.  The adapter keeps
the high-level :class:`~openmcp.server.app.MCPServer` decoupled from `uvicorn` and
`starlette`, while still fulfilling the spec's requirements for a single POST/GET
endpoint and SSE support.  Tests patch :meth:`StreamableHTTPTransport._run_server` to
run entirely in-memory.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ..._sdk_loader import ensure_sdk_importable
from .base import BaseTransport

ensure_sdk_importable()

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..app import MCPServer


class StreamableHTTPTransport(BaseTransport):
    """Serve an :class:`openmcp.server.app.MCPServer` over Streamable HTTP."""

    def __init__(
        self,
        server: "MCPServer",
        *,
        security_settings: "TransportSecuritySettings | None" = None,
    ) -> None:
        super().__init__(server)
        self._security_settings = security_settings

    async def run(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 3000,
        path: str = "/mcp",
        log_level: str = "info",
        **uvicorn_options: Any,
    ) -> None:
        """Start the transport.

        Parameters mirror the reference SDK's expectations and are passed through
        to Uvicorn.  The method delegates to :meth:`_run_server` so tests can
        substitute an in-memory implementation.
        """

        await self._run_server(
            host=host,
            port=port,
            path=path,
            log_level=log_level,
            uvicorn_options=uvicorn_options,
        )

    async def _run_server(
        self,
        *,
        host: str,
        port: int,
        path: str,
        log_level: str,
        uvicorn_options: dict[str, Any],
    ) -> None:
        try:
            from starlette.applications import Starlette
            from starlette.routing import Route
            from starlette.types import Receive, Scope, Send
            from uvicorn import Config, Server
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "Streamable HTTP transport requires 'starlette' and 'uvicorn'."
            ) from exc

        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from mcp.server.transport_security import TransportSecuritySettings

        security = self._security_settings
        if security is not None and not isinstance(security, TransportSecuritySettings):
            security = TransportSecuritySettings.model_validate(security)

        manager = StreamableHTTPSessionManager(self.server, security_settings=security)

        class StreamableHTTPApp:
            def __init__(self, session_manager: StreamableHTTPSessionManager) -> None:
                self._session_manager = session_manager

            async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
                await self._session_manager.handle_request(scope, receive, send)

        async def lifespan(app):  # pragma: no cover - exercised via integration tests
            async with manager.run():
                yield

        route = Route(path, StreamableHTTPApp(manager))
        starlette_app = Starlette(routes=[route], lifespan=lifespan)

        config = Config(
            app=starlette_app,
            host=host,
            port=port,
            log_level=log_level,
            **uvicorn_options,
        )
        server = Server(config)
        await server.serve()
