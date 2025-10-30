# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import pytest


starlette = pytest.importorskip("starlette")
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from openmcp.server.authorization import (
    AuthorizationConfig,
    AuthorizationContext,
    AuthorizationError,
    AuthorizationManager,
)


@pytest.fixture
def metadata_manager() -> AuthorizationManager:
    config = AuthorizationConfig(enabled=True, authorization_servers=["https://as.example"], cache_ttl=123)
    return AuthorizationManager(config)


def test_metadata_route_serves_prm(metadata_manager: AuthorizationManager) -> None:
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)
    resp = client.get(metadata_manager.config.metadata_path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["authorization_servers"] == ["https://as.example"]
    assert data["resource"].startswith("http://testserver")
    assert resp.headers["cache-control"] == "public, max-age=123"


def test_middleware_blocks_requests_without_token(metadata_manager: AuthorizationManager) -> None:
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.post("/mcp")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_middleware_accepts_valid_token(metadata_manager: AuthorizationManager) -> None:
    class DummyProvider:
        async def validate(self, token: str) -> AuthorizationContext:
            if token != "good-token":
                raise AuthorizationError("unexpected token")
            return AuthorizationContext(subject="user", scopes=["mcp:read"], claims={})

    metadata_manager.set_provider(DummyProvider())

    async def endpoint(request):
        ctx = request.scope.get("openmcp.auth")
        return JSONResponse({"subject": ctx.subject})

    routes = [Route("/mcp", endpoint, methods=["GET"]), metadata_manager.starlette_route()]
    app = Starlette(routes=routes)
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    assert resp.json()["subject"] == "user"


def test_fail_open_allows_request(metadata_manager: AuthorizationManager) -> None:
    metadata_manager.config.fail_open = True

    class FailingProvider:
        async def validate(self, token: str) -> AuthorizationContext:
            raise AuthorizationError("boom")

    metadata_manager.set_provider(FailingProvider())

    async def endpoint(request):
        return JSONResponse({"auth": request.scope.get("openmcp.auth")})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer bad"})
    assert resp.status_code == 200
    assert resp.json()["auth"] is None
