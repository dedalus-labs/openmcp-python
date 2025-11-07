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
def auth_config() -> AuthorizationConfig:
    return AuthorizationConfig(
        enabled=True,
        authorization_servers=["https://as.example"],
        required_scopes=["mcp:read", "mcp:write"],
        cache_ttl=123,
    )


@pytest.fixture
def metadata_manager(auth_config: AuthorizationConfig) -> AuthorizationManager:
    return AuthorizationManager(auth_config)


@pytest.fixture
def dummy_provider():
    class DummyProvider:
        async def validate(self, token: str) -> AuthorizationContext:
            if token == "good-token":
                return AuthorizationContext(subject="user", scopes=["mcp:read"], claims={})
            raise AuthorizationError("invalid token")

    return DummyProvider()


# ==============================================================================
# Protected Resource Metadata (PRM) Endpoint Tests
# ==============================================================================


def test_metadata_route_serves_prm(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint serves correct JSON with required fields."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)
    resp = client.get(metadata_manager.config.metadata_path)
    assert resp.status_code == 200
    data = resp.json()
    assert data["authorization_servers"] == ["https://as.example"]
    assert data["resource"].startswith("http://testserver")
    assert resp.headers["cache-control"] == "public, max-age=123"


def test_prm_includes_required_fields(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint includes resource and authorization_servers fields."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert "resource" in data
    assert "authorization_servers" in data
    assert isinstance(data["resource"], str)
    assert isinstance(data["authorization_servers"], list)


def test_prm_includes_scopes_supported(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint includes scopes_supported field."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    assert "scopes_supported" in data
    assert data["scopes_supported"] == ["mcp:read", "mcp:write"]


def test_prm_cache_control_header(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint includes Cache-Control header with configured TTL."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    assert "cache-control" in resp.headers
    assert resp.headers["cache-control"] == "public, max-age=123"


def test_prm_only_accepts_get(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint rejects POST, PUT, DELETE methods."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)

    # GET should work
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200

    # Other methods should fail
    resp = client.post("/.well-known/oauth-protected-resource")
    assert resp.status_code == 405

    resp = client.put("/.well-known/oauth-protected-resource")
    assert resp.status_code == 405

    resp = client.delete("/.well-known/oauth-protected-resource")
    assert resp.status_code == 405


def test_prm_respects_x_forwarded_headers(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint uses X-Forwarded-Proto and X-Forwarded-Host if present."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)

    # Test with X-Forwarded headers
    resp = client.get(
        "/.well-known/oauth-protected-resource",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "api.example.com",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["resource"] == "https://api.example.com"


def test_prm_falls_back_to_request_url(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint falls back to request URL if no forwarded headers."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)

    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    data = resp.json()
    # Should use testserver from TestClient
    assert data["resource"].startswith("http://testserver")


def test_prm_uses_host_header(metadata_manager: AuthorizationManager) -> None:
    """PRM endpoint uses Host header when provided."""
    app = Starlette(routes=[metadata_manager.starlette_route()])
    client = TestClient(app)

    resp = client.get(
        "/.well-known/oauth-protected-resource",
        headers={"Host": "custom.example.com"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should use Host header
    assert "custom.example.com" in data["resource"]


# ==============================================================================
# Bearer Token Middleware Tests
# ==============================================================================


def test_middleware_blocks_requests_without_token(metadata_manager: AuthorizationManager) -> None:
    """Middleware returns 401 when Authorization header is missing."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.post("/mcp")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_middleware_accepts_valid_token(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware accepts valid Bearer token and stores context in scope."""
    metadata_manager.set_provider(dummy_provider)

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


def test_middleware_rejects_invalid_token(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware returns 401 for invalid Bearer token."""
    metadata_manager.set_provider(dummy_provider)

    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer bad-token"})
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers


def test_middleware_www_authenticate_header_format(metadata_manager: AuthorizationManager) -> None:
    """Middleware returns properly formatted WWW-Authenticate header."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp")
    assert resp.status_code == 401
    www_auth = resp.headers["WWW-Authenticate"]
    assert www_auth.startswith("Bearer")
    assert 'error="invalid_token"' in www_auth
    assert "authorization_uri=" in www_auth


def test_middleware_stores_auth_context_in_scope(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware stores AuthorizationContext in request.scope['openmcp.auth']."""
    metadata_manager.set_provider(dummy_provider)

    async def endpoint(request):
        ctx = request.scope.get("openmcp.auth")
        return JSONResponse(
            {
                "subject": ctx.subject,
                "scopes": ctx.scopes,
                "claims": ctx.claims,
            }
        )

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer good-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject"] == "user"
    assert data["scopes"] == ["mcp:read"]
    assert data["claims"] == {}


def test_middleware_bypasses_prm_endpoint(metadata_manager: AuthorizationManager) -> None:
    """Middleware allows unauthenticated access to PRM endpoint."""
    routes = [metadata_manager.starlette_route()]
    app = Starlette(routes=routes)
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    # PRM endpoint should work without Authorization header
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200


# ==============================================================================
# Edge Cases: Authorization Header Parsing
# ==============================================================================


def test_malformed_authorization_header_missing_scheme(metadata_manager: AuthorizationManager) -> None:
    """Middleware rejects Authorization header without 'Bearer' scheme."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "just-a-token"})
    assert resp.status_code == 401


def test_bearer_case_insensitivity(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware accepts 'bearer' in lowercase."""
    metadata_manager.set_provider(dummy_provider)

    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    # Test lowercase 'bearer'
    resp = client.get("/mcp", headers={"Authorization": "bearer good-token"})
    assert resp.status_code == 200

    # Test mixed case
    resp = client.get("/mcp", headers={"Authorization": "BeArEr good-token"})
    assert resp.status_code == 200


def test_token_with_whitespace(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware strips whitespace from token."""
    metadata_manager.set_provider(dummy_provider)

    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    # Token with extra whitespace should be stripped
    resp = client.get("/mcp", headers={"Authorization": "Bearer   good-token   "})
    assert resp.status_code == 200


def test_empty_authorization_header(metadata_manager: AuthorizationManager) -> None:
    """Middleware rejects empty Authorization header."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": ""})
    assert resp.status_code == 401


def test_bearer_without_token(metadata_manager: AuthorizationManager) -> None:
    """Middleware rejects 'Bearer' without token."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer"})
    assert resp.status_code == 401

    resp = client.get("/mcp", headers={"Authorization": "Bearer "})
    assert resp.status_code == 401


# ==============================================================================
# Authorization Manager Tests
# ==============================================================================


def test_manager_enabled_property(auth_config: AuthorizationConfig) -> None:
    """AuthorizationManager.enabled reflects config."""
    manager = AuthorizationManager(auth_config)
    assert manager.enabled is True

    auth_config.enabled = False
    assert manager.enabled is False


def test_manager_disabled_state() -> None:
    """AuthorizationManager with disabled config."""
    config = AuthorizationConfig(enabled=False)
    manager = AuthorizationManager(config)
    assert manager.enabled is False


def test_manager_get_required_scopes(auth_config: AuthorizationConfig) -> None:
    """AuthorizationManager.get_required_scopes() returns configured scopes."""
    manager = AuthorizationManager(auth_config)
    scopes = manager.get_required_scopes()
    assert scopes == ["mcp:read", "mcp:write"]
    # Ensure it returns a copy, not the original list
    scopes.append("extra")
    assert manager.get_required_scopes() == ["mcp:read", "mcp:write"]


def test_fail_open_allows_request(metadata_manager: AuthorizationManager) -> None:
    """Fail-open mode allows request when validation fails."""
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


def test_fail_closed_rejects_request(metadata_manager: AuthorizationManager) -> None:
    """Fail-closed mode (default) rejects request when validation fails."""
    metadata_manager.config.fail_open = False

    class FailingProvider:
        async def validate(self, token: str) -> AuthorizationContext:
            raise AuthorizationError("validation failed")

    metadata_manager.set_provider(FailingProvider())

    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer bad"})
    assert resp.status_code == 401


def test_provider_delegation(metadata_manager: AuthorizationManager) -> None:
    """AuthorizationManager delegates validation to provider."""

    class CustomProvider:
        async def validate(self, token: str) -> AuthorizationContext:
            return AuthorizationContext(
                subject=f"user-{token}",
                scopes=["custom:scope"],
                claims={"custom": "claim"},
            )

    metadata_manager.set_provider(CustomProvider())

    async def endpoint(request):
        ctx = request.scope.get("openmcp.auth")
        return JSONResponse({"subject": ctx.subject, "scopes": ctx.scopes})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer token123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["subject"] == "user-token123"
    assert data["scopes"] == ["custom:scope"]


def test_noop_provider_raises_error() -> None:
    """Default noop provider raises AuthorizationError."""
    config = AuthorizationConfig(enabled=True)
    manager = AuthorizationManager(config)

    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp", headers={"Authorization": "Bearer token"})
    assert resp.status_code == 401
    data = resp.json()
    assert "authorization provider not configured" in data["detail"]


# ==============================================================================
# Configuration Tests
# ==============================================================================


def test_config_defaults() -> None:
    """AuthorizationConfig has sensible defaults."""
    config = AuthorizationConfig()
    assert config.enabled is False
    assert config.metadata_path == "/.well-known/oauth-protected-resource"
    assert config.authorization_servers == ["https://as.dedaluslabs.ai"]
    assert config.required_scopes == []
    assert config.cache_ttl == 300
    assert config.fail_open is False


def test_config_custom_values() -> None:
    """AuthorizationConfig accepts custom values."""
    config = AuthorizationConfig(
        enabled=True,
        metadata_path="/custom/path",
        authorization_servers=["https://auth.example.com", "https://auth2.example.com"],
        required_scopes=["read", "write", "admin"],
        cache_ttl=600,
        fail_open=True,
    )
    assert config.enabled is True
    assert config.metadata_path == "/custom/path"
    assert config.authorization_servers == ["https://auth.example.com", "https://auth2.example.com"]
    assert config.required_scopes == ["read", "write", "admin"]
    assert config.cache_ttl == 600
    assert config.fail_open is True


def test_custom_metadata_path() -> None:
    """Manager respects custom metadata path in config."""
    config = AuthorizationConfig(enabled=True, metadata_path="/custom/metadata")
    manager = AuthorizationManager(config)

    app = Starlette(routes=[manager.starlette_route()])
    client = TestClient(app)

    # Custom path should work
    resp = client.get("/custom/metadata")
    assert resp.status_code == 200

    # Default path should not work
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 404


# ==============================================================================
# Concurrent Request Tests
# ==============================================================================


def test_concurrent_requests(metadata_manager: AuthorizationManager, dummy_provider) -> None:
    """Middleware handles concurrent requests correctly."""
    metadata_manager.set_provider(dummy_provider)

    async def endpoint(request):
        ctx = request.scope.get("openmcp.auth")
        return JSONResponse({"subject": ctx.subject if ctx else None})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    # Make multiple concurrent requests
    results = []
    for _ in range(10):
        resp = client.get("/mcp", headers={"Authorization": "Bearer good-token"})
        results.append(resp)

    # All should succeed
    assert all(r.status_code == 200 for r in results)
    assert all(r.json()["subject"] == "user" for r in results)


# ==============================================================================
# AuthorizationContext Tests
# ==============================================================================


def test_authorization_context_creation() -> None:
    """AuthorizationContext can be created with all fields."""
    ctx = AuthorizationContext(
        subject="user123",
        scopes=["read", "write"],
        claims={"email": "user@example.com", "role": "admin"},
    )
    assert ctx.subject == "user123"
    assert ctx.scopes == ["read", "write"]
    assert ctx.claims == {"email": "user@example.com", "role": "admin"}


def test_authorization_context_none_subject() -> None:
    """AuthorizationContext allows None subject."""
    ctx = AuthorizationContext(subject=None, scopes=[], claims={})
    assert ctx.subject is None
    assert ctx.scopes == []
    assert ctx.claims == {}


# ==============================================================================
# Error Response Format Tests
# ==============================================================================


def test_error_response_format(metadata_manager: AuthorizationManager) -> None:
    """Error responses have correct JSON structure."""
    async def endpoint(request):
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/mcp", endpoint, methods=["GET"])])
    wrapped = metadata_manager.wrap_asgi(app)
    client = TestClient(wrapped)

    resp = client.get("/mcp")
    assert resp.status_code == 401
    data = resp.json()
    assert "error" in data
    assert "detail" in data
    assert data["error"] == "unauthorized"
