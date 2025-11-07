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

    # 1. Start the authorization server (from the mcp-knox repo)
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Bootstrap or register a public client (once per session).  The memory
    #    store accepts the helper below inside cmd/serve/main.go:
    #        store.SaveClient(&oauth2.Client{
    #            ID: "supabase-cli",
    #            RedirectURIs: []string{"https://127.0.0.1/callback"},
    #            GrantTypes: []string{"authorization_code", "refresh_token"},
    #            Scopes: []string{"mcp:tools:call", "offline_access"},
    #        })
    #    (A proper /oauth2/register endpoint is coming soon.)

    # 3. Export the Supabase + auth settings for this demo
    $ export SUPABASE_URL="https://<project>.supabase.co"
    $ export SUPABASE_SECRET_KEY="<service_role_key>"
    $ export AS_ISSUER="http://localhost:4444"
    $ export MCP_RESOURCE_URL="http://127.0.0.1:8000"
    $ export MCP_REQUIRED_SCOPES="mcp:tools:call"

    # 4. Start the MCP Resource Server
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

The matching ``client.py`` walks through the authorization-code + PKCE flow and
invokes the tool with the resulting bearer token.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from dotenv import load_dotenv

from openmcp import MCPServer, get_context, tool
from openmcp.server.authorization import AuthorizationConfig
from openmcp.server.services.jwt_validator import JWTValidator, JWTValidatorConfig


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY")
AS_ISSUER = os.getenv("AS_ISSUER", "http://localhost:4444").rstrip("/")
MCP_RESOURCE_URL = os.getenv("MCP_RESOURCE_URL", "http://127.0.0.1:8000").rstrip("/")
REQUIRED_SCOPES = [scope for scope in os.getenv("MCP_REQUIRED_SCOPES", "mcp:tools:call").split() if scope]
JWKS_URI = os.getenv("AS_JWKS_URI", f"{AS_ISSUER}/.well-known/jwks.json")

if not SUPABASE_URL:
    raise RuntimeError("Set SUPABASE_URL before starting the resource server")
if not SUPABASE_SECRET_KEY:
    raise RuntimeError("Set SUPABASE_SECRET_KEY before starting the resource server")
if not REQUIRED_SCOPES:
    raise RuntimeError("Provide at least one scope via MCP_REQUIRED_SCOPES")


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
    instructions="OAuth 2.1 protected Supabase connector (service-key stays server-side)",
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

        params = {"select": columns}
        if limit is not None:
            params["limit"] = str(limit)

        headers = {
            "apikey": SUPABASE_SECRET_KEY,
            "Authorization": f"Bearer {SUPABASE_SECRET_KEY}",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

        url = f"{SUPABASE_URL.rstrip('/')}/rest/v1/{table}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers, params=params)

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
