# Tools

**Problem**: MCP tools must appear in `tools/list`, report JSON Schemas, accept allow-list gating, and surface JSON-RPC errors consistently. Re-implementing this logic for each project is error prone.

**Solution**: Use decorators or ambient registries that turn plain Python callables into MCP tool descriptors, automatically handling schema generation, capability advertisement, and JSON-RPC plumbing.

**OpenMCP**: Decorate any callable with `@tool` inside `server.binding()`. OpenMCP builds the input schema from type hints, wires the handler into the reference SDK, and exposes it both as a Python attribute and via `tools/call`. Pagination for `tools/list` obeys the standard cursor semantics (`docs/mcp/capabilities/pagination`): clients pass the opaque `cursor` token received in `nextCursor`, malformed cursors raise `INVALID_PARAMS`, and a missing `nextCursor` means the surface is exhausted. Allow-lists (`server.allow_tools(...)`) and `enabled` predicates give you fine-grained runtime control. The decorator accepts richer metadata—`title`, `annotations`, `output_schema`, and `icons`—which are surfaced through `types.Tool` / `ToolAnnotations` exactly as the spec describes.

```python
from openmcp import MCPServer, get_context, tool

server = MCPServer("calc")

with server.binding():
    @tool(description="Human-friendly addition")
    async def add(a: int, b: int) -> int:
        ctx = get_context()
        await ctx.debug("adding", data={"a": a, "b": b})
        return a + b

    @tool(description="Uppercase text", enabled=lambda srv: srv.tool_names)
    def shout(text: str) -> str:
        return text.upper()

# Restrict exposed surface if needed
server.allow_tools(["add"])  # shout stays registered but hidden
```

### Dependency-driven allow-lists

```python
from openmcp import MCPServer, Depends, get_context, tool

server = MCPServer("plans")
USERS = {"bob": {"tier": "basic"}, "alice": {"tier": "pro"}}


def get_current_user(user_id: str) -> dict[str, str]:
    return USERS[user_id]


def require_pro(user: dict[str, str]) -> bool:
    return user["tier"] == "pro"


with server.binding():

    @tool(description="Premium forecast", enabled=Depends(require_pro, get_current_user))
    async def premium(days: int = 7, ctx=Depends(get_context)) -> dict[str, str | int]:
        await ctx.info("running premium forecast", data={"days": days})
        return {"plan": "pro", "days": days}
```

- Spec receipts: `docs/mcp/spec/schema-reference/tools-list.md`, `tools-call.md`
- Input schema inference leans on `pydantic.TypeAdapter`; unsupported annotations fall back to permissive schemas.
- Return annotations automatically generate `outputSchema` metadata (non-object outputs are wrapped as `{ "result": ... }`) and the runtime normalizer produces matching `structuredContent` so clients can consume structured results directly.
- For list change notifications, toggle `NotificationFlags.tools_changed` and emit updates when your registry mutates.
- Use `get_context()` from `docs/openmcp/context.md` to emit logs or progress
  telemetry directly from tool handlers without importing SDK internals.
- `Depends()` supports nested dependencies and is cached per request via
  :class:`openmcp.context.Context`. Use it to express plan tiers, feature flags,
  or to inject request-scoped data (for example, ``ctx: Context``) without
  exposing extra parameters to clients.
