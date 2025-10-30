# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal end-to-end MCP server demo.

This example shows how to wire tools, resources, prompts, and transports using
OpenMCP. It aligns with the concepts in ``docs/mcp/core/understanding-mcp-servers``.

Usage::

    uv run python examples/hello_trip/server.py --transport stdio

The server exposes:

* Tool ``plan_trip`` – echoes a travel plan summary
* Resource ``travel://tips/barcelona`` – static travel tips
* Prompt ``plan-vacation`` – demonstrates prompt rendering

Try it alongside ``client.py`` to see the full flow.
"""

from __future__ import annotations

import asyncio
from typing import Any

from openmcp import MCPServer, get_context, prompt, resource, tool


server = MCPServer("hello-trip")

with server.binding():

    @tool(
        description="Summarize a travel plan",
        tags={"travel", "demo"},
        output_schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}, "suggestion": {"type": "string"}},
            "required": ["summary"],
        },
    )
    async def plan_trip(destination: str, days: int, budget: float) -> dict[str, Any]:
        ctx = get_context()
        await ctx.info("planning trip", data={"destination": destination, "days": days, "budget": budget})

        async with ctx.progress(total=3) as tracker:
            await tracker.advance(1, message="Gathering highlights")
            await asyncio.sleep(0)
            await tracker.advance(1, message="Estimating costs")
            await asyncio.sleep(0)
            await tracker.advance(1, message="Summarising itinerary")

        summary = f"Plan: {days} days in {destination} with budget ${budget:.2f}."
        result = {"summary": summary, "suggestion": "Remember to book tickets early!"}
        await ctx.debug("plan complete", data=result)
        return result

    @resource(uri="travel://tips/barcelona", name="Barcelona Tips", mime_type="text/plain")
    def barcelona_tips() -> str:
        return "Visit Sagrada Família, explore the Gothic Quarter, and enjoy tapas on La Rambla."

    @prompt(name="plan-vacation", description="Guide the model through planning a trip")
    def plan_vacation_prompt(args: dict[str, str]) -> list[dict[str, str]]:
        destination = args.get("destination", "unknown destination")
        return [
            {
                "role": "assistant",
                "content": "You are a helpful travel planner. Summarize the itinerary and call tools if needed.",
            },
            {"role": "user", "content": f"Plan a vacation to {destination}."},
        ]


async def main(transport: str = "streamable-http") -> None:
    await server.serve(transport=transport)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run the hello-trip MCP server")
    parser.add_argument(
        "--transport", default="streamable-http", choices=["streamable-http", "stdio"], help="Transport to use"
    )
    args = parser.parse_args()

    asyncio.run(main(args.transport))
