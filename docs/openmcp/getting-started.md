# Getting Started with OpenMCP

**Problem**: Building a spec-compliant MCP server from scratch requires wiring the reference SDK, handling initialization responses, and juggling transport setup before you can expose a single tool or resource.

**Solution**: Standardize the bootstrapping workflow so every project gets the MCP handshake, capability advertisement, and transport selection right, without rewriting the same scaffolding.

**OpenMCP**: `MCPServer` wraps the reference SDK with opinionated defaults. You supply a server name (plus optional metadata) and register capabilities within a short `binding()` scope. Streamable HTTP is the default transport, but `serve(transport="stdio")` gives you parity with CLI runtimes.

```python
from openmcp import MCPServer, tool, get_context

server = MCPServer(
    "demo",
    instructions="Example MCP server",
    version="0.1.0",
)

with server.binding():
    @tool(description="Adds two numbers")
    async def add(a: int, b: int) -> int:
        ctx = get_context()  # raises LookupError outside a request
        await ctx.debug("adding numbers", data={"a": a, "b": b})
        result = a + b
        await ctx.info("addition complete", data={"result": result})
        return result

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.serve())  # defaults to Streamable HTTP
```

- Handshake receipts: `docs/mcp/core/lifecycle/lifecycle-phases.md`
- Transport helpers map to `docs/mcp/spec/overview/messages.md`
- Capability negotiation is surfaced via `NotificationFlags` and exposed through `create_initialization_options()`
- Request context helpers (`get_context`, logging, progress) derive from the
  utilities described in `docs/mcp/capabilities/logging/index.md` and
  `docs/mcp/core/progress/index.md`

## Examples

See ``examples/hello_trip`` and the accompanying documentation in `docs/openmcp/examples/hello-trip.md` for a runnable end-to-end walkthrough.
