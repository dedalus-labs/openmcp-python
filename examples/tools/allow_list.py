# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Plan-gated tools using `Depends`-based allow-lists.

The MCP spec only requires that advertised tools actually work; it leaves the
allow-list rules to the server.  This example hides a premium tool for basic
users by expressing the business rule with :class:`openmcp.Depends`.

Run::

    uv run python examples/tools/allow_list.py

The script spins up a Streamable HTTP server on ``127.0.0.1:8000/mcp`` and
calls ``tools/list`` for both plan tiers to show how :class:`openmcp.Depends`
controls visibility.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass

from openmcp import MCPServer, Depends, tool, types
from openmcp.client import open_connection


server = MCPServer(name="allow-list-demo", transport="streamable-http")
SERVER_URL = "http://127.0.0.1:8000/mcp"


@dataclass(frozen=True)
class User:
    tier: str


USERS: dict[str, User] = {"bob": User(tier="basic"), "alice": User(tier="pro")}
DEFAULT_USER_ID = "bob"
ACTIVE_USER_ID = DEFAULT_USER_ID


def get_current_user() -> User | None:
    """This might be a database call."""
    return USERS.get(ACTIVE_USER_ID)


def require_pro(user: User | None) -> bool:
    """Some business logic."""
    return bool(user and user.tier == "pro")


with server.binding():

    @tool(description="Public health check")
    def health_check() -> str:
        return "ok"

    @tool(description="Premium tool (Pro tier)", enabled=Depends(require_pro, get_current_user), tags={"pro"})
    async def premium_tool() -> str:
        """Tier-gated tool call."""
        return "Access granted!"


async def list_tools_for(user_id: str) -> list[str]:
    """Return the tool names visible to *user_id* via a live handshake."""

    global ACTIVE_USER_ID
    ACTIVE_USER_ID = user_id
    async with open_connection(url=SERVER_URL) as client:
        request = types.ClientRequest(types.ListToolsRequest())
        result = await client.send_request(request, types.ListToolsResult)
        tools = [tool.name for tool in result.tools]
    ACTIVE_USER_ID = DEFAULT_USER_ID
    return tools


async def run_demo() -> None:
    print("Starting allow-list demo server on http://127.0.0.1:8000/mcp")
    server_task = asyncio.create_task(server.serve(transport="streamable-http"))
    await asyncio.sleep(0.2)  # allow the transport to bind

    for user_id, user in USERS.items():
        tools = await list_tools_for(user_id)
        tool_list = ", ".join(tools) if tools else "<none>"
        print(f"  - {user_id} ({user.tier}) → tools: {tool_list}")

    server_task.cancel()
    with suppress(asyncio.CancelledError):
        await server_task
    print("Demo complete.")


if __name__ == "__main__":
    asyncio.run(run_demo())
