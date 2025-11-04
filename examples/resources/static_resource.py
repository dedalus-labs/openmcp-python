# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Static resource example.

Demonstrates basic resource registration with text and JSON content.
Resources are static data that clients can retrieve via `resources/read`.

Spec:
- https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- resources/read returns TextResourceContents or BlobResourceContents

Usage:
    uv run python examples/resources/static_resource.py
"""

from __future__ import annotations

import asyncio
import json

from openmcp import MCPServer, resource


server = MCPServer("static-resources")

with server.binding():

    @resource(
        uri="config://app/settings",
        name="Application Settings",
        description="Read-only application configuration",
        mime_type="application/json",
    )
    def app_settings() -> str:
        """Return configuration as JSON string.

        Resources can return str (text) or bytes (binary). When returning str,
        the server wraps it in TextResourceContents.
        """
        config = {
            "version": "1.0.0",
            "features": ["caching", "compression"],
            "limits": {"max_connections": 100, "timeout_seconds": 30},
        }
        return json.dumps(config, indent=2)

    @resource(
        uri="doc://readme",
        name="README",
        description="Project documentation",
        mime_type="text/markdown",
    )
    def readme() -> str:
        """Static text resource with Markdown content."""
        return """# Project Overview

This server demonstrates static resources in OpenMCP.

## Features
- Static configuration
- Documentation as resources
- Schema-based content
"""


async def main() -> None:
    await server.serve(transport="streamable-http", port=8080)


if __name__ == "__main__":
    asyncio.run(main())
