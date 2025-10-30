# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""STDIO transport adapter built on the reference MCP SDK.

Implements the framing rules from ``docs/mcp/core/transports/stdio.md`` by
delegating to the SDK's ``stdio_server`` helper, which handles newline-delimited
JSON-RPC traffic over ``stdin``/``stdout``.
"""

from __future__ import annotations

from .base import BaseTransport
from ..._sdk_loader import ensure_sdk_importable


ensure_sdk_importable()

from mcp.server.stdio import stdio_server


def get_stdio_server():
    """Return the SDK's stdio context manager.

    Separated into a helper so tests can patch it with in-memory transports.
    """
    return stdio_server


class StdioTransport(BaseTransport):
    """Run an :class:`openmcp.server.app.MCPServer` over STDIO."""

    TRANSPORT = ("stdio", "STDIO", "Standard IO")

    async def run(self, *, raise_exceptions: bool = False, stateless: bool = False) -> None:
        stdio_ctx = get_stdio_server()
        init_options = self.server.create_initialization_options()

        async with stdio_ctx() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, init_options, raise_exceptions=raise_exceptions, stateless=stateless
            )
