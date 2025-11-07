# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Integration tests for Context.resolve_client wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from openmcp import MCPServer, tool, get_context
from openmcp.context import RUNTIME_CONTEXT_KEY
from ..helpers import RecordingSession, run_with_context


class DummyResolver:
    """Resolver stub capturing resolve_client invocations."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def resolve_client(self, handle: str, request_context: dict[str, object]) -> str:
        self.calls.append((handle, request_context))
        return f"client-for-{handle}"


@pytest.mark.anyio
async def test_context_resolve_client_invokes_registered_resolver() -> None:
    server = MCPServer("resolver-test")
    resolver = DummyResolver()
    server.set_connection_resolver(resolver)

    with server.binding():
        @tool(description="Resolve connection handle via context helper")
        async def use_connection(connection: str) -> str:
            ctx = get_context()
            client = await ctx.resolve_client(connection)
            return client

    session = RecordingSession("resolver-session")
    auth_context = SimpleNamespace(claims={"ddls:connectors": ["ddls:conn_demo"]})

    result = await run_with_context(
        session,
        server.tools.call_tool,
        "use_connection",
        {"connection": "ddls:conn_demo"},
        request_scope={"openmcp.auth": auth_context},
        lifespan_context={RUNTIME_CONTEXT_KEY: {"server": server, "resolver": resolver}},
    )

    assert result.content and result.content[0].text == "client-for-ddls:conn_demo"
    assert resolver.calls, "resolver should be invoked"
    handle, request_payload = resolver.calls[0]
    assert handle == "ddls:conn_demo"
    assert request_payload["openmcp.auth"] is auth_context
