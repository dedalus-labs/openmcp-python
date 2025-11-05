# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Client advertising filesystem roots to MCP servers.

Demonstrates how to configure the roots capability to establish filesystem
boundaries for servers. The server can only access paths within these roots,
preventing directory traversal attacks.

See: https://modelcontextprotocol.io/specification/2025-06-18/client/roots
See also: docs/openmcp/roots.md

Run with:
    uv run python examples/client/roots_config.py
"""

from __future__ import annotations

from pathlib import Path

import anyio

from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, open_connection


SERVER_URL = "http://127.0.0.1:8000/mcp"


async def main() -> None:
    """Connect to a server with filesystem roots configured."""

    # Define which directories the server can access
    # Use file:// URIs for cross-platform compatibility
    project_root = Path.cwd()
    temp_dir = Path("/tmp")

    initial_roots = [
        types.Root(
            uri=project_root.as_uri(),  # file:///path/to/project
            name="Project Directory",
        ),
        types.Root(
            uri=temp_dir.as_uri(),  # file:///tmp
            name="Temporary Files",
        ),
    ]

    capabilities = ClientCapabilitiesConfig(
        enable_roots=True,
        initial_roots=initial_roots,
    )

    async with open_connection(
        url=SERVER_URL,
        transport="streamable-http",
        capabilities=capabilities,
    ) as client:
        print("Connected with roots capability enabled")
        print(f"Server info: {client.initialize_result.serverInfo.name}")
        print(f"\nAdvertised roots:")
        for root in await client.list_roots():
            print(f"  - {root.name}: {root.uri}")

        # Demonstrate dynamic root updates
        # Add a new root after connection
        await anyio.sleep(2)
        print("\nAdding new root...")

        new_roots = initial_roots + [
            types.Root(
                uri=Path.home().as_uri(),
                name="Home Directory",
            )
        ]

        await client.update_roots(new_roots, notify=True)
        print("Updated roots:")
        for root in await client.list_roots():
            print(f"  - {root.name}: {root.uri}")

        # The server receives a notifications/roots/list_changed notification
        # and can re-query roots/list to see the new boundaries

        # Keep connection alive to demonstrate server-side validation
        print("\nServer can now validate paths against these roots")
        print("Try calling a file operation tool - it will be validated")
        await anyio.sleep(10)


if __name__ == "__main__":
    anyio.run(main)
