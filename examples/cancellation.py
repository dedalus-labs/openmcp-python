"""Client cancellation demo.

Requires `examples/full_demo/server.py` to be running.
"""

from __future__ import annotations

import anyio

from openmcp import MCPClient
from mcp.client.streamable_http import streamablehttp_client
from openmcp import types


async def main() -> None:
    async with streamablehttp_client("http://127.0.0.1:3000/mcp") as (reader, writer, _):
        async with MCPClient(reader, writer) as client:
            request = types.ClientRequest(
                types.CallToolRequest(name="sleep", arguments={"seconds": 10})
            )

            async def invoke():
                return await client.send_request(request, types.CallToolResult)

            async with anyio.create_task_group() as tg:
                tg.start_soon(invoke)
                await anyio.sleep(2)
                await client.cancel_request(request.id, reason="timeout")
                tg.cancel_scope.cancel()
                print("Cancellation sent")


if __name__ == "__main__":
    anyio.run(main)
