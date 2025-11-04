# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Parameterized prompt with required and optional arguments.

DRAFT: Shows argument handling, validation, and default values.
Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts

Usage: uv run python examples/prompts/parameterized.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, prompt


server = MCPServer("parameterized-prompt-demo")

with server.binding():

    @prompt(
        name="write-function",
        description="Generate a function with specified requirements",
        arguments=[
            {"name": "function_name", "description": "Function name", "required": True},
            {"name": "language", "description": "Language (default: python)", "required": False},
            {"name": "description", "description": "What it does", "required": True},
        ],
    )
    def write_function_prompt(arguments: dict[str, str] | None) -> list[dict[str, str]]:
        """Render parameterized prompt with argument substitution.

        Framework validates required args before calling this function.
        Missing required args trigger INVALID_PARAMS error automatically.
        """
        if not arguments:
            raise ValueError("Arguments required")

        func_name = arguments["function_name"]
        language = arguments.get("language", "python")  # Optional with default
        desc = arguments["description"]

        return [
            {"role": "assistant", "content": f"You are an expert {language} programmer."},
            {
                "role": "user",
                "content": f"Write a function named `{func_name}` that {desc}. "
                f"Follow {language} best practices and include type hints.",
            },
        ]


async def main() -> None:
    await server.serve(transport="streamable-http")


if __name__ == "__main__":
    asyncio.run(main())
