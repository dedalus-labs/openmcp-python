# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""[DRAFT] Custom transport registration pattern.

Demonstrates how to implement and register a custom transport for MCP servers.
This example shows a Unix domain socket transport, useful for local IPC.

Run:
    uv run python examples/advanced/custom_transport.py

Reference:
    - Transport base: src/openmcp/server/transports/base.py
    - Built-in transports: src/openmcp/server/transports/{stdio,streamable_http}.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import anyio
from anyio.streams.stapled import StapledObjectStream

from openmcp import MCPServer, tool
from openmcp.server.transports.base import BaseTransport


class UnixSocketTransport(BaseTransport):
    """Custom transport using Unix domain sockets for local IPC.

    Production use cases:
    - High-throughput local communication without TCP overhead
    - Process isolation with file-based permissions
    - Container-to-host communication via volume mounts
    """

    TRANSPORT = ("unix-socket", "unix", "uds")

    async def run(self, socket_path: str = "/tmp/mcp.sock", **kwargs: Any) -> None:
        """Start listening on a Unix domain socket."""
        path = Path(socket_path)
        # Clean up stale socket
        if path.exists():
            path.unlink()

        self._server._logger.info(f"Starting Unix socket transport at {socket_path}")

        async def handle_connection(stream: anyio.abc.SocketStream) -> None:
            """Handle a single client connection."""
            async with stream:
                # Wrap the raw socket stream for JSON-RPC
                reader = anyio.wrap_file(stream)  # type: ignore
                writer = anyio.wrap_file(stream)  # type: ignore

                # Minimal JSON-RPC framing: newline-delimited JSON
                async for line in reader:
                    try:
                        message = json.loads(line)
                        # In a real implementation, dispatch to server._handle_request
                        # For this stub, echo back
                        response = {"jsonrpc": "2.0", "id": message.get("id"), "result": "stub"}
                        await writer.write(json.dumps(response) + "\n")
                    except json.JSONDecodeError:
                        self._server._logger.warning(f"Invalid JSON received: {line}")
                        continue

        listener = await anyio.create_unix_listener(socket_path)
        async with listener:
            self._server._logger.info(f"Listening on {socket_path}")
            await listener.serve(handle_connection)


async def main() -> None:
    """Demonstrate custom transport registration and usage."""
    server = MCPServer("unix-socket-demo", instructions="Custom transport demo")

    # Register the custom transport with multiple aliases
    server.register_transport("unix-socket", lambda s: UnixSocketTransport(s), aliases=("unix", "uds"))

    # Register a simple tool
    with server.binding():

        @tool(description="Test tool for custom transport")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

    # Serve using the custom transport
    await server.serve(transport="unix-socket", socket_path="/tmp/mcp-demo.sock")


# Production patterns:

# 1. Transport selection from config
def create_server_with_config(config: dict[str, Any]) -> MCPServer:
    """Factory pattern for environment-specific transport selection."""
    server = MCPServer("configurable-server")

    if config.get("transport") == "unix":
        server.register_transport("unix", lambda s: UnixSocketTransport(s))
        server._default_transport = "unix"

    return server


# 2. Dual-transport server (HTTP + Unix socket)
async def multi_transport_server() -> None:
    """Run the same server on multiple transports simultaneously."""
    server = MCPServer("multi-transport")

    with server.binding():

        @tool(description="Available on all transports")
        async def status() -> str:
            return "operational"

    # Register custom transport
    server.register_transport("unix", lambda s: UnixSocketTransport(s))

    async with asyncio.TaskGroup() as tg:
        # HTTP for external clients
        tg.create_task(server.serve(transport="streamable-http", port=8000))
        # Unix socket for local clients
        tg.create_task(server.serve(transport="unix", socket_path="/tmp/mcp.sock"))


if __name__ == "__main__":
    print("Custom transport example: Unix domain socket MCP server")
    print("Socket path: /tmp/mcp-demo.sock")
    # asyncio.run(main())  # Uncomment to run
