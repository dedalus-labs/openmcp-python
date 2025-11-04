# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Basic tool example with automatic schema inference.

Demonstrates:
- Minimal tool registration with @tool decorator
- Automatic JSON Schema generation from type hints
- Sync and async tool functions
- Simple return types (str, dict, list)

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

Usage:
    uv run python examples/tools/basic_tool.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, tool


server = MCPServer("basic-tools")


with server.binding():

    @tool(description="Add two integers")
    def add(a: int, b: int) -> int:
        """Schema inferred: a and b as required integers, returns int."""
        return a + b

    @tool(description="Greet a user by name")
    async def greet(name: str) -> str:
        """Async tools work identically. Schema: name (required str) → str."""
        return f"Hello, {name}!"

    @tool(description="Return structured data")
    def get_user_info(user_id: int) -> dict[str, str | int]:
        """Schema infers dict[str, str | int] as output type."""
        return {"id": user_id, "username": f"user_{user_id}", "status": "active"}


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
