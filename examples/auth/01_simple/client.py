# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Simplified MCP client for the Supabase REST demo.

Run the Supabase server first:

    uv run python examples/auth/01_simple/server.py

Then in another shell:

    uv run python examples/auth/01_simple/client.py --table users --limit 5

Environment variables:
    * MCP_SERVER_URL – overrides the MCP endpoint URL
      (default: http://127.0.0.1:8000/mcp)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any

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


DEFAULT_URL = os.getenv("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")


async def run_client(args: argparse.Namespace) -> None:
    async with open_connection(url=args.url, transport=args.transport) as client:
        init = client.initialize_result
        if init is None:
            raise RuntimeError("Client failed to negotiate initialize handshake")

        server = init.serverInfo
        print(f"Connected to {server.name} v{server.version or '0.0.0'} via {args.transport}")
        print(f"Negotiated MCP protocol version: {init.protocolVersion}\n")

        list_request = ClientRequest(ListToolsRequest())
        tools_result = await client.send_request(list_request, ListToolsResult)

        print("Available tools:")
        for idx, tool in enumerate(tools_result.tools, start=1):
            desc = tool.description or "(no description)"
            print(f"  {idx:>2}. {tool.name} — {desc}")

        if not tools_result.tools:
            raise SystemExit("Server returned zero tools; nothing to call.")

        tool_name = "supabase_query"
        if tool_name not in {tool.name for tool in tools_result.tools}:
            raise SystemExit(f"Tool '{tool_name}' not found in server response.")

        call_arguments: dict[str, Any] = {
            "table": args.table,
            "columns": args.columns,
        }
        if args.limit is not None:
            call_arguments["limit"] = args.limit

        try:
            call_request = ClientRequest(
                CallToolRequest(params=CallToolRequestParams(name=tool_name, arguments=call_arguments))
            )
        except ValidationError as exc:
            message = "Failed to build CallToolRequest; check provided arguments."
            raise SystemExit(f"{message}\n{exc}") from exc

        call_result = await client.send_request(call_request, CallToolResult)

        status = "error" if call_result.isError else "success"
        print(f"\nTool call status: {status}")
        if call_result.isError:
            text_blocks = [block for block in call_result.content if getattr(block, "type", None) == "text"]
            if text_blocks:
                first = text_blocks[0]
                message = getattr(first, "text", None)
                if message:
                    print(f"Server reported: {message}")

        payload = to_json(call_result)
        print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MCP client for the Supabase REST demo")
    parser.add_argument("--url", default=DEFAULT_URL, help="MCP endpoint URL (default: %(default)s)")
    parser.add_argument(
        "--transport",
        default="streamable-http",
        choices=["streamable-http", "lambda-http"],
        help="Transport to use (default: %(default)s)",
    )
    parser.add_argument("--table", default="users", help="Supabase table name (default: %(default)s)")
    parser.add_argument("--columns", default="*", help="Column selection for Supabase query")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Row limit for Supabase query; use -1 to omit",
    )
    return parser


async def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.limit is not None and args.limit < 0:
        args.limit = None
    await run_client(args)


if __name__ == "__main__":
    asyncio.run(main())
