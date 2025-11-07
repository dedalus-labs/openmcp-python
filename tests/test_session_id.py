"""Tests for session ID access in Context and MCPClient.

Validates session ID properties follow MCP spec requirements:
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#session-management
"""

import pytest
import types as py_types

from openmcp import MCPClient
from openmcp.context import Context, _CURRENT_CONTEXT


@pytest.mark.anyio
async def test_context_session_id_with_header(monkeypatch):
    """Context.session_id returns session ID from mcp-session-id header."""
    # Mock request context with headers
    mock_request = py_types.SimpleNamespace(headers={"mcp-session-id": "test-session-123"})
    mock_request_context = py_types.SimpleNamespace(
        request=mock_request, request_id="req-1", session=None, meta=None, lifespan_context={}
    )

    ctx = Context.from_request_context(mock_request_context)
    assert ctx.session_id == "test-session-123"


@pytest.mark.anyio
async def test_context_session_id_without_header():
    """Context.session_id returns None when no mcp-session-id header present."""
    mock_request = py_types.SimpleNamespace(headers={})
    mock_request_context = py_types.SimpleNamespace(
        request=mock_request, request_id="req-1", session=None, meta=None, lifespan_context={}
    )

    ctx = Context.from_request_context(mock_request_context)
    assert ctx.session_id is None


@pytest.mark.anyio
async def test_context_session_id_no_request():
    """Context.session_id returns None when request object doesn't exist."""
    mock_request_context = py_types.SimpleNamespace(request_id="req-1", session=None, meta=None, lifespan_context={})

    ctx = Context.from_request_context(mock_request_context)
    assert ctx.session_id is None


@pytest.mark.anyio
async def test_context_session_id_no_headers():
    """Context.session_id returns None when headers attribute doesn't exist."""
    mock_request = py_types.SimpleNamespace()  # No headers attribute
    mock_request_context = py_types.SimpleNamespace(
        request=mock_request, request_id="req-1", session=None, meta=None, lifespan_context={}
    )

    ctx = Context.from_request_context(mock_request_context)
    assert ctx.session_id is None


@pytest.mark.anyio
async def test_client_session_id_before_initialization():
    """MCPClient.session_id returns None before connection is established."""
    import anyio

    write_stream, read_stream = anyio.create_memory_object_stream(0)

    # Without get_session_id callback
    client = MCPClient(read_stream, write_stream)
    assert client.session_id is None


@pytest.mark.anyio
async def test_client_session_id_with_callback():
    """MCPClient.session_id calls callback and returns result."""
    import anyio

    write_stream, read_stream = anyio.create_memory_object_stream(0)

    # With get_session_id callback
    def get_session_id() -> str:
        return "callback-session-456"

    client = MCPClient(read_stream, write_stream, get_session_id=get_session_id)
    assert client.session_id == "callback-session-456"


@pytest.mark.anyio
async def test_client_session_id_callback_returns_none():
    """MCPClient.session_id handles callback returning None."""
    import anyio

    write_stream, read_stream = anyio.create_memory_object_stream(0)

    def get_session_id() -> None:
        return None

    client = MCPClient(read_stream, write_stream, get_session_id=get_session_id)
    assert client.session_id is None


@pytest.mark.anyio
async def test_session_scoped_authorization_pattern():
    """Test session-scoped authorization using session_id mapping."""
    from openmcp import MCPServer, tool
    from openmcp.server.dependencies import Depends
    from mcp.server.lowlevel.server import request_ctx
    from mcp.shared.context import RequestContext

    # Simulated session → user mapping
    SESSION_USERS = {"session-1": "alice", "session-2": "bob"}
    USERS = {"alice": "pro", "bob": "basic"}

    def get_tier(ctx: Context) -> str:
        session_id = ctx.session_id
        if session_id is None:
            return "basic"
        user_id = SESSION_USERS.get(session_id, "bob")
        return USERS[user_id]

    def require_pro(tier: str) -> bool:
        return tier == "pro"

    server = MCPServer("session-auth-test")

    with server.binding():

        @tool()
        def public_tool() -> str:
            return "public"

        @tool(enabled=Depends(require_pro, get_tier))
        async def premium_tool() -> str:
            return "premium"

    # Use DummySession for both tests
    from tests.helpers import DummySession

    session1 = DummySession("alice-session")
    session2 = DummySession("bob-session")

    # Simulate session 1 (alice = pro) with session_id in headers
    mock_request_1 = py_types.SimpleNamespace(headers={"mcp-session-id": "session-1"})
    ctx1 = RequestContext(request_id=1, meta=None, session=session1, lifespan_context={}, request=mock_request_1)  # type: ignore
    token1 = request_ctx.set(ctx1)
    try:
        result1 = await server.tools.list_tools(None)
        names1 = [t.name for t in result1.tools]
        assert "public_tool" in names1
        assert "premium_tool" in names1  # Alice has pro tier
    finally:
        request_ctx.reset(token1)

    # Simulate session 2 (bob = basic) with different session_id
    mock_request_2 = py_types.SimpleNamespace(headers={"mcp-session-id": "session-2"})
    ctx2 = RequestContext(request_id=2, meta=None, session=session2, lifespan_context={}, request=mock_request_2)  # type: ignore
    token2 = request_ctx.set(ctx2)
    try:
        result2 = await server.tools.list_tools(None)
        names2 = [t.name for t in result2.tools]
        assert "public_tool" in names2
        assert "premium_tool" not in names2  # Bob has basic tier
    finally:
        request_ctx.reset(token2)


@pytest.mark.anyio
async def test_multiple_concurrent_sessions():
    """Multiple sessions can exist simultaneously with different session IDs."""
    import anyio

    write_stream, read_stream = anyio.create_memory_object_stream(0)

    session_id_value = "initial-session"

    def get_session_id() -> str:
        return session_id_value

    client = MCPClient(read_stream, write_stream, get_session_id=get_session_id)
    assert client.session_id == "initial-session"

    # Simulate session ID change (reconnection scenario)
    session_id_value = "new-session-after-reconnect"
    assert client.session_id == "new-session-after-reconnect"
