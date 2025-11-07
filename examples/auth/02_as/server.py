# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Supabase REST demo protected by the OpenMCP Authorization Server.

This example reuses the Supabase tool from ``01_simple`` but requires OAuth 2.1
access tokens issued by the Go Authorization Server that lives in the
``mcp-knox`` workspace.

Quick start::

    # 1. Launch the authorization server (client "dedalus-browser" is seeded)
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Export Supabase + resource server settings
    $ export SUPABASE_URL="https://<project>.supabase.co"
    $ export SUPABASE_SECRET_KEY="<service_role_key>"
    $ export AS_ISSUER="http://localhost:4444"
    $ export MCP_RESOURCE_URL="http://127.0.0.1:8000"
    $ export MCP_REQUIRED_SCOPES="mcp:tools:call"

    # 3. Start the protected MCP Resource Server
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

Client command (separate shell)::

    $ uv run python examples/auth/02_as/client.py \
          --client-id dedalus-browser \
          --redirect-uri http://127.0.0.1:8400/callback \
          --callback-port 8400 \
          --table users --limit 5

The client spins up a temporary callback listener, opens Clerk’s hosted login
page, and trades the resulting authorization code for an access token before
calling ``supabase_select_live``.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Any

import httpx
from dotenv import load_dotenv

from openmcp import MCPServer, get_context, tool
from openmcp.server.authorization import AuthorizationConfig
from openmcp.server.authorization import AuthorizationContext
from openmcp.server.services.jwt_validator import JWTValidator, JWTValidatorConfig


load_dotenv()


AS_ISSUER = os.getenv("AS_ISSUER", "http://localhost:4444").rstrip("/")
MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL", "http://127.0.0.1:8000").rstrip("/")
REQUIRED_SCOPES = [scope for scope in os.getenv("MCP_REQUIRED_SCOPES", "mcp:tools:call").split() if scope]
JWKS_URI = os.getenv("AS_JWKS_URI", f"{AS_ISSUER}/.well-known/jwks.json")

if not REQUIRED_SCOPES:
    raise RuntimeError("Provide at least one scope via MCP_REQUIRED_SCOPES")


@dataclass(slots=True)
class SupabaseCredentials:
    """Resolved Supabase material for a single invocation.

    For the hackathon we read everything from env vars. In production this
    object will be created from SSM / Secrets Manager *after* JWT validation
    using the connection handle encoded in the token claims.
    """

    url: str
    service_key: str

    @classmethod
    def from_env(cls) -> "SupabaseCredentials":
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SECRET_KEY")
        if not url:
            raise RuntimeError("SUPABASE_URL must be set (try .env for local dev)")
        if not key:
            raise RuntimeError("SUPABASE_SECRET_KEY must be set")
        return cls(url=url.rstrip("/"), service_key=key)

    def auth_headers(self) -> dict[str, str]:
        return {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }


def resolve_supabase_credentials(auth_ctx: AuthorizationContext | None) -> SupabaseCredentials:
    """Resolve the credential bundle for this request.

    Today we simply return the env-backed service key. The important part is
    *when* the lookup happens: only after ``auth_ctx`` exists (meaning the AS
    has validated the caller and we know which handle they requested). Once we
    add per-user secrets, this function will:

      1. Read ``auth_ctx.claims`` (e.g., ``conn_secret_path`` or ``conn_handle``)
      2. Call AWS SSM / Secrets Manager for just that path
      3. Return ``SupabaseCredentials(url=<from config>, service_key=<decrypted>)``

    That keeps secrets out of the Lambda image while still letting the RS act
    on behalf of the user.
    """

    _ = auth_ctx  # placeholder until per-user handles are wired
    return SupabaseCredentials.from_env()


def _audiences(base: str) -> list[str]:
    clean = base.rstrip("/")
    candidates = {clean}
    if clean.endswith("/mcp"):
        parent = clean[: -len("/mcp")]
        if parent:
            candidates.add(parent)
    else:
        candidates.add(f"{clean}/mcp")
    return sorted(candidates)


audience_candidates = _audiences(MCP_RESOURCE_URL)

server = MCPServer(
    name="supabase-connector-demo",
    instructions=(
        "OAuth 2.1 protected Supabase connector. Access tokens come from the "
        "Go Authorization Server; the service key never leaves the RS."),
    authorization=AuthorizationConfig(
        enabled=True,
        authorization_servers=[AS_ISSUER],
        required_scopes=REQUIRED_SCOPES,
    ),
)

jwt_config = JWTValidatorConfig(
    jwks_uri=JWKS_URI,
    issuer=AS_ISSUER,
    audience=audience_candidates,
    required_scopes=REQUIRED_SCOPES,
)
server.set_authorization_provider(JWTValidator(jwt_config))


with server.binding():

    @tool(description="Execute a Supabase REST query using the configured service role key.")
    async def supabase_select_live(
        table: str = "users",
        columns: str = "*",
        limit: int | None = 5,
    ) -> dict[str, Any]:
        ctx = get_context()
        auth_ctx = ctx.auth_context
        subject = getattr(auth_ctx, "subject", None) if auth_ctx else None
        scopes = getattr(auth_ctx, "scopes", None) if auth_ctx else None

        creds = resolve_supabase_credentials(auth_ctx)

        params = {"select": columns}
        if limit is not None:
            params["limit"] = str(limit)

        url = f"{creds.url}/rest/v1/{table}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=creds.auth_headers(), params=params)

        body: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body = response.json()
        else:
            body = response.text

        extra = {
            "event": "supabase.request",
            "table": table,
            "limit": limit,
            "status": response.status_code,
            "subject": subject,
        }
        if scopes:
            extra["scopes"] = scopes

        if response.status_code >= 400:
            server._logger.warning("supabase request failed", extra={"context": extra | {"body": body}})
        else:
            row_count = len(body) if isinstance(body, list) else None
            server._logger.info("supabase request succeeded", extra={"context": extra | {"row_count": row_count}})

        result = {
            "url": url,
            "status": response.status_code,
            "body": body,
        }
        if subject or scopes:
            result["_meta"] = {"subject": subject, "scopes": scopes}
        return result


async def main() -> None:
    print(
        "[supabase-oauth-demo] starting — "
        f"issuer={AS_ISSUER}, resource={MCP_RESOURCE_URL}, scopes={','.join(REQUIRED_SCOPES)}"
    )
    await server.serve(
        transport="streamable-http",
        verbose=False,
        log_level="info",
        uvicorn_options={"access_log": False},
    )


if __name__ == "__main__":
    asyncio.run(main())
