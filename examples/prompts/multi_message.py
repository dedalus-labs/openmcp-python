# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Multi-turn conversation with system, assistant, and user messages.

DRAFT: Shows complex conversation flows with multiple message roles.
Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts

Usage: uv run python examples/prompts/multi_message.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, prompt, types


server = MCPServer("multi-message-prompt-demo")

with server.binding():

    @prompt(
        name="debug-session",
        description="Guide a debugging session with context and examples",
        arguments=[
            {"name": "error_message", "required": True},
            {"name": "code_snippet", "required": True},
        ],
    )
    def debug_session_prompt(arguments: dict[str, str] | None) -> types.GetPromptResult:
        """Return GetPromptResult with explicit PromptMessage + TextContent objects.

        Most explicit form for multi-turn conversations with typed content blocks.
        """
        if not arguments:
            raise ValueError("Arguments required")

        error_msg = arguments["error_message"]
        code = arguments["code_snippet"]

        messages = [
            types.PromptMessage(
                role="assistant",
                content=types.TextContent(
                    type="text",
                    text="You are a debugging assistant. Analyze errors methodically: "
                    "1) Identify root cause, 2) Explain why, 3) Suggest fix.",
                ),
            ),
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=f"Error:\n```\n{error_msg}\n```"),
            ),
            types.PromptMessage(
                role="user",
                content=types.TextContent(type="text", text=f"Code:\n```\n{code}\n```\n\nWhat's wrong?"),
            ),
        ]

        return types.GetPromptResult(description="Debugging session for error analysis", messages=messages)


async def main() -> None:
    await server.serve(transport="streamable-http")


if __name__ == "__main__":
    asyncio.run(main())
