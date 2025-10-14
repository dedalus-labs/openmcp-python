# Tools

**Problem**: MCP tools must appear in `tools/list`, report JSON Schemas, accept allow-list gating, and surface JSON-RPC errors consistently. Re-implementing this logic for each project is error prone.

**Solution**: Use decorators or ambient registries that turn plain Python callables into MCP tool descriptors, automatically handling schema generation, capability advertisement, and JSON-RPC plumbing.

**OpenMCP**: Decorate any callable with `@tool` inside `server.collecting()`. OpenMCP builds the input schema from type hints, wires the handler into the reference SDK, and exposes it both as a Python attribute and via `tools/call`. Pagination for `tools/list` obeys the standard cursor semantics (`docs/mcp/capabilities/pagination`): clients pass the opaque `cursor` token received in `nextCursor`, malformed cursors raise `INVALID_PARAMS`, and a missing `nextCursor` means the surface is exhausted. Allow-lists (`server.allow_tools(...)`) and `enabled` predicates give you fine-grained runtime control. The decorator accepts richer metadata—`title`, `annotations`, `output_schema`, and `icons`—which are surfaced through `types.Tool` / `ToolAnnotations` exactly as the spec describes.

```python
from openmcp import MCPServer, tool

server = MCPServer("calc")

with server.collecting():
    @tool(description="Human-friendly addition")
    def add(a: int, b: int) -> int:
        return a + b

    @tool(description="Uppercase text", enabled=lambda srv: srv.tool_names)
    def shout(text: str) -> str:
        return text.upper()

# Restrict exposed surface if needed
server.allow_tools(["add"])  # shout stays registered but hidden
```

- Spec receipts: `docs/mcp/spec/schema-reference/tools-list.md`, `tools-call.md`
- Input schema inference leans on `pydantic.TypeAdapter`; unsupported annotations fall back to permissive schemas.
- For list change notifications, toggle `NotificationFlags.tools_changed` and emit updates when your registry mutates.
