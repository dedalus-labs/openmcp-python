"""Streamable HTTP transport adapter.

This mirrors the lifecycle described in ``docs/mcp/core/transports/streamable-http.md``
by using the reference SDK's :class:`StreamableHTTPSessionManager`.  The adapter keeps
the high-level :class:`~openmcp.server.app.MCPServer` decoupled from `uvicorn` and
`starlette`, while still fulfilling the spec's requirements for a single POST/GET
endpoint and SSE support.  Tests patch :meth:`StreamableHTTPTransport._run_server` to
run entirely in-memory.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..._sdk_loader import ensure_sdk_importable
from ...versioning import SUPPORTED_PROTOCOL_VERSIONS
from .base import BaseTransport

ensure_sdk_importable()

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..app import MCPServer
    from ..authorization import AuthorizationManager


class StreamableHTTPTransport(BaseTransport):
    """Serve an :class:`openmcp.server.app.MCPServer` over Streamable HTTP."""

    def __init__(self, server: "MCPServer", *, security_settings: "TransportSecuritySettings | None" = None) -> None:
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

        await self._run_server(host=host, port=port, path=path, log_level=log_level, uvicorn_options=uvicorn_options)

    async def _run_server(
        self, *, host: str, port: int, path: str, log_level: str, uvicorn_options: dict[str, Any]
    ) -> None:
        try:
            from starlette.applications import Starlette
            from starlette.requests import Request
            from starlette.responses import Response
            from starlette.routing import Route
            from starlette.types import Message, Receive, Scope, Send
            from uvicorn import Config, Server
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("Streamable HTTP transport requires 'starlette' and 'uvicorn'.") from exc

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
                request = Request(scope, receive)

                # Read body once so we can validate headers before forwarding to the
                # Streamable HTTP manager, then replay it for the downstream handler.
                body_bytes = b""
                if request.method in {"POST", "PUT", "PATCH"}:
                    body_bytes = await request.body()

                error = _validate_transport_headers(request, body_bytes)
                if error is not None:
                    response = Response(error, status_code=400)
                    await response(scope, receive, send)
                    return

                receive_callable: Receive
                if body_bytes:
                    receive_callable = _replay_body(body_bytes, receive)
                else:
                    receive_callable = receive

                await self._session_manager.handle_request(scope, receive_callable, send)

        async def lifespan(app):  # pragma: no cover - exercised via integration tests
            async with manager.run():
                yield

        authorization: AuthorizationManager | None = getattr(self.server, "authorization_manager", None)

        routes = [Route(path, StreamableHTTPApp(manager))]
        if authorization and authorization.enabled:
            routes.append(authorization.starlette_route())

        starlette_app = Starlette(routes=routes, lifespan=lifespan)

        app_asgi: Any = starlette_app
        if authorization and authorization.enabled:
            app_asgi = authorization.wrap_asgi(starlette_app)

        config = Config(app=app_asgi, host=host, port=port, log_level=log_level, **uvicorn_options)
        server = Server(config)
        await server.serve()


def _validate_transport_headers(request, body: bytes) -> str | None:
    """Validate MCP HTTP headers according to docs/mcp/core/transports/streamable-http.md."""

    version = request.headers.get("MCP-Protocol-Version")
    if not version:
        return "Bad Request: Missing MCP-Protocol-Version header"

    if version not in SUPPORTED_PROTOCOL_VERSIONS:
        return f"Bad Request: Unsupported MCP-Protocol-Version '{version}'"

    session_id = request.headers.get("Mcp-Session-Id")
    if session_id is None and not _is_initialize_request(body):
        return "Bad Request: Missing Mcp-Session-Id header"

    return None


def _is_initialize_request(body: bytes) -> bool:
    if not body:
        return False
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("method") == "initialize"


def _replay_body(body: bytes, original_receive: Receive) -> Receive:
    """Return a receive callable that replays *body* once before delegating."""

    body_sent = False

    async def receive_wrapper() -> Message:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await original_receive()

    return receive_wrapper
