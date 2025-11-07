# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Client-credentials MCP client for the Supabase OAuth demo.

This example demonstrates fully headless authentication: the CLI exchanges a
confidential ``client_id``/``client_secret`` pair for an access token using the
OAuth 2.1 ``client_credentials`` grant, then calls the protected MCP resource
server from ``examples/auth/02_as``.

Quick start::

    # 1. Seed the "dedalus-m2m" client by exporting a secret before
    #    starting the Go authorization server
    $ export AS_M2M_CLIENT_SECRET="dev-m2m-secret"
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Start the protected Supabase resource server
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

    # 3. Run this client with matching credentials (env or flags)
    $ export MCP_CLIENT_SECRET="dev-m2m-secret"
    $ uv run python examples/auth/03_client_credentials/client.py \
          --client-id dedalus-m2m --table users --limit 5

Because this grant type never involves a browser or Clerk, it is ideal for CI/CD
pipelines and other machine-to-machine workflows.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

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
DEFAULT_CLIENT_ID = os.getenv("MCP_CLIENT_ID", "dedalus-m2m")
DEFAULT_CLIENT_SECRET = os.getenv("MCP_CLIENT_SECRET")


class OAuthError(RuntimeError):
    """Raised when the OAuth handshake fails."""


async def fetch_access_token(args: argparse.Namespace) -> dict[str, Any]:
    """Exchange client credentials for an access token."""

    token_url = f"{args.issuer.rstrip('/')}/oauth2/token"
    data = {
        "grant_type": "client_credentials",
        "scope": args.scope,
        "resource": args.resource,
    }
    auth = httpx.BasicAuth(args.client_id, args.client_secret)

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            token_response = await client.post(token_url, data=data, auth=auth)
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
    parser = argparse.ArgumentParser(description="Supabase OAuth client demo (client_credentials grant)")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="MCP endpoint (default: %(default)s)")
    parser.add_argument("--resource", default=DEFAULT_RESOURCE, help="Resource/audience URI (default: %(default)s)")
    parser.add_argument("--issuer", default=DEFAULT_ISSUER, help="Authorization Server issuer (default: %(default)s)")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID, help="OAuth client_id (default: %(default)s)")
    parser.add_argument(
        "--client-secret",
        default=DEFAULT_CLIENT_SECRET,
        help="OAuth client_secret (default: MCP_CLIENT_SECRET env)",
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
    parser.add_argument("--access-token", help="Skip OAuth flow and use an existing access token")
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

    if not args.client_secret:
        raise SystemExit("Provide --client-secret or set MCP_CLIENT_SECRET before running this example.")

    token_data: dict[str, Any]
    if args.access_token:
        token_data = {"access_token": args.access_token}
    else:
        print("Requesting OAuth token (client_credentials)…")
        token_data = await fetch_access_token(args)
        print("Received access token; calling MCP server…\n")

    access_token = token_data.get("access_token")
    if not access_token:
        raise SystemExit("Authorization Server response lacked access_token")

    await call_supabase_tool(args, access_token)


if __name__ == "__main__":
    asyncio.run(main())
