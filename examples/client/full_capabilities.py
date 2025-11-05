# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""DRAFT: Client with all capabilities enabled.

Demonstrates a fully-featured MCP client that advertises all optional
capabilities: sampling, elicitation, roots, and logging. This represents
a production-ready client configuration.

See: https://modelcontextprotocol.io/specification/2025-06-18/
See also: docs/openmcp/sampling.md, docs/openmcp/elicitation.md, docs/openmcp/roots.md

Run with:
    export ANTHROPIC_API_KEY=your-key
    uv run python examples/client/full_capabilities.py
"""

from __future__ import annotations

import os
from pathlib import Path

import anyio
import anthropic

from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, open_connection


SERVER_URL = "http://127.0.0.1:8000/mcp"


async def sampling_handler(
    _context: object, params: types.CreateMessageRequestParams
) -> types.CreateMessageResult | types.ErrorData:
    """Handle sampling requests with Anthropic API."""
    try:
        client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

        messages = [
            {"role": msg.role, "content": msg.content.text if hasattr(msg.content, "text") else str(msg.content)}
            for msg in params.messages
        ]

        model = "claude-3-5-sonnet-20241022"
        if params.modelPreferences and params.modelPreferences.hints:
            model = params.modelPreferences.hints[0].name

        response = await client.messages.create(
            model=model, messages=messages, max_tokens=params.maxTokens or 1024
        )

        return types.CreateMessageResult(
            model=response.model,
            content=types.TextContent(type="text", text=response.content[0].text),
            role=types.Role.assistant,
            stopReason=types.StopReason.endTurn,
        )
    except Exception as e:
        return types.ErrorData(code=-32603, message=f"Sampling failed: {e}")


async def elicitation_handler(
    _context: object, params: types.ElicitRequestParams
) -> types.ElicitResult | types.ErrorData:
    """Handle elicitation requests via CLI prompts."""
    try:
        print(f"\n{'=' * 60}")
        print(f"Server requests: {params.message}")
        print(f"{'=' * 60}\n")

        # For demo, auto-accept with minimal data
        # In production, you'd collect actual user input
        schema = params.requestedSchema
        properties = schema.get("properties", {})

        content: dict[str, object] = {}
        for field_name, field_schema in properties.items():
            field_type = field_schema.get("type", "string")
            if field_type == "boolean":
                content[field_name] = True
            elif field_type in ("integer", "number"):
                content[field_name] = 42
            else:
                content[field_name] = "demo-value"

        return types.ElicitResult(action="accept", content=content)
    except Exception as e:
        return types.ErrorData(code=-32603, message=f"Elicitation failed: {e}")


def logging_handler(params: types.LoggingMessageNotificationParams) -> None:
    """Handle logging notifications from server."""
    level = params.level.upper() if params.level else "INFO"
    print(f"[SERVER {level}] {params.data or params.logger}")


async def main() -> None:
    """Connect with all client capabilities enabled."""

    # Configure all capabilities
    capabilities = ClientCapabilitiesConfig(
        sampling=sampling_handler,
        elicitation=elicitation_handler,
        logging=logging_handler,
        enable_roots=True,
        initial_roots=[
            types.Root(uri=Path.cwd().as_uri(), name="Working Directory"),
            types.Root(uri=Path("/tmp").as_uri(), name="Temp"),
        ],
    )

    async with open_connection(
        url=SERVER_URL,
        transport="streamable-http",
        capabilities=capabilities,
    ) as client:
        print("Connected with all capabilities enabled")
        print(f"Server: {client.initialize_result.serverInfo.name}")
        print(f"Protocol: {client.initialize_result.protocolVersion}")

        # Show advertised capabilities
        caps = client.initialize_result.capabilities
        print("\nClient capabilities:")
        if hasattr(caps, "sampling") and caps.sampling:
            print("  - sampling: enabled")
        if hasattr(caps, "elicitation") and caps.elicitation:
            print("  - elicitation: enabled")
        if hasattr(caps, "roots") and caps.roots:
            print("  - roots: enabled")
            roots = await client.list_roots()
            for root in roots:
                print(f"    - {root.name}: {root.uri}")

        # List available tools
        tools_result = await client.send_request(
            types.ClientRequest(types.ListToolsRequest()),
            types.ListToolsResult,
        )
        print(f"\nAvailable tools: {len(tools_result.tools)}")
        for tool in tools_result.tools[:5]:  # Show first 5
            print(f"  - {tool.name}: {tool.description or 'no description'}")

        # Keep connection alive for server to use our capabilities
        print("\nClient ready. Server can now use all advertised capabilities.")
        await anyio.sleep(30)


if __name__ == "__main__":
    anyio.run(main)
