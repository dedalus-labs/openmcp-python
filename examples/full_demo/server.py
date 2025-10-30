"""Full capability demo server.

Run with:
    uv run python examples/full_demo/server.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import anyio

from openmcp import MCPServer, NotificationFlags, completion, get_context, prompt, resource, tool
from openmcp import types

server = MCPServer(
    "full-demo",
    instructions="Demonstrates tools/resources/prompts/sampling/elicitation",
    notification_flags=NotificationFlags(
        prompts_changed=True,
        resources_changed=True,
        tools_changed=True,
    ),
)


with server.binding():

    @tool(description="Adds numbers")
    async def add(a: int, b: int) -> int:
        ctx = get_context()
        await ctx.debug("adding", data={"a": a, "b": b})
        async with ctx.progress(total=1) as tracker:
            await tracker.advance(1, message="computed")
        return a + b

    @tool(description="Sleeps for N seconds")
    async def sleep(seconds: float = 1.0) -> str:
        ctx = get_context()
        await ctx.info("sleep start", data={"seconds": seconds})
        async with ctx.progress(total=seconds) as tracker:
            remaining = seconds
            while remaining > 0:
                await anyio.sleep(1.0)
                remaining -= 1.0
                await tracker.advance(1.0, message=f"remaining {max(remaining, 0):.0f}s")
        return "slept"

    @resource("resource://time", mime_type="text/plain")
    def current_time() -> str:
        return datetime.utcnow().isoformat() + "Z"

    @prompt(
        name="plan-vacation",
        description="Guide the model through planning a vacation",
        arguments=[
            types.PromptArgument(name="destination", description="Where to travel", required=True),
        ],
    )
    def plan_prompt(args: dict[str, str]) -> list[dict[str, str]]:
        destination = args.get("destination", "unknown")
        return [
            {
                "role": "assistant",
                "content": "You are a helpful planner. Use tools as needed.",
            },
            {
                "role": "user",
                "content": f"Plan a trip to {destination}.",
            },
        ]

    @completion(prompt="plan-vacation")
    async def plan_completion(argument: types.CompletionArgument, context: types.CompletionContext | None):
        return ["This is a synthetic completion."]


@completion(prompt="plan-vacation")
async def plan_completion(argument: types.CompletionArgument, context: types.CompletionContext | None):
    return ["This is a synthetic completion."]


async def sampling_handler(ref: Any, params: types.CreateMessageRequestParams, context: Any) -> types.CreateMessageResult:
    return types.CreateMessageResult(
        content=[types.TextContent(type="text", text="Sampled by demo server")]
    )


server.sampling.create_message = sampling_handler  # demonstration override


async def elicitation_handler(ref: Any, params: types.ElicitRequestParams, context: Any) -> types.ElicitResult:
    return types.ElicitResult(fields={"confirm": True})


server.elicitation.create = elicitation_handler


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
