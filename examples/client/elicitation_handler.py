# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Client implementing elicitation capability for MCP servers.

Demonstrates how to handle elicitation/create requests from servers that need
user input during tool execution. This example uses simple CLI prompts but
could be adapted for GUI dialogs, web forms, etc.

See: https://modelcontextprotocol.io/specification/2025-06-18/server/elicitation
See also: docs/openmcp/elicitation.md

Run with:
    uv run python examples/client/elicitation_handler.py
"""

from __future__ import annotations

import sys

import anyio

from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, open_connection


SERVER_URL = "http://127.0.0.1:8000/mcp"


async def elicitation_handler(
    _context: object, params: types.ElicitRequestParams
) -> types.ElicitResult | types.ErrorData:
    """Handle elicitation/create requests by prompting the user via CLI.

    The server calls this when it needs user input. We present the message,
    collect input matching the schema, and return the result with the
    appropriate action (accept, decline, cancel).
    """
    try:
        print(f"\n{'=' * 60}")
        print(f"Server requests input: {params.message}")
        print(f"{'=' * 60}\n")

        # Parse the schema to understand what fields are needed
        schema = params.requestedSchema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Collect user input for each field
        content: dict[str, object] = {}
        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type", "string")
            is_required = field_name in required

            prompt = f"{field_name} ({field_type})"
            if not is_required:
                prompt += " [optional]"
            prompt += ": "

            # Simple CLI input loop
            while True:
                try:
                    user_input = await anyio.to_thread.run_sync(input, prompt)

                    # Handle empty input
                    if not user_input:
                        if is_required:
                            print(f"  Error: {field_name} is required")
                            continue
                        break

                    # Type coercion based on schema
                    if field_type == "boolean":
                        content[field_name] = user_input.lower() in ("true", "yes", "1", "y")
                    elif field_type == "integer":
                        content[field_name] = int(user_input)
                    elif field_type == "number":
                        content[field_name] = float(user_input)
                    else:
                        content[field_name] = user_input

                    break

                except ValueError:
                    print(f"  Error: Expected {field_type}, try again")

        # Ask for confirmation
        confirm = await anyio.to_thread.run_sync(input, "\nSubmit? [Y/n/cancel]: ")

        if confirm.lower() == "cancel":
            return types.ElicitResult(action="cancel", content={})
        elif confirm.lower() == "n":
            return types.ElicitResult(action="decline", content={})
        else:
            return types.ElicitResult(action="accept", content=content)

    except Exception as e:
        return types.ErrorData(code=-32603, message=f"Elicitation failed: {e}")


async def main() -> None:
    """Connect to a server that uses elicitation and handle its requests."""
    capabilities = ClientCapabilitiesConfig(
        elicitation=elicitation_handler  # Advertise that we support elicitation
    )

    async with open_connection(
        target=SERVER_URL,
        transport="streamable-http",
        capabilities=capabilities,
    ) as client:
        print("Connected with elicitation capability enabled")
        print(f"Server info: {client.initialize_result.serverInfo.name}")

        # Call a tool that triggers elicitation
        # Example: A tool that deletes files and needs confirmation
        try:
            result = await client.send_request(
                types.ClientRequest(
                    types.CallToolRequest(
                        params=types.CallToolRequestParams(
                            name="some_tool_needing_confirmation",
                            arguments={},
                        )
                    )
                ),
                types.CallToolResult,
            )
            print(f"\nTool result: {result.content}")
        except Exception as e:
            print(f"\nError calling tool: {e}")


if __name__ == "__main__":
    anyio.run(main)
