# Client Capability Examples

**DRAFT**: These examples demonstrate client-side MCP capabilities. All examples are self-contained and runnable.

## Files

### sampling_handler.py (99 LOC)
Demonstrates client handling of `sampling/createMessage` requests from servers. Integrates with the Anthropic API to provide real LLM completions when servers need them during tool execution.

**Key concepts**:
- Handler signature: `async def sampling_handler(context, params) -> CreateMessageResult | ErrorData`
- Message format conversion (MCP ↔ Anthropic)
- Model preference negotiation
- Error handling without crashing the connection

**Spec**: https://modelcontextprotocol.io/specification/2025-06-18/server/sampling

### elicitation_handler.py (138 LOC)
Demonstrates client handling of `elicitation/create` requests from servers. Uses CLI prompts to collect user input matching a JSON schema.

**Key concepts**:
- Schema-driven input collection
- Type coercion (boolean, integer, number, string)
- Three-way actions (accept, decline, cancel)
- Required vs optional field handling

**Spec**: https://modelcontextprotocol.io/specification/2025-06-18/server/elicitation

### roots_config.py (95 LOC)
Demonstrates client advertising filesystem roots to establish security boundaries. Shows both initial configuration and dynamic updates.

**Key concepts**:
- file:// URI construction (cross-platform)
- Initial roots via `ClientCapabilitiesConfig`
- Dynamic updates with `client.update_roots()`
- `notifications/roots/list_changed` broadcasting

**Spec**: https://modelcontextprotocol.io/specification/2025-06-18/client/roots

### full_capabilities.py (153 LOC)
Combines all client capabilities (sampling, elicitation, roots, logging) into a single production-ready client configuration.

**Key concepts**:
- Multiple capability handlers in one client
- Capability negotiation during initialization
- Logging notifications from servers
- Complete client setup pattern

## Running the Examples

All examples require a running MCP server at `http://127.0.0.1:8000/mcp`.

For sampling_handler.py:
```bash
export ANTHROPIC_API_KEY=your-key
uv run python examples/client/sampling_handler.py
```

For other examples:
```bash
uv run python examples/client/elicitation_handler.py
uv run python examples/client/roots_config.py
uv run python examples/client/full_capabilities.py
```

## See Also

- [Sampling documentation](../../docs/openmcp/sampling.md)
- [Elicitation documentation](../../docs/openmcp/elicitation.md)
- [Roots documentation](../../docs/openmcp/roots.md)
- [Full demo client](../full_demo/simple_client.py)
