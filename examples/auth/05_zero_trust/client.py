# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Authorization-code MCP client for the Supabase OAuth demo.

This client talks to the resource server in ``examples/auth/02_as`` and obtains
an OAuth 2.1 access token from the Go Authorization Server before calling any
MCP tools.  The flow purposely sticks to standards-only building blocks so it
works with the production stack once the missing UI pieces land.

Usage::

    # 1. Make sure the Authorization Server is running
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Ensure the client_id + redirect_uri below exist in the AS store
    #    (see the comment in server.py for a quick helper.)

    # 3. Start the resource server (separate shell)
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

    # 4. Run the client; it will fetch a token and call supabase_select_live
    $ uv run python examples/auth/02_as/client.py \
          --client-id supabase-cli \
          --redirect-uri https://127.0.0.1/callback \
          --table users --limit 5

The Authorization Server currently auto-approves requests, so the client can
capture the authorization code directly from the 302 response without spinning
up a local callback listener.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import string
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
from pydantic import ValidationError

from openmcp.client import open_connection
from openmcp.types import (
    CallToolRequest,
    CallToolRequestParams,
    CallToolResult,
    ClientRequest,
    ListToolsRequest,
    ListToolsResult,
)
from openmcp.utils import to_json

DEFAULT_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
DEFAULT_RESOURCE = os.getenv("MCP_RESOURCE_URL", "http://127.0.0.1:8000")
DEFAULT_ISSUER = os.getenv("AS_ISSUER", "http://localhost:4444")
DEFAULT_SCOPE = os.getenv("MCP_REQUIRED_SCOPES", "mcp:tools:call")


class OAuthError(RuntimeError):
    """Raised when the OAuth handshake fails."""


def _generate_pkce() -> tuple[str, str]:
    alphabet = string.ascii_letters + string.digits + "-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


async def fetch_access_token(args: argparse.Namespace) -> dict[str, Any]:
    """Run the OAuth 2.1 authorization code flow against the AS."""

    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    query = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": args.redirect_uri,
        "scope": args.scope,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": args.resource,
    }

    token_url = f"{args.issuer.rstrip('/')}/oauth2/token"
    auth_url = f"{args.issuer.rstrip('/')}/oauth2/auth"

    async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as client:
        try:
            auth_response = await client.get(auth_url, params=query)
        except httpx.ConnectError as exc:
            raise OAuthError(
                f"Failed to contact authorization server at {auth_url}. "
                "Ensure AS_ISSUER is correct and the server is running."
            ) from exc
        if auth_response.status_code not in (302, 303):
            raise OAuthError(
                f"Authorization request failed: HTTP {auth_response.status_code} {auth_response.text}"
            )

        location = auth_response.headers.get("location")
        if not location:
            raise OAuthError("Authorization server did not provide a redirect location")

        parsed = urlparse(location)
        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        returned_state = params.get("state", [None])[0]
        if not code:
            error = params.get("error", ["unknown_error"])[0]
            desc = params.get("error_description", ["no description"])[0]
            hint = ""
            if error == "invalid_client":
                hint = (
                    " — the client_id/redirect_uri pair is not registered. "
                    "Register the client_id/redirect_uri pair with the authorization server before retrying."
                )
            raise OAuthError(f"Authorization server returned error={error}: {desc}{hint}")
        if returned_state != state:
            raise OAuthError("State mismatch while handling authorization response")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": args.client_id,
            "redirect_uri": args.redirect_uri,
            "code_verifier": verifier,
            "resource": args.resource,
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            token_response = await client.post(token_url, data=data, headers=headers)
        except httpx.ConnectError as exc:
            raise OAuthError(
                f"Failed to reach token endpoint at {token_url}. "
                "Confirm AS_ISSUER is correct and network access is available."
            ) from exc
        if token_response.status_code != 200:
            raise OAuthError(
                f"Token request failed: HTTP {token_response.status_code} {token_response.text}"
            )
        return token_response.json()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supabase OAuth client demo")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="MCP endpoint (default: %(default)s)")
    parser.add_argument("--resource", default=DEFAULT_RESOURCE, help="Resource/audience URI (default: %(default)s)")
    parser.add_argument("--issuer", default=DEFAULT_ISSUER, help="Authorization Server issuer (default: %(default)s)")
    parser.add_argument("--client-id", required=True, help="OAuth client_id registered with the AS")
    parser.add_argument(
        "--redirect-uri",
        required=True,
        help="Redirect URI registered with the AS (exact match)",
    )
    parser.add_argument("--scope", default=DEFAULT_SCOPE, help="Space-separated scopes (default: %(default)s)")
    parser.add_argument("--table", default="users", help="Supabase table to query")
    parser.add_argument("--columns", default="*", help="Column projection for Supabase")
    parser.add_argument("--limit", type=int, default=5, help="Row limit (default: %(default)s)")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "lambda-http"],
        help="MCP transport (default: %(default)s)",
    )
    parser.add_argument(
        "--access-token",
        help="Skip OAuth flow and use an existing access token",
    )
    return parser


async def call_supabase_tool(args: argparse.Namespace, access_token: str) -> None:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with open_connection(url=args.url, transport=args.transport, headers=headers) as client:
        init = client.initialize_result
        if init is None:
            raise RuntimeError("MCP initialize handshake failed")
        print(
            f"Connected to {init.serverInfo.name} v{init.serverInfo.version or '0.0.0'} via {args.transport}"
        )
        print(f"Negotiated MCP protocol version: {init.protocolVersion}\n")

        list_request = ClientRequest(ListToolsRequest())
        tools_result = await client.send_request(list_request, ListToolsResult)

        print("Available tools:")
        for idx, tool in enumerate(tools_result.tools, start=1):
            desc = tool.description or "(no description)"
            print(f"  {idx:>2}. {tool.name} — {desc}")

        expected_tool = "supabase_select_live"
        available = {tool.name for tool in tools_result.tools}
        if expected_tool not in available:
            print(
                f"Tool '{expected_tool}' is not available on server '{init.serverInfo.name}'.\n"
                "Ensure the protected server (examples/auth/02_as/server.py) is running "
                "or register an equivalent tool before retrying."
            )
            return

        arguments: dict[str, Any] = {"table": args.table, "columns": args.columns}
        if args.limit is not None:
            arguments["limit"] = args.limit

        try:
            request = ClientRequest(
                CallToolRequest(params=CallToolRequestParams(name="supabase_select_live", arguments=arguments))
            )
        except ValidationError as exc:
            raise SystemExit(f"Invalid tool arguments: {exc}") from exc

        result = await client.send_request(request, CallToolResult)
        status = "error" if result.isError else "success"
        print(f"\nTool call status: {status}")

        payload = to_json(result)
        print(json.dumps(payload, indent=2))


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.limit is not None and args.limit < 0:
        args.limit = None

    token_data: dict[str, Any]
    if args.access_token:
        token_data = {"access_token": args.access_token}
    else:
        print("Requesting OAuth token from Authorization Server…")
        token_data = await fetch_access_token(args)
        print("Received access token; calling MCP server…\n")

    access_token = token_data.get("access_token")
    if not access_token:
        raise SystemExit("Authorization Server response lacked access_token")

    await call_supabase_tool(args, access_token)


if __name__ == "__main__":
    asyncio.run(main())
