# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

from typing import Any

from mcp.shared.exceptions import McpError
import pytest

from openmcp import MCPServer, types
from tests.helpers import run_with_context


class FakeSession:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.capable = True
        self.calls: list[types.ServerRequest] = []

    def check_client_capability(self, capability: types.ClientCapabilities) -> bool:  # type: ignore[override]
        return self.capable

    async def send_request(self, request, result_type):
        self.calls.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.anyio
async def test_elicitation_requires_capability() -> None:
    server = MCPServer("elicitation")
    session = FakeSession(types.ElicitResult(action="accept", content={}))
    session.capable = False

    params = types.ElicitRequestParams(
        message="Provide a value",
        requestedSchema={"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]},
    )

    with pytest.raises(McpError) as exc:
        await run_with_context(session, server.request_elicitation, params)
    assert exc.value.error.code == types.METHOD_NOT_FOUND


@pytest.mark.anyio
async def test_elicitation_happy_path_records_call() -> None:
    result = types.ElicitResult(action="accept", content={"value": "yes"})
    server = MCPServer("elicitation")
    session = FakeSession(result)

    params = types.ElicitRequestParams(
        message="Provide a value", requestedSchema={"type": "object", "properties": {"value": {"type": "string"}}}
    )

    response = await run_with_context(session, server.request_elicitation, params)
    assert response.action == "accept"
    assert session.calls
    assert isinstance(session.calls[0].root, types.ElicitRequest)


@pytest.mark.anyio
async def test_elicitation_propagates_client_error() -> None:
    error = McpError(types.ErrorData(code=-1, message="User declined"))
    server = MCPServer("elicitation")
    session = FakeSession(error)

    params = types.ElicitRequestParams(
        message="Provide a value", requestedSchema={"type": "object", "properties": {"value": {"type": "string"}}}
    )

    with pytest.raises(McpError) as exc:
        await run_with_context(session, server.request_elicitation, params)
    assert exc.value.error.message == "User declined"


@pytest.mark.anyio
async def test_elicitation_schema_validation() -> None:
    server = MCPServer("elicitation")
    session = FakeSession(types.ElicitResult(action="accept", content={}))

    bad_params = types.ElicitRequestParams(message="Provide", requestedSchema={"type": "object", "properties": {}})

    with pytest.raises(McpError):
        await run_with_context(session, server.request_elicitation, bad_params)
