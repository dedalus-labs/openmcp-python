# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Device-authorization MCP client for the Supabase OAuth demo.

This client talks to the resource server in ``examples/auth/02_as`` and obtains
an OAuth 2.1 access token from the Go Authorization Server before calling any
MCP tools.  The flow purposely sticks to standards-only building blocks so it
works with the production stack once the missing UI pieces land.

Usage::

    # 1. Make sure the Authorization Server is running
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Start the resource server (separate shell)
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

    # 3. Run the device-flow client; it will fetch a token and call the tool
    $ uv run python examples/auth/04_device_flow/client.py \
          --client-id dedalus-cli \
          --table users --limit 5

The Authorization Server uses RFC 8628 device authorization for the CLI: this
program requests a device code, asks you to visit ``/device`` (Clerk-hosted
sign-in), polls the token endpoint, and then calls Supabase once the device code
is approved.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
from typing import Any
from urllib.parse import urlparse

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
DEFAULT_CLIENT_ID = os.getenv("MCP_CLIENT_ID", "dedalus-cli")


class OAuthError(RuntimeError):
    """Raised when the OAuth handshake fails."""


async def fetch_access_token(args: argparse.Namespace) -> dict[str, Any]:
    """Run the RFC 8628 device authorization flow against the AS."""

    token_url = f"{args.issuer.rstrip('/')}/oauth2/token"
    device_url = f"{args.issuer.rstrip('/')}/oauth2/device/auth"

    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {
            "client_id": args.client_id,
            "scope": args.scope,
            "resource": args.resource,
        }
        try:
            device_response = await client.post(device_url, data=payload)
        except httpx.ConnectError as exc:
            raise OAuthError(
                f"Failed to contact authorization server at {device_url}. "
                "Ensure AS_ISSUER is correct and the server is running."
            ) from exc
        if device_response.status_code != 200:
            raise OAuthError(
                f"Device authorization failed: HTTP {device_response.status_code} {device_response.text}"
            )

        device_json = device_response.json()
        device_code = device_json["device_code"]
        user_code = device_json["user_code"]
        verification_uri = device_json["verification_uri"]
        verification_uri_complete = device_json.get("verification_uri_complete")
        interval = int(device_json.get("interval", 5))

        print("\n=== Device authorization required ===")
        print(f" User code: {user_code}")
        if verification_uri_complete:
            print(f" Visit: {verification_uri_complete}")
        else:
            print(f" Visit: {verification_uri} and enter the user code above.")
        print(" Waiting for approval…\n")

        while True:
            await asyncio.sleep(interval)
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": args.client_id,
            }
            try:
                token_response = await client.post(token_url, data=data)
            except httpx.ConnectError as exc:
                raise OAuthError(
                    f"Failed to reach token endpoint at {token_url}. "
                    "Confirm AS_ISSUER is correct and network access is available."
                ) from exc

            if token_response.status_code == 200:
                print("✓ Device approved.\n")
                return token_response.json()

            error_payload = token_response.json()
            error = error_payload.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            raise OAuthError(
                f"Device flow failed: error={error} description={error_payload.get('error_description')}"
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Supabase OAuth client demo")
    parser.add_argument("--url", default=DEFAULT_SERVER_URL, help="MCP endpoint (default: %(default)s)")
    parser.add_argument("--resource", default=DEFAULT_RESOURCE, help="Resource/audience URI (default: %(default)s)")
    parser.add_argument("--issuer", default=DEFAULT_ISSUER, help="Authorization Server issuer (default: %(default)s)")
    parser.add_argument(
        "--client-id",
        default=DEFAULT_CLIENT_ID,
        help="OAuth client_id registered with the AS (default: %(default)s)",
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
