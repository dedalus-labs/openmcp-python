# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Prompt with argument completion support.

DRAFT: Shows autocomplete suggestions for prompt arguments.
Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/completion

Usage: uv run python examples/prompts/completion.py
"""

from __future__ import annotations

import asyncio

from openmcp import MCPServer, completion, prompt, types


server = MCPServer("prompt-completion-demo")

# Static knowledge base for completion
LANGUAGES = ["python", "javascript", "typescript", "rust", "go"]
FRAMEWORKS = {
    "python": ["django", "flask", "fastapi"],
    "javascript": ["react", "vue", "angular"],
    "typescript": ["next.js", "nest.js"],
}

with server.binding():

    @prompt(
        name="scaffold-project",
        description="Generate project structure for a new application",
        arguments=[
            {"name": "language", "description": "Programming language", "required": True},
            {"name": "framework", "description": "Framework", "required": False},
        ],
    )
    def scaffold_prompt(arguments: dict[str, str] | None) -> list[dict[str, str]]:
        """Render scaffold instructions based on language and framework."""
        if not arguments:
            raise ValueError("Arguments required")

        lang = arguments["language"]
        framework = arguments.get("framework", "none")

        return [
            {"role": "assistant", "content": f"You are a {lang} expert."},
            {
                "role": "user",
                "content": f"Create a {lang} project" + (f" using {framework}" if framework != "none" else ""),
            },
        ]

    @completion(prompt="scaffold-project")
    def complete_scaffold_args(
        argument: types.CompletionArgument,
        context: types.CompletionContext | None,
    ) -> list[str]:
        """Provide completions for language/framework arguments.

        argument.name: which field needs completion
        argument.value: partial text typed so far
        context: already-provided arguments
        """
        partial = argument.value.lower() if argument.value else ""

        if argument.name == "language":
            return [lang for lang in LANGUAGES if lang.startswith(partial)]

        if argument.name == "framework" and context:
            lang = context.dict().get("language")
            if lang in FRAMEWORKS:
                return [fw for fw in FRAMEWORKS[lang] if fw.startswith(partial)]

        return []


async def main() -> None:
    await server.serve(transport="streamable-http")


if __name__ == "__main__":
    asyncio.run(main())
