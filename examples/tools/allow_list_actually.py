"""Minimal allow-list demo using ``Depends`` with session-scoped authorization.

Demonstrates how to use MCP session IDs to track user identity across requests.
Each client connection represents a different authenticated user session.
"""

import asyncio
from contextlib import suppress

from openmcp import Context, Depends, MCPServer, tool, types
from openmcp.client import open_connection

SERVER_URL = "http://127.0.0.1:8000/mcp"
USERS = {"bob": "basic", "alice": "pro"}

# Maps MCP session ID → user ID (set once per connection)
SESSION_USERS: dict[str, str] = {}


def get_tier(ctx: Context) -> str:
    """Extract user tier from session-scoped storage."""
    session_id = ctx.session_id
    if session_id is None:
        return "basic"
    user_id = SESSION_USERS.get(session_id, "bob")
    return USERS[user_id]


def require_pro(tier: str) -> bool:
    return tier == "pro"


server = MCPServer("allow-list-demo", transport="streamable-http")
with server.binding():

    @tool()
    def health_check() -> str:
        return "ok"

    @tool(enabled=Depends(require_pro, get_tier))
    async def premium_tool() -> str:
        return "Access granted!"


async def main():
    task = asyncio.create_task(server.serve(transport="streamable-http"))
    await asyncio.sleep(0.2)

    try:
        for user, tier in USERS.items():
            async with open_connection(url=SERVER_URL) as client:
                # Map this session to the user (simulates auth middleware)
                session_id = client.session_id
                if session_id:
                    SESSION_USERS[session_id] = user

                result = await client.send_request(
                    types.ClientRequest(types.ListToolsRequest()), types.ListToolsResult
                )
            tools = ", ".join(t.name for t in result.tools) or "<none>"
            print(f"{user} ({tier}) → {tools}")
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    asyncio.run(main())
