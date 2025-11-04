# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Error handling and validation patterns.

Demonstrates:
- Input validation with ValueError
- Custom error messages via CallToolResult
- Structured error responses
- Logging errors with ctx.error()

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools
https://modelcontextprotocol.io/specification/2025-06-18/basic/jsonrpc

Usage:
    uv run python examples/tools/error_handling.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, get_context, tool, types


server = MCPServer("error-handling")


with server.binding():

    @tool(description="Divide two numbers with validation")
    async def divide(a: float, b: float) -> float:
        """Raise ValueError for invalid inputs (zero division).

        Framework catches exceptions and wraps them in CallToolResult with isError=True.
        """
        if b == 0:
            ctx = get_context()
            await ctx.error("division by zero", data={"a": a, "b": b})
            raise ValueError("Cannot divide by zero")
        return a / b

    @tool(description="Fetch user with explicit error result")
    async def fetch_user(user_id: int) -> types.CallToolResult | dict[str, str]:
        """Return CallToolResult explicitly for richer error control."""
        ctx = get_context()

        if user_id <= 0:
            await ctx.warning("invalid user_id", data={"user_id": user_id})
            return types.CallToolResult(
                content=[types.TextContent(type="text", text="User ID must be positive")],
                isError=True,
            )

        # Simulate not found
        if user_id == 999:
            await ctx.info("user not found", data={"user_id": user_id})
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"User {user_id} not found")],
                isError=True,
            )

        return {"id": str(user_id), "name": f"User {user_id}"}


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
