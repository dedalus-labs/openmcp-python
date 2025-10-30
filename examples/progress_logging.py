"""Standalone progress/logging demo."""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, get_context, tool

server = MCPServer("progress-demo")


with server.binding():

    @tool(description="Processes a batch")
    async def process(batch: list[str]) -> str:
        ctx = get_context()
        await ctx.info("batch start", data={"size": len(batch)})
        async with ctx.progress(total=len(batch)) as tracker:
            for item in batch:
                await tracker.advance(1, message=f"done {item}")
        await ctx.info("batch complete")
        return "ok"


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
