# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""[DRAFT] Multi-server ambient registration pattern.

Demonstrates how to use ambient registration to share the same tool function
across multiple MCP server instances, each serving different transports or
configurations.

Run:
    uv run python examples/advanced/multi_server.py

Reference:
    - Ambient registration: docs/openmcp/ambient-registration.md
    - Tools capability: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, tool


# Shared tool function that will be registered on multiple servers
async def calculate(operation: str, a: float, b: float) -> float:
    """Perform basic arithmetic operations."""
    operations = {"add": a + b, "subtract": a - b, "multiply": a * b, "divide": a / b if b != 0 else float("inf")}
    return operations.get(operation, 0.0)


# Create two servers with different configurations
public_server = MCPServer("public-calc", instructions="Public calculator service", transport="streamable-http")

internal_server = MCPServer("internal-calc", instructions="Internal calculator with extended ops", transport="stdio")


# Register shared tool on public server with minimal ops
with public_server.binding():

    @tool(description="Basic calculator (add, subtract)")
    async def calc_basic(operation: str, a: float, b: float) -> float:
        if operation not in ("add", "subtract"):
            raise ValueError("Only add and subtract allowed on public server")
        return await calculate(operation, a, b)


# Register full suite on internal server
with internal_server.binding():

    @tool(description="Full calculator (add, subtract, multiply, divide)")
    async def calc_full(operation: str, a: float, b: float) -> float:
        return await calculate(operation, a, b)

    @tool(description="Power operation")
    async def power(base: float, exponent: float) -> float:
        """Raise base to the power of exponent."""
        return base**exponent


# Pattern: conditional registration based on environment
def register_tools(server: MCPServer, enable_admin: bool = False) -> None:
    """Dynamically register tools based on server configuration."""
    with server.binding():

        @tool(description="Echo a message")
        async def echo(message: str) -> str:
            return message

        if enable_admin:

            @tool(description="Admin: reset server state")
            async def reset() -> str:
                """This would reset internal state in a real implementation."""
                return "Server state reset"


async def main() -> None:
    """Run both servers concurrently on different transports."""
    # Register conditional tools
    register_tools(public_server, enable_admin=False)
    register_tools(internal_server, enable_admin=True)

    async with asyncio.TaskGroup() as tg:
        # Public server on HTTP port 8001
        tg.create_task(public_server.serve(host="127.0.0.1", port=8001))
        # Internal server on stdio (would typically be spawned by a client)
        # Commented out to avoid blocking - in production you'd run one or the other
        # tg.create_task(internal_server.serve())

    # Production pattern: select transport at runtime
    # server = public_server if config.public else internal_server
    # await server.serve()


if __name__ == "__main__":
    print("Multi-server example: public-calc on :8001, internal-calc on stdio")
    print("Public server has: calc_basic, echo")
    print("Internal server has: calc_full, power, echo, reset")
    # asyncio.run(main())  # Uncomment to actually run
