# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal MCP client demonstrating tool, resource, and prompt usage.

Run after starting ``server.py`` in another shell.

    uv run python examples/hello_trip/client.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPClient
from openmcp.client import lambda_http_client


SERVER_URL = "http://127.0.0.1:8000/mcp"


async def main() -> None:
    async with (
        lambda_http_client(SERVER_URL, terminate_on_close=True) as (read_stream, write_stream, get_session_id),
        MCPClient(read_stream, write_stream) as client,
    ):
        print("Connected. Protocol version:", client.initialize_result.protocolVersion)

        tools = await client.session.list_tools()
        print("Tools:", [tool.name for tool in tools.tools])
        for tool_def in tools.tools:
            print("Tool schema:", tool_def.outputSchema)

        result = await client.session.call_tool("plan_trip", {"destination": "Barcelona", "days": 5, "budget": 2500})
        print("plan_trip result:", result.structuredContent or result.content)

        resources = await client.session.list_resources()
        print("Resources:", [res.uri for res in resources.resources])

        resource_uri = str(resources.resources[0].uri) if resources.resources else None
        resource = await client.session.read_resource(resource_uri) if resource_uri else None
        if resource and resource.contents:
            print("Resource contents:", resource.contents[0].text)

        prompt = await client.session.get_prompt("plan-vacation", {"destination": "Barcelona"})
        print("Prompt messages:", prompt.messages)


if __name__ == "__main__":
    asyncio.run(main())
