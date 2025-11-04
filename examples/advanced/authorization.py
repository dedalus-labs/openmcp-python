# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""[DRAFT] OAuth 2.1 authorization flow stub.

Production-ready interface stub for OAuth 2.1 protected resource pattern.
Full implementation pending PLA-26 (authorization server) and PLA-27 (token
introspection client).

This example demonstrates the complete authorization flow interface that will
be supported once the authorization server infrastructure is available.

Run:
    uv run python examples/advanced/authorization.py

Reference:
    - Current stub: examples/auth_stub/server.py
    - Authorization config: src/openmcp/server/authorization.py
    - OAuth 2.1: https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-11
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from openmcp import AuthorizationConfig, MCPServer, tool
from openmcp.server.authorization import AuthorizationContext, AuthorizationError, AuthorizationProvider


@dataclass
class TokenClaims:
    """JWT claims from validated access token."""

    sub: str  # Subject (user ID)
    iss: str  # Issuer (authorization server)
    aud: str | list[str]  # Audience (this resource server)
    exp: int  # Expiration timestamp
    iat: int  # Issued at timestamp
    scope: str  # Space-separated scopes
    client_id: str | None = None  # OAuth client identifier
    custom_claims: dict[str, Any] | None = None  # Extension claims


class RemoteTokenIntrospectionProvider(AuthorizationProvider):
    """Production authorization provider using token introspection.

    Validates access tokens against an OAuth 2.1 authorization server
    via RFC 7662 token introspection endpoint.

    Implementation blocked on: PLA-27 (token introspection client)
    """

    def __init__(self, introspection_endpoint: str, client_id: str, client_secret: str) -> None:
        self.introspection_endpoint = introspection_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        # Cache for validated tokens (TTL-based)
        self._token_cache: dict[str, tuple[AuthorizationContext, float]] = {}

    async def validate(self, token: str) -> AuthorizationContext:
        """Validate token via remote introspection endpoint.

        Production implementation would:
        1. Check local cache for token
        2. If miss, call introspection endpoint with client credentials
        3. Parse introspection response (active, scope, sub, exp, etc.)
        4. Cache result with TTL = min(exp - now, cache_ttl)
        5. Return AuthorizationContext or raise AuthorizationError

        Stub implementation for interface demonstration:
        """
        import time

        # Check cache
        if token in self._token_cache:
            ctx, expiry = self._token_cache[token]
            if time.time() < expiry:
                return ctx

        # STUB: This would be an HTTP POST to introspection_endpoint
        # POST /introspect
        # Authorization: Basic base64(client_id:client_secret)
        # Content-Type: application/x-www-form-urlencoded
        # Body: token=<token>&token_type_hint=access_token

        # Simulated introspection response
        if token.startswith("valid-"):
            introspection_response = {
                "active": True,
                "scope": "mcp:read mcp:write",
                "client_id": "demo-client",
                "username": "user@example.com",
                "token_type": "Bearer",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
                "sub": "user-123",
                "aud": "mcp-server",
            }
        else:
            introspection_response = {"active": False}

        if not introspection_response.get("active"):
            raise AuthorizationError("Token is not active")

        # Extract context
        ctx = AuthorizationContext(
            subject=introspection_response.get("sub"),
            scopes=introspection_response.get("scope", "").split(),
            claims={
                "client_id": introspection_response.get("client_id"),
                "username": introspection_response.get("username"),
                "exp": introspection_response.get("exp"),
            },
        )

        # Cache with TTL
        cache_ttl = min(introspection_response["exp"] - int(time.time()), 300)
        self._token_cache[token] = (ctx, time.time() + cache_ttl)

        return ctx


