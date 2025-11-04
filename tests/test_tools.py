# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from mcp.shared.exceptions import McpError
import pytest

from openmcp import NotificationFlags, types
from openmcp.server import MCPServer
from openmcp.tool import tool
from openmcp.utils.schema import resolve_output_schema
from tests.helpers import DummySession, run_with_context


@pytest.mark.asyncio
async def test_binding_registers_tools():
    server = MCPServer("demo")

    with server.binding():

        @tool(description="Adds two numbers")
        def add(a: int, b: int) -> int:
            return a + b

    assert "add" in server.tool_names
    assert server.add(2, 3) == 5  # type: ignore[attr-defined]

    result = await server.invoke_tool("add", a=4, b=7)
    assert not result.isError
    assert result.content
    assert result.content[0].text == "11"
    assert result.structuredContent == {"result": 11}


@pytest.mark.asyncio
async def test_allowlist_controls_visibility():
    server = MCPServer("demo")
    server.allow_tools(["slow"])

    with server.binding():

        @tool()
        def add(a: int, b: int) -> int:
            return a + b

        @tool()
        def slow() -> str:
            return "ok"

    assert "add" not in server.tool_names
    assert "slow" in server.tool_names

    server.allow_tools(["add"])
    server.register_tool(add)  # type: ignore[arg-type]
    assert "add" in server.tool_names
    result = await server.invoke_tool("add", a=1, b=2)
    assert result.content[0].text == "3"
    assert result.structuredContent == {"result": 3}


@pytest.mark.asyncio
async def test_registering_outside_binding():
    server = MCPServer("demo")

    @tool(description="Multiply numbers")
    def multiply(a: int, b: int) -> int:
        return a * b

    assert "multiply" not in server.tool_names

    server.register_tool(multiply)
    assert "multiply" in server.tool_names
    result = await server.invoke_tool("multiply", a=3, b=4)
    assert result.content[0].text == "12"
    assert result.structuredContent == {"result": 12}


@pytest.mark.asyncio
async def test_serve_dispatch(monkeypatch):
    http_server = MCPServer("demo-http")
    stdio_server = MCPServer("demo-stdio", transport="stdio")

    called_http: dict[str, Any] = {}
    called_stdio: dict[str, Any] = {}

    async def fake_http(**kwargs: Any):
        called_http["kwargs"] = kwargs

    async def fake_stdio(**kwargs: Any):
        called_stdio["kwargs"] = kwargs

    monkeypatch.setattr(http_server, "serve_streamable_http", fake_http)
    monkeypatch.setattr(stdio_server, "serve_stdio", fake_stdio)

    await http_server.serve(host="0.0.0.0")
    assert called_http == {"kwargs": {"host": "0.0.0.0"}}

    await http_server.serve(transport="streamable-http", port=9999)
    assert called_http == {"kwargs": {"port": 9999}}

    await stdio_server.serve()
    assert called_stdio == {"kwargs": {}}

    await stdio_server.serve(transport="stdio", stateless=True)
    assert called_stdio == {"kwargs": {"stateless": True}}

    with pytest.raises(ValueError):
        await http_server.serve(transport="unknown")


def test_type_adapter_schema():
    server = MCPServer("schema")

    with server.binding():

        @tool()
        def analytics(a: int, count: int = 1, tags: list[str] | None = None):
            return a

    schema = server.tools.definitions["analytics"].inputSchema
    props = schema["properties"]

    assert schema["type"] == "object"
    assert schema["required"] == ["a"]
    assert props["a"]["type"] in {"integer", "number"}
    assert props["count"]["type"] in {"integer", "number"}
    assert props["count"].get("default") == 1
    tags = props["tags"]
    assert any(item.get("type") == "array" for item in tags.get("anyOf", []))


@pytest.mark.anyio
async def test_tools_list_pagination():
    server = MCPServer("tools-pagination")

    for idx in range(120):

        def make_tool(i: int):
            def tool_fn(value: int = 0, _i=i) -> int:
                return _i + value

            tool_fn.__name__ = f"tool_{i:03d}"
            return tool_fn

        server.register_tool(make_tool(idx))

    handler = server.request_handlers[types.ListToolsRequest]

    first = await run_with_context(DummySession("tools-1"), handler, types.ListToolsRequest())
    first_result = first.root
    assert len(first_result.tools) == 50
    assert first_result.nextCursor == "50"

    second_request = types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="50"))
    second = await run_with_context(DummySession("tools-2"), handler, second_request)
    second_result = second.root
    assert len(second_result.tools) == 50
    assert second_result.nextCursor == "100"

    third_request = types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="100"))
    third = await run_with_context(DummySession("tools-3"), handler, third_request)
    third_result = third.root
    assert len(third_result.tools) == 20
    assert third_result.nextCursor is None


@pytest.mark.anyio
async def test_tools_list_invalid_cursor():
    server = MCPServer("tools-invalid-cursor")

    server.register_tool(tool()(lambda: None))
    handler = server.request_handlers[types.ListToolsRequest]

    request = types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="oops"))

    with pytest.raises(McpError) as excinfo:
        await run_with_context(DummySession("tools-invalid"), handler, request)

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.anyio
async def test_tools_list_cursor_past_end():
    server = MCPServer("tools-past-end")

    for idx in range(3):

        def make_tool(i: int):
            def _fn(_value=i):
                return _value

            _fn.__name__ = f"tiny_{i}"
            return _fn

        server.register_tool(make_tool(idx))

    handler = server.request_handlers[types.ListToolsRequest]
    request = types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="9999"))
    response = await run_with_context(DummySession("tools-past"), handler, request)

    assert response.root.tools == []
    assert response.root.nextCursor is None


