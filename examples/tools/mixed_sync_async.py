# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Sync vs Async tools demonstration.

Shows that OpenMCP transparently handles both synchronous and asynchronous
tool functions via utils.maybe_await_with_args. The framework inspects
callables at invocation time and awaits only when necessary.

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

Usage:
    uv run python examples/tools/mixed_sync_async.py

    # In another terminal:
    curl -X POST http://127.0.0.1:8000/mcp \
      -H "Content-Type: application/json" \
      -d '{"jsonrpc": "2.0", "method": "tools/list", "id": 1}'
"""

from __future__ import annotations

import asyncio
import json
import time

from openmcp import MCPServer, tool


server = MCPServer(name="mixed-sync-async-demo")


with server.binding():

    @tool(description="Synchronous computation - no I/O, CPU-bound")
    def calculate_fibonacci(n: int) -> dict[str, int]:
        """Pure function: deterministic, no side effects, instant execution.

        Use sync when:
        - Pure computation (math, string ops, data transforms)
        - No I/O (network, disk, subprocess)
        - Sub-millisecond execution time
        """
        if n < 0:
            raise ValueError("n must be non-negative")
        if n <= 1:
            return {"result": n}

        a, b = 0, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return {"result": b}

    @tool(description="Synchronous validation - fast, deterministic")
    def validate_email(email: str) -> dict[str, str]:
        """Simple validation logic - no async needed.

        Framework calls this directly without await overhead.
        """
        is_valid = "@" in email and "." in email.split("@")[-1]
        return {
            "valid": str(is_valid),
            "reason": "Valid format" if is_valid else "Missing @ or domain"
        }

    @tool(description="Asynchronous I/O - network fetch simulation")
    async def fetch_weather(city: str) -> dict[str, str | float]:
        """Network I/O requires async for concurrency.

        Use async when:
        - Network requests (HTTP, gRPC, database)
        - File I/O (reading logs, processing large files)
        - Long-running operations (>100ms)
        - Need to yield control during waits
        """
        await asyncio.sleep(0.5)  # Simulate API latency
        return {
            "city": city,
            "temperature": 72.5,
            "condition": "sunny",
            "source": "mock-api"
        }

    @tool(description="Asynchronous database query simulation")
    async def query_user_data(user_id: int) -> dict[str, str | int]:
        """Database access is inherently async in Python.

        Real implementation would use asyncpg, motor, etc.
        """
        await asyncio.sleep(0.2)  # Simulate query time
        return {
            "user_id": user_id,
            "username": f"user_{user_id}",
            "status": "active",
            "last_login": "2025-01-03T12:00:00Z"
        }

    @tool(description="Hybrid: sync preprocessing + async I/O")
    async def process_and_store(data: str, destination: str) -> dict[str, str | int]:
        """Common pattern: validate sync, then async I/O.

        Sync validation is fast (no await needed internally),
        but the tool itself is async for the storage step.
        """
        # Sync preprocessing
        normalized = data.strip().upper()
        size = len(normalized)

        # Async storage simulation
        await asyncio.sleep(0.1)

        return {
            "status": "stored",
            "destination": destination,
            "bytes": size,
            "checksum": f"sha256:{hash(normalized) & 0xFFFFFFFF:08x}"
        }


async def demo_invocation() -> None:
    """Show that both sync and async tools work seamlessly."""
    print("=== Registered Tools ===")
    print("Tools registered (mix of sync and async):")
    print("  - calculate_fibonacci (sync)")
    print("  - validate_email (sync)")
    print("  - fetch_weather (async)")
    print("  - query_user_data (async)")
    print("  - process_and_store (async)")

    print("\n=== Framework handles both transparently ===")
    print("All tools invoked via same call_tool API, regardless of sync/async.")


async def main() -> None:
    print("Starting Mixed Sync/Async Server\n")

    # Run demo before starting server
    await demo_invocation()

    print("\n=== Server Running ===")
    print("Listening on http://127.0.0.1:8000/mcp")
    print("Try: curl -X POST http://127.0.0.1:8000/mcp \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -d '{\"jsonrpc\": \"2.0\", \"method\": \"tools/list\", \"id\": 1}'")

    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
