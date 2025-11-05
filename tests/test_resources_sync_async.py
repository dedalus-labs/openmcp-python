"""Test sync/async resource function support.

Verifies that ResourcesService correctly handles both synchronous and asynchronous
resource functions via maybe_await_with_args, per:
https://modelcontextprotocol.io/specification/2025-06-18/server/resources
"""

import asyncio

import pytest

from openmcp import MCPServer, resource


@pytest.mark.asyncio
async def test_sync_resource_function() -> None:
    """Synchronous resource functions execute correctly."""
    server = MCPServer(name="test-sync-resource")

    with server.binding():

        @resource("file://config.txt")
        def get_config() -> str:
            return "database=postgresql\nport=5432"

    read_result = await server.invoke_resource("file://config.txt")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert str(content.uri).startswith("file://config.txt")
    assert isinstance(content.text, str)
    assert "database=postgresql" in content.text


@pytest.mark.asyncio
async def test_async_resource_function() -> None:
    """Asynchronous resource functions execute correctly."""
    server = MCPServer(name="test-async-resource")

    with server.binding():

        @resource("file://data.json")
        async def fetch_data() -> str:
            await asyncio.sleep(0)  # Yield to event loop
            return '{"status": "ok", "data": [1, 2, 3]}'

    read_result = await server.invoke_resource("file://data.json")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert str(content.uri).startswith("file://data.json")
    assert isinstance(content.text, str)
    assert '"status": "ok"' in content.text


@pytest.mark.asyncio
async def test_mixed_sync_async_resources() -> None:
    """Server can register both sync and async resources."""
    server = MCPServer(name="test-mixed-resources")

    with server.binding():

        @resource("file://sync.txt")
        def sync_resource() -> str:
            return "synchronous data"

        @resource("file://async.txt")
        async def async_resource() -> str:
            await asyncio.sleep(0)
            return "asynchronous data"

    # Read sync resource
    sync_result = await server.invoke_resource("file://sync.txt")
    assert sync_result.contents[0].text == "synchronous data"

    # Read async resource
    async_result = await server.invoke_resource("file://async.txt")
    assert async_result.contents[0].text == "asynchronous data"


@pytest.mark.asyncio
async def test_binary_resource_sync() -> None:
    """Sync resources can return binary data."""
    server = MCPServer(name="test-binary-sync")

    with server.binding():

        @resource("file://image.png")
        def get_image() -> bytes:
            return b"\x89PNG\r\n\x1a\n"

    read_result = await server.invoke_resource("file://image.png")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert str(content.uri).startswith("file://image.png")
    assert isinstance(content.blob, str)  # base64 encoded


@pytest.mark.asyncio
async def test_binary_resource_async() -> None:
    """Async resources can return binary data."""
    server = MCPServer(name="test-binary-async")

    with server.binding():

        @resource("file://archive.zip")
        async def fetch_archive() -> bytes:
            await asyncio.sleep(0)
            return b"PK\x03\x04"  # ZIP magic number

    read_result = await server.invoke_resource("file://archive.zip")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert str(content.uri).startswith("file://archive.zip")
    assert isinstance(content.blob, str)


@pytest.mark.asyncio
async def test_async_resource_concurrent_reads() -> None:
    """Async resources don't block concurrent operations."""
    server = MCPServer(name="test-concurrent")
    call_order = []

    with server.binding():

        @resource("file://slow.txt")
        async def slow_resource() -> str:
            call_order.append("slow_start")
            await asyncio.sleep(0.01)
            call_order.append("slow_end")
            return "slow data"

        @resource("file://fast.txt")
        async def fast_resource() -> str:
            call_order.append("fast_start")
            await asyncio.sleep(0)
            call_order.append("fast_end")
            return "fast data"

    # Start both reads concurrently
    slow_task = asyncio.create_task(server.invoke_resource("file://slow.txt"))
    await asyncio.sleep(0.005)  # Let slow start
    fast_task = asyncio.create_task(server.invoke_resource("file://fast.txt"))

    await slow_task
    await fast_task

    # Fast should complete while slow is waiting
    assert call_order == ["slow_start", "fast_start", "fast_end", "slow_end"]


@pytest.mark.asyncio
async def test_sync_resource_exception_propagates() -> None:
    """Exceptions from sync resources are caught and handled."""
    server = MCPServer(name="test-sync-error")

    with server.binding():

        @resource("file://error.txt")
        def failing_resource() -> str:
            raise ValueError("Resource error")

    read_result = await server.invoke_resource("file://error.txt")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert isinstance(content.text, str)
    assert "Resource error" in content.text


@pytest.mark.asyncio
async def test_async_resource_exception_propagates() -> None:
    """Exceptions from async resources are caught and handled."""
    server = MCPServer(name="test-async-error")

    with server.binding():

        @resource("file://async-error.txt")
        async def failing_async_resource() -> str:
            await asyncio.sleep(0)
            raise RuntimeError("Async resource error")

    read_result = await server.invoke_resource("file://async-error.txt")
    assert len(read_result.contents) == 1
    content = read_result.contents[0]
    assert isinstance(content.text, str)
    assert "Async resource error" in content.text
