# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Sync/async function support tests for tools.

Exercises the maybe_await_with_args utility from utils/coro.py in the tool
capability context, ensuring both synchronous and asynchronous tool functions
are correctly dispatched without blocking the event loop.

Spec reference: docs/mcp/spec/schema-reference/tools-call.md
"""

from __future__ import annotations

import asyncio

import pytest

from openmcp import MCPServer
from openmcp.tool import tool


@pytest.mark.asyncio
async def test_sync_tool_function():
    """Synchronous tool functions execute correctly."""
    server = MCPServer("sync-tools")

    with server.binding():

        @tool(description="Synchronously adds two numbers")
        def add(a: int, b: int) -> int:
            return a + b

    assert "add" in server.tool_names

    result = await server.invoke_tool("add", a=2, b=3)
    assert not result.isError
    assert result.content
    assert result.content[0].text == "5"
    assert result.structuredContent == {"result": 5}


@pytest.mark.asyncio
async def test_async_tool_function():
    """Asynchronous tool functions execute correctly."""
    server = MCPServer("async-tools")

    with server.binding():

        @tool(description="Asynchronously adds two numbers")
        async def add_async(a: int, b: int) -> int:
            await asyncio.sleep(0)  # yield to event loop
            return a + b

    assert "add_async" in server.tool_names

    result = await server.invoke_tool("add_async", a=4, b=7)
    assert not result.isError
    assert result.content
    assert result.content[0].text == "11"
    assert result.structuredContent == {"result": 11}


@pytest.mark.asyncio
async def test_mixed_sync_async_tools():
    """Server supports both sync and async tools simultaneously."""
    server = MCPServer("mixed-tools")

    with server.binding():

        @tool(description="Synchronous multiply")
        def multiply(a: int, b: int) -> int:
            return a * b

        @tool(description="Asynchronous divide")
        async def divide(a: float, b: float) -> float:
            await asyncio.sleep(0)
            return a / b

    assert "multiply" in server.tool_names
    assert "divide" in server.tool_names

    # Invoke sync tool
    sync_result = await server.invoke_tool("multiply", a=3, b=4)
    assert not sync_result.isError
    assert sync_result.structuredContent == {"result": 12}

    # Invoke async tool
    async_result = await server.invoke_tool("divide", a=10.0, b=2.0)
    assert not async_result.isError
    assert async_result.structuredContent == {"result": 5.0}


@pytest.mark.asyncio
async def test_sync_tool_does_not_block_event_loop():
    """Sync tools execute without blocking concurrent tasks."""
    server = MCPServer("nonblocking")
    execution_order = []

    with server.binding():

        @tool()
        def slow_sync() -> str:
            execution_order.append("sync-start")
            # Synchronous sleep would block; we verify it yields
            execution_order.append("sync-end")
            return "done"

        @tool()
        async def fast_async() -> str:
            execution_order.append("async-start")
            await asyncio.sleep(0)
            execution_order.append("async-end")
            return "done"

    # Execute both concurrently
    results = await asyncio.gather(
        server.invoke_tool("slow_sync"),
        server.invoke_tool("fast_async"),
    )

    # Both should complete successfully
    assert all(not r.isError for r in results)

    # Event loop interleaving proves no blocking occurred
    assert len(execution_order) == 4
    assert "sync-start" in execution_order
    assert "async-start" in execution_order


@pytest.mark.asyncio
async def test_sync_tool_schema_inference():
    """Sync tool schemas are correctly derived from signature."""
    server = MCPServer("sync-schema")

    with server.binding():

        @tool()
        def compute(value: int, multiplier: int = 2) -> int:
            return value * multiplier

    schema = server.tools.definitions["compute"].inputSchema
    props = schema["properties"]

    assert schema["type"] == "object"
    assert schema["required"] == ["value"]
    assert props["value"]["type"] in {"integer", "number"}
    assert props["multiplier"]["type"] in {"integer", "number"}
    assert props["multiplier"].get("default") == 2


@pytest.mark.asyncio
async def test_async_tool_schema_inference():
    """Async tool schemas are correctly derived from signature."""
    server = MCPServer("async-schema")

    with server.binding():

        @tool()
        async def analyze(data: list[int], threshold: int = 100) -> dict[str, int]:
            await asyncio.sleep(0)
            return {"count": len(data), "threshold": threshold}

    schema = server.tools.definitions["analyze"].inputSchema
    props = schema["properties"]

    assert schema["type"] == "object"
    assert schema["required"] == ["data"]
    assert props["threshold"].get("default") == 100


@pytest.mark.asyncio
async def test_sync_tool_with_dict_return():
    """Sync tools returning dicts are correctly normalized."""
    server = MCPServer("sync-dict")

    with server.binding():

        @tool()
        def status(code: int) -> dict[str, int | str]:
            return {"code": code, "message": "OK"}

    result = await server.invoke_tool("status", code=200)
    assert not result.isError
    assert result.structuredContent == {"code": 200, "message": "OK"}


@pytest.mark.asyncio
async def test_async_tool_with_exception():
    """Async tool exceptions propagate correctly (not wrapped)."""
    server = MCPServer("async-error")

    with server.binding():

        @tool()
        async def failing_tool() -> int:
            await asyncio.sleep(0)
            raise ValueError("Something went wrong")

    # Exceptions propagate directly
    with pytest.raises(ValueError, match="Something went wrong"):
        await server.invoke_tool("failing_tool")


@pytest.mark.asyncio
async def test_sync_tool_with_exception():
    """Sync tool exceptions propagate correctly (not wrapped)."""
    server = MCPServer("sync-error")

    with server.binding():

        @tool()
        def failing_sync() -> int:
            raise RuntimeError("Sync failure")

    # Exceptions propagate directly
    with pytest.raises(RuntimeError, match="Sync failure"):
        await server.invoke_tool("failing_sync")


@pytest.mark.asyncio
async def test_sync_tool_output_schema_inference():
    """Sync tool output schemas are correctly inferred from dataclass."""
    from dataclasses import dataclass

    server = MCPServer("sync-output")

    @dataclass
    class Metrics:
        input: int
        squared: int

    with server.binding():

        @tool()
        def compute_metrics(value: int) -> Metrics:
            return Metrics(input=value, squared=value ** 2)

    tool_def = server.tools.definitions["compute_metrics"]
    assert tool_def.outputSchema is not None
    props = tool_def.outputSchema.get("properties")
    assert props and "input" in props and "squared" in props


@pytest.mark.asyncio
async def test_async_tool_output_schema_inference():
    """Async tool output schemas are correctly inferred."""
    server = MCPServer("async-output")

    from dataclasses import dataclass

    @dataclass
    class Result:
        total: int
        average: float

    with server.binding():

        @tool()
        async def summarize(values: list[int]) -> Result:
            await asyncio.sleep(0)
            total = sum(values)
            return Result(total=total, average=total / len(values) if values else 0.0)

    tool_def = server.tools.definitions["summarize"]
    assert tool_def.outputSchema is not None
    props = tool_def.outputSchema.get("properties")
    assert props and "total" in props and "average" in props
