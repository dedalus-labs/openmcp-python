# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal Brave Search MCP server."""

from __future__ import annotations

import os
from pathlib import Path
import sys

from dotenv import load_dotenv

from openmcp import MCPServer


THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from simple_tools import register_brave_tools  # noqa: E402


load_dotenv()

server = MCPServer("brave-search", instructions="Brave Search tools")

register_brave_tools(server, api_key=os.getenv("BRAVE_API_KEY"))


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
