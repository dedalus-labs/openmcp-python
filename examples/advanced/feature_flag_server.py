"""Feature-flagged tool exposure using dynamic mode.

Run with ``uv run`` and toggle the feature flag via the ``set_feature`` coroutine.
Dynamic behaviour requires ``allow_dynamic_tools=True`` and callers MUST emit
``notifications/tools/list_changed`` after each mutation.
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, tool


server = MCPServer("feature-flagged", allow_dynamic_tools=True)
_flag_enabled = False


def bootstrap() -> MCPServer:
    """Register the baseline tool set.

    Returns:
        Configured ``MCPServer`` instance.
    """
    with server.binding():

        @tool(description="Ping the server")
        def ping() -> str:
            return "pong"

    return server


async def set_feature(*, enabled: bool = False) -> None:
    """Toggle the experimental search tool at runtime."""
    global _flag_enabled
    _flag_enabled = enabled

    with server.binding():

        @tool(description="Ping the server")
        def ping() -> str:
            return "pong"

        if _flag_enabled:

            @tool(description="Experimental semantic search")
            async def search(query: str) -> str:
                return f"results for {query}"

    await server.notify_tools_list_changed()


async def main() -> None:
    """Launch the server in STDIO mode for development."""
    bootstrap()
    print(
        "Serving feature-flagged tools. Toggle by calling "
        "`await set_feature(True|False)` from another task or REPL."
    )
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve_stdio(validate=False))


if __name__ == "__main__":
    asyncio.run(main())


__all__ = ["bootstrap", "server", "set_feature"]
