# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Basic prompt template example.

DRAFT: Demonstrates simplest prompt registration with static messages.
Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts

Usage: uv run python examples/prompts/basic_prompt.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, prompt


server = MCPServer("basic-prompt-demo")

# All prompts must be registered within server.binding() context
with server.binding():

    @prompt(
        name="code-review",
        description="Guide the model through a code review process",
    )
    def code_review_prompt(arguments: dict[str, str] | None) -> list[dict[str, str]]:
        """Return static conversation template.

        Return types: list[dict], list[PromptMessage], or GetPromptResult.
        Simple dicts are auto-converted to PromptMessage objects.
        """
        return [
            {
                "role": "assistant",
                "content": "You are a careful code reviewer focusing on correctness, readability, and maintainability.",
            },
            {"role": "user", "content": "Review the code and provide constructive feedback."},
        ]


async def main() -> None:
    await server.serve(transport="streamable-http")


if __name__ == "__main__":
    asyncio.run(main())
