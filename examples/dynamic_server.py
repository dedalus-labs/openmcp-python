# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import json
from typing import Any

import anyio
from anyio import create_task_group

from openmcp import MCPServer, tool
from openmcp.server import MCPServer


server = MCPServer("webhook-driven", instructions="Hot-reload tools from controller")
server.allow_tools(None)  # start in permissive mode


async def reconcile_tools(config: dict[str, Any]) -> None:
    allow = set(config.get("allow", [])) or None
    server.allow_tools(allow)

    # re-register declarative tools shipped in your app
    from my_app import base_tools

    with server.binding():
        base_tools.register(server)

    # dynamically define or update inline tools from the payload
    for spec in config.get("inline_tools", []):
        name = spec["name"]
        tags = spec.get("tags", ())

        async def dynamic_tool(**kwargs):
            return {"name": name, "args": kwargs}

        dynamic_tool.__name__ = name
        with server.binding():
            tool(name=name, tags=tags)(dynamic_tool)  # decorator handles metadata
        server.register_tool(dynamic_tool)

    await server.notify_tools_list_changed()


async def webhook_listener(port: int) -> None:
    from anyio.abc import SocketStream

    async def handle_client(stream: SocketStream) -> None:
        data = await stream.receive(65536)
        payload = data.decode("utf-8")
        config = json.loads(payload)
        await reconcile_tools(config)
        await stream.send(b"HTTP/1.1 204 No Content\r\n\r\n")

    listeners = await anyio.create_tcp_listener(local_host="127.0.0.1", local_port=port)
    async with listeners:
        await listeners.serve(handle_client)
    async with create_task_group() as tg:
        tg.start_soon(server.serve, transport="streamable-http", port=8000)
        tg.start_soon(webhook_listener, 8000)


if __name__ == "__main__":
    anyio.run(main)
