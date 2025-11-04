# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Runtime tool filtering with allow-lists.

Demonstrates:
- Conditional tool registration via enabled= callback
- Environment-based feature flags
- Dynamic tool availability
- Server configuration for selective tool exposure

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

Usage:
    # Enable all tools
    uv run python examples/tools/allow_list.py

    # Enable only safe tools
    TOOL_MODE=safe uv run python examples/tools/allow_list.py

    # Enable only admin tools
    TOOL_MODE=admin uv run python examples/tools/allow_list.py
"""

from __future__ import annotations

import asyncio
import os

from openmcp import MCPServer, tool


server = MCPServer("allow-list-demo")


def is_safe_mode(srv: MCPServer) -> bool:
    """Check if server allows safe operations."""
    mode = os.getenv("TOOL_MODE", "all")
    return mode in ("safe", "all")


def is_admin_mode(srv: MCPServer) -> bool:
    """Check if server allows admin operations."""
    mode = os.getenv("TOOL_MODE", "all")
    return mode in ("admin", "all")


with server.binding():

    @tool(description="Public tool available in all modes")
    def ping() -> str:
        """Always available regardless of TOOL_MODE."""
        return "pong"

    @tool(description="Safe read operation", enabled=is_safe_mode, tags={"safe"})
    def read_data(key: str) -> str:
        """Only available when TOOL_MODE=safe or all."""
        return f"data for {key}"

    @tool(description="Admin-only deletion", enabled=is_admin_mode, tags={"admin", "dangerous"})
    async def delete_data(key: str) -> str:
        """Only available when TOOL_MODE=admin or all."""
        return f"deleted {key}"


async def main() -> None:
    mode = os.getenv("TOOL_MODE", "all")
    print(f"Starting server in mode: {mode}")
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
