# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Advanced type hints for rich input schemas.

Demonstrates:
- Literal types for enum-like parameters
- Optional parameters with defaults
- Dataclass parameters for structured inputs
- Schema inference from complex type annotations

Spec reference:
https://modelcontextprotocol.io/specification/2025-06-18/server/tools

Usage:
    uv run python examples/tools/typed_tool.py
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from openmcp import MCPServer, tool


server = MCPServer("typed-tools")


@dataclass
class SearchFilter:
    """Dataclass parameters are inferred as nested object schemas."""

    category: str
    min_price: float = 0.0
    max_price: float = 1000.0


with server.binding():

    @tool(description="Format text with style")
    def format_text(
        text: str,
        style: Literal["uppercase", "lowercase", "title"] = "title",
    ) -> str:
        """Literal types generate enum constraints in JSON Schema."""
        if style == "uppercase":
            return text.upper()
        elif style == "lowercase":
            return text.lower()
        else:
            return text.title()

    @tool(description="Search products")
    async def search_products(query: str, filters: SearchFilter | None = None) -> dict[str, list[str]]:
        """Optional dataclass parameter with nested schema inference."""
        results = [f"Product matching '{query}'"]
        if filters:
            results.append(f"Filtered: {filters.category} ${filters.min_price}-${filters.max_price}")
        return {"results": results}


async def main() -> None:
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
