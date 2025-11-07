# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Session-scoped authorization with dynamic tool visibility.

Demonstrates per-connection capability gating using MCP session identifiers
and dependency injection. Each client connection maintains a unique session ID
(see https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle#lifecycle-phases),
allowing server authors to enforce different authorization policies per authenticated user.

Pattern:
1. Store user identity keyed by `ctx.session_id` (set once per connection)
2. Define dependency function that extracts tier/role from session context
3. Gate tools with `enabled=Depends(require_role, get_tier)`

Dependencies are re-evaluated on every `tools/list` or `tools/call` request,
so tool visibility is dynamic—bob sees `[health_check]`, alice sees
`[health_check, premium_tool]`.

When to use this pattern:
- Multi-tenant servers where each client represents a different user
- Plan-based feature gating (free/pro/enterprise tiers)
- Role-based access control (admin/user/guest)
- Per-session feature flags

Context parameters are auto-injected via type hints—no need for
`Depends(get_context)`. The framework inspects signatures and supplies
`Context` at resolution time.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from openmcp import MCPServer, tool
from openmcp.client import open_connection
from openmcp.context import Context
from openmcp.server.dependencies import Depends
from openmcp.types import ClientRequest, ListToolsRequest, ListToolsResult

# Suppress SDK and server logs for cleaner demo output
for logger_name in ("mcp", "httpx", "uvicorn", "uvicorn.access", "uvicorn.error"):
    logging.getLogger(logger_name).setLevel(logging.CRITICAL)

SERVER_URL = "http://127.0.0.1:8000/mcp"
USERS = {"bob": "basic", "alice": "pro"}

# Maps MCP session ID to user ID (set once per connection)
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

    @tool(description="Public health check")
    def health_check() -> str:
        return "ok"

    @tool(description="Premium tool (Pro tier)", enabled=Depends(require_pro, get_tier), tags={"pro"})
    async def premium_tool() -> str:
        return "Access granted!"


async def demo() -> None:
    task = asyncio.create_task(
        server.serve(
            transport="streamable-http",
            verbose=False,
            log_level="critical",
            uvicorn_options={"access_log": False},
        )
    )
    await asyncio.sleep(0.1)
    try:
        for user_id, tier in USERS.items():
            async with open_connection(url=SERVER_URL) as client:
                # Map this session to the user (simulates auth middleware)
                session_id = client.session_id
                if session_id:
                    SESSION_USERS[session_id] = user_id

                result = await client.send_request(
                    ClientRequest(ListToolsRequest()), ListToolsResult
                )
            tools = ", ".join(t.name for t in result.tools) or "<none>"
            print(f"  - {user_id} ({tier}) → tools: {tools}")
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

if __name__ == "__main__":
    import sys
    try:
        asyncio.run(demo())
    except KeyboardInterrupt:
        print("Keyboard interrupt received, exiting...")
        sys.exit(0)