@pytest.mark.anyio
async def test_tools_metadata_fields_present():
    server = MCPServer("tools-metadata")

    with server.binding():

        @tool(
            description="Adds two numbers",
            title="Adder",
            output_schema={"type": "object", "properties": {"sum": {"type": "number"}}},
            annotations={"readOnlyHint": True},
            icons=[{"src": "file:///icon.png"}],
        )
        def add(a: int, b: int) -> dict[str, int]:
            return {"sum": a + b}

    handler = server.request_handlers[types.ListToolsRequest]
    response = await run_with_context(DummySession("tools-metadata"), handler, types.ListToolsRequest())

    tool_entry = response.root.tools[0]
    assert tool_entry.description == "Adds two numbers"
    assert tool_entry.outputSchema == {"type": "object", "properties": {"sum": {"type": "number"}}}
    assert tool_entry.annotations
    assert tool_entry.annotations.title == "Adder"
    assert tool_entry.annotations.readOnlyHint is True
    assert tool_entry.icons
    assert tool_entry.icons[0].src == "file:///icon.png"


@pytest.mark.anyio
async def test_tool_output_schema_inferred_from_return_type():
    server = MCPServer("tools-output-schema")

    @dataclass
    class Result:
        total: int

    with server.binding():

        @tool()
        async def sum_values(values: list[int]) -> Result:
            return Result(total=sum(values))

    tool_def = server.tools.definitions["sum_values"]
    assert tool_def.outputSchema is not None
    props = tool_def.outputSchema.get("properties")
    assert props and "total" in props

    result = await server.invoke_tool("sum_values", values=[1, 2, 3])
    assert result.structuredContent == {"total": 6}


@pytest.mark.anyio
async def test_tool_output_schema_handles_nested_dataclasses():
    server = MCPServer("tools-output-nested")

    with server.binding():

        @tool()
        async def describe_profile(name: str, street: str | None = None) -> NestedProfile:
            addr = NestedAddress(street=street or "Unknown", postal_code=94107)
            return NestedProfile(name=name, address=addr if street else None, tags=["example"])

    tool_def = server.tools.definitions["describe_profile"]
    schema = tool_def.outputSchema
    assert schema is not None
    expected = resolve_output_schema(NestedProfile).schema
    expected.pop("$defs", None)
    assert schema == expected

    result = await server.tools.call_tool("describe_profile", {"name": "Ada", "street": "Market"})
    assert result.structuredContent == {
        "name": "Ada",
        "address": {"street": "Market", "postal_code": 94107},
        "tags": ["example"],
    }


@pytest.mark.anyio
async def test_tool_output_schema_supports_union_types():
    server = MCPServer("tools-output-union")

    with server.binding():

        @tool()
        async def choose_action(chat: bool) -> UnionAction:
            if chat:
                return UnionAction(kind="chat", payload={"message": "hi"})
            return UnionAction(kind="navigate", payload={"url": "https://example.com"})

    tool_def = server.tools.definitions["choose_action"]
    schema = tool_def.outputSchema
    assert schema is not None
    expected = resolve_output_schema(UnionAction).schema
    expected.pop("$defs", None)
    assert schema == expected

    result = await server.tools.call_tool("choose_action", {"chat": False})
    assert result.structuredContent == {
        "kind": "navigate",
        "payload": {"url": "https://example.com"},
    }


@pytest.mark.anyio
async def test_tool_output_schema_explicit_pass_through():
    server = MCPServer("tools-output-explicit")

    explicit_schema = {
        "type": "object",
        "properties": {
            "value": {"type": "number"},
            "unit": {"type": "string"},
        },
        "required": ["value", "unit"],
        "additionalProperties": False,
    }

    with server.binding():

        @tool(output_schema=explicit_schema)
        async def measure() -> dict[str, Any]:
            return {"value": 42, "unit": "ms"}

    specification = server.tools.definitions["measure"]
    schema = specification.outputSchema
    assert schema["properties"] == explicit_schema["properties"]
    assert schema["required"] == explicit_schema["required"]

    result = await server.tools.call_tool("measure", {})
    assert result.structuredContent == {"value": 42, "unit": "ms"}


@pytest.mark.anyio
async def test_tool_output_schema_boxes_scalars():
    server = MCPServer("tools-output-scalar")

    with server.binding():

        @tool()
        async def answer() -> int:
            return 7

    schema = server.tools.definitions["answer"].outputSchema
    assert schema is not None
    assert schema["type"] == "object"
    assert schema["properties"] == {"result": {"type": "integer"}}
    assert schema["required"] == ["result"]

    result = await server.tools.call_tool("answer", {})
    assert result.structuredContent == {"result": 7}


@pytest.mark.anyio
async def test_tools_list_changed_notification_enabled():
    server = MCPServer("tools-list-changed", notification_flags=NotificationFlags(tools_changed=True))
    handler = server.request_handlers[types.ListToolsRequest]
    session = DummySession("tool-observer")

    await run_with_context(session, handler, types.ListToolsRequest())
    await server.notify_tools_list_changed()

    assert session.notifications
    assert session.notifications[-1].root.method == "notifications/tools/list_changed"


@pytest.mark.anyio
async def test_tools_list_changed_notification_disabled():
    server = MCPServer("tools-list-changed-off")
    handler = server.request_handlers[types.ListToolsRequest]
    session = DummySession("tool-observer-off")

    await run_with_context(session, handler, types.ListToolsRequest())
    await server.notify_tools_list_changed()

    assert all(note.root.method != "notifications/tools/list_changed" for note in session.notifications)
@dataclass
class NestedAddress:
    street: str
    postal_code: int


@dataclass
class NestedProfile:
    name: str
    address: NestedAddress | None
    tags: list[str]


@dataclass
class UnionAction:
    kind: Literal["chat", "navigate"]
    payload: dict[str, Any]
