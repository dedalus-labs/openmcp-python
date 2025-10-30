# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import asyncio
from typing import Any

from mcp.shared.exceptions import McpError
import pytest

from openmcp import MCPServer, types
from tests.helpers import DummySession, run_with_context


class FakeSession(DummySession):
    def __init__(self) -> None:
        super().__init__("sampling")
        self.capable = True
        self.requests: list[types.ServerRequest] = []
        self.result = types.CreateMessageResult(
            role="assistant", content=types.TextContent(type="text", text="ok"), model="demo", stopReason="endTurn"
        )

    def check_client_capability(self, capability: types.ClientCapabilities) -> bool:  # type: ignore[override]
        return self.capable

    async def send_request(
        self, request: types.ServerRequest, result_type: type[Any], *, progress_callback=None
    ) -> Any:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.anyio
async def test_sampling_missing_capability_raises_method_not_found() -> None:
    server = MCPServer("sampling")
    session = FakeSession()
    session.capable = False

    params = types.CreateMessageRequestParams(
        messages=[types.SamplingMessage(role="user", content=types.TextContent(type="text", text="hi"))], maxTokens=10
    )

    with pytest.raises(McpError) as exc:
        await run_with_context(session, server.request_sampling, params)
    assert exc.value.error.code == types.METHOD_NOT_FOUND


@pytest.mark.anyio
async def test_sampling_successful_roundtrip_records_request() -> None:
    server = MCPServer("sampling")
    session = FakeSession()

    params = types.CreateMessageRequestParams(
        messages=[types.SamplingMessage(role="user", content=types.TextContent(type="text", text="hello"))],
        maxTokens=32,
    )

    result = await run_with_context(session, server.request_sampling, params)
    assert isinstance(result, types.CreateMessageResult)
    assert session.requests
    sent = session.requests[0].root
    assert isinstance(sent, types.CreateMessageRequest)
    assert sent.params.maxTokens == 32


@pytest.mark.anyio
async def test_sampling_propagates_client_error() -> None:
    server = MCPServer("sampling")
    session = FakeSession()
    session.result = McpError(types.ErrorData(code=-1, message="User rejected sampling request"))

    params = types.CreateMessageRequestParams(
        messages=[types.SamplingMessage(role="user", content=types.TextContent(type="text", text="hello"))],
        maxTokens=32,
    )

    with pytest.raises(McpError) as exc:
        await run_with_context(session, server.request_sampling, params)
    assert exc.value.error.message == "User rejected sampling request"


@pytest.mark.anyio
async def test_sampling_timeout_triggers_circuit_breaker() -> None:
    server = MCPServer("sampling")

    session = FakeSession()

    async def slow_send(request, result_type, progress_callback=None):
        await asyncio.sleep(1.0)
        return session.result

    session.send_request = slow_send  # type: ignore[assignment]

    params = types.CreateMessageRequestParams(
        messages=[types.SamplingMessage(role="user", content=types.TextContent(type="text", text="slow"))], maxTokens=4
    )

    server.sampling._timeout = 0.01  # type: ignore[attr-defined]

    with pytest.raises(McpError) as exc:
        await run_with_context(session, server.request_sampling, params)
    assert exc.value.error.code == types.INTERNAL_ERROR
