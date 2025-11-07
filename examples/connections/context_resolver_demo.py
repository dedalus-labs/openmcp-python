# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal demo showing ``Context.resolve_client`` in isolation.

Run with ``python examples/connections/context_resolver_demo.py``.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext

from openmcp import MCPServer, tool, get_context
from openmcp.context import RUNTIME_CONTEXT_KEY


class MemorySession:
    """Tiny session stub for invoking tools without transports."""

    async def send_notification(self, *args, **kwargs):  # pragma: no cover - demo helper
        return None

    async def send_log_message(self, *args, **kwargs):  # pragma: no cover - demo helper
        return None

    async def send_progress_notification(self, *args, **kwargs):  # pragma: no cover - demo helper
        return None


class DemoResolver:
    """Resolver stub returning a synthetic client string."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def resolve_client(self, handle: str, request_context: dict[str, object]) -> str:
        self.calls.append((handle, request_context))
        return f"client-for-{handle}"


async def main() -> None:
    server = MCPServer("context-demo")
    resolver = DemoResolver()
    server.set_connection_resolver(resolver)

    with server.binding():
        @tool(description="Return the resolver output for the provided connection handle")
        async def demo_tool(connection: str) -> str:
            ctx = get_context()
            return await ctx.resolve_client(connection)

    session = MemorySession()
    auth_context = SimpleNamespace(claims={"ddls:connectors": ["ddls:conn_demo"]})
    request = SimpleNamespace(scope={"openmcp.auth": auth_context})
    lifespan = {RUNTIME_CONTEXT_KEY: {"server": server, "resolver": resolver}}

    ctx = RequestContext(
        request_id="demo-1",
        meta=None,
        session=session,
        lifespan_context=lifespan,
        request=request,
    )

    token = request_ctx.set(ctx)
    try:
        result = await server.tools.call_tool("demo_tool", {"connection": "ddls:conn_demo"})
    finally:
        request_ctx.reset(token)

    print("Tool result:", result.content[0].text)
    print("Resolver payload:", resolver.calls[0][1])


if __name__ == "__main__":
    asyncio.run(main())
