# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Streamable HTTP auth enforcement tests."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette

from openmcp import MCPServer, tool
from openmcp.server.authorization import AuthorizationConfig, AuthorizationContext, AuthorizationError, AuthorizationProvider
from openmcp.server.transports import StreamableHTTPTransport


class DummyProvider(AuthorizationProvider):
    def __init__(self, expected_token: str = "valid") -> None:
        self.expected_token = expected_token

    async def validate(self, token: str) -> AuthorizationContext:
        if token != self.expected_token:
            raise AuthorizationError("invalid token")
        return AuthorizationContext(subject="demo", scopes=["mcp:tools:call"], claims={"ddls:connections": []})


@pytest.fixture
async def server() -> MCPServer:
    srv = MCPServer(
        "auth-demo",
        authorization=AuthorizationConfig(enabled=True),
    )

    with srv.binding():
        @tool(description="Ping")
        async def ping() -> str:
            return "pong"

    srv.set_authorization_provider(DummyProvider())
    yield srv


def build_asgi_app(transport: StreamableHTTPTransport) -> tuple[Starlette, callable]:
    manager = transport._build_session_manager()
    handler = transport._build_handler(manager)
    routes = list(transport._build_routes(path="/mcp", handler=handler))

    authorization = transport.server.authorization_manager
    if authorization and authorization.enabled:
        routes.append(authorization.starlette_route())

    base_app = Starlette(routes=routes, lifespan=handler.lifespan())
    if authorization and authorization.enabled:
        wrapped = authorization.wrap_asgi(base_app)
    else:
        wrapped = base_app
    return wrapped, base_app.router.lifespan_context(base_app)


@pytest.mark.anyio
async def test_missing_bearer_is_rejected(server: MCPServer) -> None:
    transport = StreamableHTTPTransport(server)
    app, lifespan = build_asgi_app(transport)

    async with lifespan:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert resp.status_code == 401
        assert resp.headers["www-authenticate"].startswith("Bearer")
        assert resp.json()["error"] == "unauthorized"


@pytest.mark.anyio
async def test_valid_bearer_allows_request(server: MCPServer) -> None:
    transport = StreamableHTTPTransport(server)
    app, lifespan = build_asgi_app(transport)

    async with lifespan:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            headers = {
                "Authorization": "Bearer valid",
                "Accept": "application/json, text/event-stream",
            }

            resp = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "clientInfo": {"name": "test", "version": "1.0"},
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                    },
                },
                headers=headers,
            )
            assert resp.status_code == 200