class LocalJWTProvider(AuthorizationProvider):
    """Alternative provider for self-contained JWT validation.

    Validates JWT access tokens locally using public keys from authorization
    server's JWKS endpoint. Faster than introspection but requires periodic
    key rotation handling.

    Implementation blocked on: JWT library integration and JWKS client
    """

    def __init__(self, jwks_uri: str, audience: str, issuer: str) -> None:
        self.jwks_uri = jwks_uri
        self.audience = audience
        self.issuer = issuer
        # Public keys cache (fetched from JWKS endpoint)
        self._keys: dict[str, Any] = {}

    async def validate(self, token: str) -> AuthorizationContext:
        """Validate JWT locally using cached public keys.

        Production implementation would:
        1. Decode JWT header to extract 'kid' (key ID)
        2. Fetch public key from JWKS endpoint if not cached
        3. Verify JWT signature using public key
        4. Validate standard claims (exp, iat, iss, aud)
        5. Extract scopes and custom claims
        6. Return AuthorizationContext

        Stub for interface:
        """
        # STUB: This would use PyJWT or python-jose
        # jwt.decode(token, key, algorithms=['RS256'], audience=self.audience, issuer=self.issuer)

        raise AuthorizationError("JWT validation not yet implemented")


async def main() -> None:
    """Demonstrate OAuth 2.1 protected resource pattern."""

    # Production configuration pointing to real authorization server
    server = MCPServer(
        "oauth-protected-server",
        instructions="OAuth 2.1 protected MCP server",
        authorization=AuthorizationConfig(
            enabled=True,
            # Advertised to clients in /.well-known/oauth-protected-resource
            authorization_servers=["https://as.dedaluslabs.ai"],
            # Required scopes for accessing this server
            required_scopes=["mcp:read", "mcp:write"],
            # Metadata endpoint (RFC 8414 extension)
            metadata_path="/.well-known/oauth-protected-resource",
            # Cache validated tokens for 5 minutes
            cache_ttl=300,
        ),
    )

    # Inject production authorization provider
    # Choose between introspection (stateless, always fresh) or JWT (faster, cached)
    provider = RemoteTokenIntrospectionProvider(
        introspection_endpoint="https://as.dedaluslabs.ai/introspect",
        client_id="mcp-server-001",
        client_secret="secret-from-env",  # In production: os.environ['OAUTH_CLIENT_SECRET']
    )
    server.set_authorization_provider(provider)

    # Register protected tools
    with server.binding():

        @tool(description="Read user data (requires mcp:read scope)")
        async def read_data(user_id: str) -> dict[str, Any]:
            """Access control enforced by framework via required_scopes."""
            # In production, you could access the authorization context:
            # from openmcp import get_context
            # ctx = get_context()
            # auth_ctx = ctx.authorization  # AuthorizationContext with scopes/claims
            return {"user_id": user_id, "data": "sensitive information"}

        @tool(description="Write user data (requires mcp:write scope)")
        async def write_data(user_id: str, data: dict[str, Any]) -> str:
            """Fine-grained access control example."""
            # Example: check custom claim for admin privilege
            # if 'admin' not in auth_ctx.claims.get('roles', []):
            #     raise PermissionError("Admin role required")
            return f"Data written for {user_id}"

    # Client interaction example:
    # 1. Client obtains access token from authorization server
    #    POST https://as.dedaluslabs.ai/token
    #    Body: grant_type=client_credentials&scope=mcp:read mcp:write
    #
    # 2. Client includes token in MCP requests
    #    Authorization: Bearer <access-token>
    #
    # 3. Server validates token before processing request
    #    - If invalid/expired: 401 Unauthorized
    #    - If insufficient scopes: 403 Forbidden
    #    - If valid: process request with authorization context

    await server.serve(port=8000)


if __name__ == "__main__":
    print("OAuth 2.1 authorization example (interface stub)")
    print("Full implementation pending: PLA-26 (auth server), PLA-27 (introspection)")
    print("")
    print("Test with valid token:")
    print('  curl -H "Authorization: Bearer valid-demo-token" http://localhost:8000/mcp')
    # asyncio.run(main())  # Uncomment when auth server is available
