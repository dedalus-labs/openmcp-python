# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Client implementing sampling capability for MCP servers.

Demonstrates how to handle sampling/createMessage requests from servers that
need LLM completions during tool execution. This example integrates with the
Anthropic API to provide real completions.

See: https://modelcontextprotocol.io/specification/2025-06-18/client/sampling
See also: docs/openmcp/sampling.md

Run with:
    export ANTHROPIC_API_KEY=your-key
    uv run python examples/client/sampling_handler.py
"""

from __future__ import annotations

import os

import anyio
import anthropic

from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, open_connection


SERVER_URL = "http://127.0.0.1:8000/mcp"


async def sampling_handler(
    _context: object, params: types.CreateMessageRequestParams
) -> types.CreateMessageResult | types.ErrorData:
    """Handle sampling/createMessage requests by invoking Anthropic API.

    The server calls this when it needs an LLM completion. We convert MCP
    messages to Anthropic format, respect model preferences, and return
    the completion as a CreateMessageResult.
    """
    try:
        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        # Convert MCP SamplingMessage to Anthropic format
        messages = [
            {"role": msg.role, "content": msg.content.text if hasattr(msg.content, "text") else str(msg.content)}
            for msg in params.messages
        ]

        # Respect model preferences if provided, otherwise default to Sonnet
        model = "claude-3-5-sonnet-20241022"
        if params.modelPreferences and params.modelPreferences.hints:
            model = params.modelPreferences.hints[0].name

        # Call Anthropic API
        response = await client.messages.create(
            model=model,
            messages=messages,
            max_tokens=params.maxTokens or 1024,
        )

        # Convert response back to MCP format
        text_content = response.content[0].text if response.content else ""
        return types.CreateMessageResult(
            model=response.model,
            content=types.TextContent(type="text", text=text_content),
            role=types.Role.assistant,
            stopReason=types.StopReason.endTurn if response.stop_reason == "end_turn" else types.StopReason.maxTokens,
        )

    except Exception as e:
        # Return error to server instead of crashing
        return types.ErrorData(code=-32603, message=f"Sampling failed: {e}")


async def main() -> None:
    """Connect to a server that uses sampling and handle its requests."""
    capabilities = ClientCapabilitiesConfig(
        sampling=sampling_handler  # Advertise that we support sampling
    )

    async with open_connection(
        url=SERVER_URL,
        transport="streamable-http",
        capabilities=capabilities,
    ) as client:
        print("Connected with sampling capability enabled")
        print(f"Server info: {client.initialize_result.serverInfo.name}")

        # Now call a tool that triggers sampling on the server side
        # For demo, we just keep the connection alive for the server to initiate
        await anyio.sleep(60)


if __name__ == "__main__":
    anyio.run(main)
