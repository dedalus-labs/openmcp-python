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

    # 1. Start the Go Authorization Server (dedalus-browser is seeded)
    $ cd ~/Desktop/dedalus-labs/codebase/mcp-knox/openmcp-authorization-server
    $ go run ./cmd/serve

    # 2. Start the protected resource server (new shell)
    $ cd ~/Desktop/dedalus-labs/codebase/openmcp
    $ uv run python examples/auth/02_as/server.py

    # 3. Run the PKCE client locally; it hosts http://127.0.0.1:8400/callback,
    #    opens Clerk’s sign-in page, and waits for the authorization response.
    $ uv run python examples/auth/02_as/client.py \
          --client-id dedalus-browser \
          --redirect-uri http://127.0.0.1:8400/callback \
          --callback-port 8400 \
          --table users --limit 5

When the browser prompts, sign in via Clerk. After the redirect hits the local
callback listener, the CLI exchanges the code for tokens and calls the MCP
tool with the resulting bearer credentials.
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
import threading
import webbrowser
from typing import Any
from urllib.parse import parse_qs, urlparse

from http.server import BaseHTTPRequestHandler
import socketserver

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
DEFAULT_CLIENT_ID = os.getenv("MCP_CLIENT_ID", "dedalus-browser")
DEFAULT_CALLBACK_PORT = int(os.getenv("MCP_CALLBACK_PORT", "8400"))


class OAuthError(RuntimeError):
    """Raised when the OAuth handshake fails."""


class _CallbackServer(socketserver.TCPServer):
    allow_reuse_address = True


def _generate_pkce() -> tuple[str, str]:
    alphabet = string.ascii_letters + string.digits + "-._~"
    verifier = "".join(secrets.choice(alphabet) for _ in range(64))
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


def _start_callback_listener(state: str, port: int) -> tuple[socketserver.TCPServer, asyncio.Future]:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[dict[str, Any]] = loop.create_future()
    callback_path = "/callback"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

        def do_GET(self) -> None:  # noqa: D401
            parsed = urlparse(self.path)
            if parsed.path != callback_path:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Invalid callback path")
                return

            params = parse_qs(parsed.query)
            result = {
                "code": params.get("code", [None])[0],
                "state": params.get("state", [None])[0],
                "error": params.get("error", [None])[0],
                "error_description": params.get("error_description", [None])[0],
            }

            body = (
                "<html><body><h1>Authentication complete</h1>"
                "<p>You can return to the CLI.</p></body></html>"
            )
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

            if not future.done():
                loop.call_soon_threadsafe(future.set_result, result)

    server = _CallbackServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    server._thread = thread  # type: ignore[attr-defined]
    return server, future


def _stop_callback_listener(server: socketserver.TCPServer) -> None:
    thread = getattr(server, "_thread", None)
    server.shutdown()
    server.server_close()
    if isinstance(thread, threading.Thread):
        thread.join(timeout=1)


async def fetch_access_token(args: argparse.Namespace) -> dict[str, Any]:
    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(16)

    redirect_uri = args.redirect_uri or f"http://127.0.0.1:{args.callback_port}/callback"

    query = {
        "response_type": "code",
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "scope": args.scope,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "resource": args.resource,
    }

    token_url = f"{args.issuer.rstrip('/')}/oauth2/token"
    auth_url = f"{args.issuer.rstrip('/')}/oauth2/auth"

    server, future = _start_callback_listener(state, args.callback_port)

    auth_request = httpx.QueryParams(query)
    full_auth_url = f"{auth_url}?{auth_request}"
    print("Opening browser for Clerk sign-in…")
    if not webbrowser.open(full_auth_url, new=1, autoraise=True):
        print("Please open this URL manually:")
        print(full_auth_url)
    else:
        print("If the browser did not open, paste this URL manually:")
        print(full_auth_url)

    try:
        callback = await asyncio.wait_for(future, timeout=300)
    except asyncio.TimeoutError as exc:
        _stop_callback_listener(server)
        raise OAuthError("Timed out waiting for the authorization response.") from exc
    finally:
        _stop_callback_listener(server)

    error = callback.get("error")
    if error:
        raise OAuthError(
            f"Authorization server returned error={error}: {callback.get('error_description') or 'no description'}"
        )

    returned_state = callback.get("state")
    if returned_state != state:
        raise OAuthError("State mismatch while handling authorization response")

    code = callback.get("code")
    if not code:
        raise OAuthError("Authorization server did not supply an authorization code")

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": args.client_id,
        "redirect_uri": redirect_uri,
        "code_verifier": verifier,
        "resource": args.resource,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient(timeout=30.0) as client:
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
    parser.add_argument(
        "--client-id",
        default=DEFAULT_CLIENT_ID,
        help="OAuth client_id registered with the AS (default: %(default)s)",
    )
    parser.add_argument(
        "--redirect-uri",
        default=None,
        help="Redirect URI registered with the AS (defaults to http://127.0.0.1:<port>/callback)",
    )
    parser.add_argument(
        "--callback-port",
        type=int,
        default=DEFAULT_CALLBACK_PORT,
        help="Local port for the temporary redirect listener (default: %(default)s)",
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
