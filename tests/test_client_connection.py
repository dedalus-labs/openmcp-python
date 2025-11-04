# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import socket

import anyio
import httpx
import pytest

from openmcp import MCPServer, tool, types
from openmcp.client import open_connection
from openmcp.versioning import SUPPORTED_PROTOCOL_VERSIONS


HTTP_OK = 200
HTTP_BAD_REQUEST = 400
JSONRPC_INVALID_REQUEST = -32600


async def _wait_for_port(host: str, port: int, *, timeout: float = 5.0) -> None:
    with anyio.fail_after(timeout):
        while True:
            try:
                with socket.create_connection((host, port), timeout=0.1):
                    return
            except OSError:
                await anyio.sleep(0.05)


@pytest.mark.anyio
async def test_open_connection_streamable_http(unused_tcp_port: int) -> None:
    server = MCPServer("connection-test")

    with server.binding():

        @tool()
        def add(a: int, b: int) -> int:
            return a + b

    host = "127.0.0.1"
    port = unused_tcp_port

    async def run_server() -> None:
        await server.serve(transport="streamable-http", host=host, port=port)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_server)
        await _wait_for_port(host, port)

        async with open_connection(f"http://{host}:{port}/mcp") as client:
            result = await client.send_request(
                types.ClientRequest(
                    types.CallToolRequest(params=types.CallToolRequestParams(name="add", arguments={"a": 3, "b": 4}))
                ),
                types.CallToolResult,
            )

            assert not result.isError
            assert result.content
            assert result.content[0].text == "7"
            if result.structuredContent is not None:
                assert result.structuredContent == {"result": 7}
            assert client.session is not None

        tg.cancel_scope.cancel()
        await anyio.sleep(0)


@pytest.mark.anyio
async def test_open_connection_unknown_transport() -> None:
    with pytest.raises(ValueError, match="Unsupported transport"):
        async with open_connection("whatever://", transport="bogus"):
            pass


@pytest.mark.anyio
async def test_streamable_http_allows_preinitialize_get(unused_tcp_port: int) -> None:
    server = MCPServer("preinit-get")

    host = "127.0.0.1"
    port = unused_tcp_port

    async def run_server() -> None:
        await server.serve(transport="streamable-http", host=host, port=port)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_server)
        await _wait_for_port(host, port)

        version = SUPPORTED_PROTOCOL_VERSIONS[0]
        base_url = f"http://{host}:{port}/mcp"

        async with httpx.AsyncClient(timeout=2.0) as client:
            initialize_payload = {
                "jsonrpc": "2.0",
                "id": "init-1",
                "method": "initialize",
                "params": {
                    "protocolVersion": version,
                    "capabilities": {},
                    "clientInfo": {"name": "test-client", "version": "0.0.0"},
                },
            }

            post_headers = {
                "MCP-Protocol-Version": version,
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }

            async with client.stream("POST", base_url, headers=post_headers, json=initialize_payload) as init_response:
                assert init_response.status_code == HTTP_OK
                session_id = init_response.headers.get("Mcp-Session-Id")
                assert session_id

            get_headers = {"MCP-Protocol-Version": version, "Mcp-Session-Id": session_id, "Accept": "text/event-stream"}

            async with client.stream("GET", base_url, headers=get_headers) as response:
                assert response.status_code == HTTP_OK

        tg.cancel_scope.cancel()
        await anyio.sleep(0)


@pytest.mark.anyio
async def test_streamable_http_stateless_allows_preinitialize_get(unused_tcp_port: int) -> None:
    server = MCPServer("stateless", streamable_http_stateless=True)

    host = "127.0.0.1"
    port = unused_tcp_port

    async def run_server() -> None:
        await server.serve(transport="streamable-http", host=host, port=port)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_server)
        await _wait_for_port(host, port)

        headers = {"MCP-Protocol-Version": SUPPORTED_PROTOCOL_VERSIONS[0], "Accept": "text/event-stream"}

        async with httpx.AsyncClient(timeout=2.0) as client, client.stream(
            "GET", f"http://{host}:{port}/mcp", headers=headers
        ) as response:
            assert response.status_code == HTTP_OK

        tg.cancel_scope.cancel()
        await anyio.sleep(0)


@pytest.mark.anyio
async def test_streamable_http_preinitialize_get_requires_session(unused_tcp_port: int) -> None:
    server = MCPServer("stateful-get")

    host = "127.0.0.1"
    port = unused_tcp_port

    async def run_server() -> None:
        await server.serve(transport="streamable-http", host=host, port=port)

    async with anyio.create_task_group() as tg:
        tg.start_soon(run_server)
        await _wait_for_port(host, port)

        headers = {"MCP-Protocol-Version": SUPPORTED_PROTOCOL_VERSIONS[0], "Accept": "text/event-stream"}

        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(f"http://{host}:{port}/mcp", headers=headers)
            assert response.status_code == HTTP_BAD_REQUEST
            payload = response.json()
            error = payload.get("error", {})
            assert error.get("code") == JSONRPC_INVALID_REQUEST
            message = error.get("message", "").lower()
            assert "missing" in message
            assert "session" in message

        tg.cancel_scope.cancel()
        await anyio.sleep(0)
