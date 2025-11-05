# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import pytest

from openmcp import MCPServer, tool


def _bootstrap_server(*, allow_dynamic: bool) -> MCPServer:
    server = MCPServer("dynamic-test", allow_dynamic_tools=allow_dynamic)

    with server.binding():

        @tool()
        def ping() -> str:
            return "pong"

    return server


@pytest.mark.anyio
async def test_static_server_rejects_runtime_mutation() -> None:
    server = _bootstrap_server(allow_dynamic=False)
    server._runtime_started = True  # simulate post-startup state

    with pytest.raises(RuntimeError):
        with server.binding():

            @tool()
            def extra() -> str:  # pragma: no cover - executed in raising branch
                return "extra"


@pytest.mark.anyio
async def test_dynamic_server_requires_notification() -> None:
    server = _bootstrap_server(allow_dynamic=True)
    server._runtime_started = True

    with server.binding():

        @tool()
        def search(query: str) -> str:
            return f"results for {query}"

    assert server._tool_mutation_pending_notification is True

    await server.notify_tools_list_changed()
    assert server._tool_mutation_pending_notification is False
