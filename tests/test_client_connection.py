import socket

import anyio
import pytest

from openmcp import MCPServer, tool, types
from openmcp.client import open_connection


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
                    types.CallToolRequest(
                        params=types.CallToolRequestParams(
                            name="add",
                            arguments={"a": 3, "b": 4},
                        )
                    )
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
    with pytest.raises(ValueError):
        async with open_connection("whatever://", transport="bogus"):
            pass
