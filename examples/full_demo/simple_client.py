# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal MCP client for the Brave Search demo server."""

from __future__ import annotations

import anyio

from openmcp import types
from openmcp.client import open_connection


SERVER_URL: str = "http://127.0.0.1:8000/mcp"
url = SERVER_URL


async def main() -> None:
    async with open_connection(url=url, transport="streamable-http") as client:
        tools = await client.send_request(types.ClientRequest(types.ListToolsRequest()), types.ListToolsResult)
        print("Tools:", [tool.name for tool in tools.tools])

        result = await client.send_request(
            types.ClientRequest(
                types.CallToolRequest(
                    params=types.CallToolRequestParams(
                        name="brave_web_search", arguments={"query": "model context protocol", "count": 1}
                    )
                )
            ),
            types.CallToolResult,
        )
        print("brave_web_search result:", result.content)


if __name__ == "__main__":
    anyio.run(main)
