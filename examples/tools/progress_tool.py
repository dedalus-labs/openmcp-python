# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Long-running tool with progress notifications.

Demonstrates:
- Progress tracking with ctx.progress()
- Async operations with progress updates
- Structured logging (info/debug)
- Progress token requirement (client must supply _meta.progressToken)

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress

Usage:
    uv run python examples/tools/progress_tool.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, get_context, tool


server = MCPServer("progress-demo")


with server.binding():

    @tool(description="Process a batch of items with progress")
    async def batch_process(items: list[str], delay: float = 0.5) -> dict[str, int]:
        """Report progress for each item processed.

        The client must supply _meta.progressToken or ctx.progress() raises ValueError.
        """
        ctx = get_context()
        await ctx.info("batch started", data={"count": len(items)})

        processed = 0
        async with ctx.progress(total=len(items)) as tracker:
            for item in items:
                # Simulate work
                await asyncio.sleep(delay)
                processed += 1
                await tracker.advance(1, message=f"processed {item}")

        await ctx.info("batch complete", data={"processed": processed})
        return {"total": len(items), "processed": processed}


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
