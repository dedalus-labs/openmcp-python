# Pagination

**Status**: DRAFT (DX may change before publication)

**Problem**: MCP list endpoints must handle arbitrarily large collections without overwhelming clients or servers.

**Solution**: The spec mandates cursor-based pagination with opaque tokens. Clients request pages via `cursor` parameter, servers return sliced results plus optional `nextCursor` to continue iteration. Missing `nextCursor` signals exhaustion. Invalid cursors raise `INVALID_PARAMS` (-32602).

**OpenMCP**: All list operations default to 50 items per page (configurable via `MCPServer(pagination_limit=N)`). The `paginate_sequence` helper validates cursors and produces `nextCursor` only when more data exists.

## Specification

- **Spec Citation**: https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/pagination
- **Applicable Endpoints**:
  - `tools/list` → `ListToolsResult.nextCursor`
  - `resources/list` → `ListResourcesResult.nextCursor`
  - `prompts/list` → `ListPromptsResult.nextCursor`
  - `roots/list` → `ListRootsResult.nextCursor`
  - `resources/templates/list` → `ListResourceTemplatesResult.nextCursor`
- **Request Parameters**: `cursor` (string, optional) — opaque token from previous response
- **Response Fields**:
  - `nextCursor` (string, optional) — token to fetch next page; absent if no more results
- **Error Code**: `INVALID_PARAMS` (-32602) — malformed or unrecognized cursor

## Cursor Semantics

Cursors are **opaque strings** from the client's perspective. Clients treat them as black boxes; servers encode pagination state (OpenMCP uses integer offsets as strings).

**Lifecycle**:
1. Client sends `cursor=null` → server returns first page + `nextCursor` (if more data).
2. Client sends `cursor=<token>` → server returns next page + new `nextCursor` (if applicable).
3. `nextCursor` absent → end of collection.

**Validation**: Invalid cursors raise `INVALID_PARAMS` (-32602) with message `"Invalid cursor provided"`.

## Configuration

OpenMCP defaults to **50 items per page** across all list endpoints (`tools/list`, `resources/list`, `prompts/list`, `roots/list`, `resources/templates/list`). Override at server construction:

```python
from openmcp import MCPServer

server = MCPServer("my-server", pagination_limit=100)
```

The 50-item default balances latency against round-trip overhead. Tune higher for low-latency networks, lower for constrained clients.

## Implementation

The `paginate_sequence` helper in `src/openmcp/server/pagination.py`:

```python
def paginate_sequence(
    items: Sequence[T], cursor: str | None, *, limit: int
) -> tuple[list[T], str | None]:
    """Slice *items* by *cursor* and *limit*. Raises McpError (INVALID_PARAMS) if cursor is malformed."""
    start = 0
    if cursor:
        try:
            start = max(0, int(cursor))
        except ValueError as exc:
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Invalid cursor provided")) from exc
    end = start + limit
    page = list(items[start:end])
    next_cursor = str(end) if end < len(items) else None
    return page, next_cursor
```

Services call this uniformly during `list_*` operations (see `src/openmcp/server/services/tools.py`, `resources.py`).

## Error Handling

Malformed cursors raise `INVALID_PARAMS` (-32602):

```json
{
  "jsonrpc": "2.0",
  "id": 42,
  "error": {
    "code": -32602,
    "message": "Invalid cursor provided"
  }
}
```

Clients should treat `-32602` as unrecoverable and restart pagination from `cursor=null`. OpenMCP's offset-based cursors are stateless and never expire.

## Examples

### Paginating Through Tools

Enumerate all tools using cursor-based iteration:

```python
from openmcp import MCPClient

async def list_all_tools(client: MCPClient) -> list[str]:
    """Fetch all tool names by paginating through tools/list."""
    all_tools = []
    cursor = None

    while True:
        response = await client.list_tools(cursor=cursor)
        all_tools.extend(tool.name for tool in response.tools)

        if response.nextCursor is None:
            break
        cursor = response.nextCursor

    return all_tools
```

**Explanation**:
1. Start with `cursor=None` to fetch the first page.
2. Append results to accumulator.
3. If `nextCursor` is absent, exit loop.
4. Otherwise, use `nextCursor` as the next `cursor` parameter.

### Testing Pagination Boundaries

```python
from openmcp import MCPServer, tool, types

server = MCPServer("page-test", pagination_limit=10)

with server.binding():
    for i in range(25):
        fn = tool(description=f"Tool {i}")(lambda: None)
        fn.__name__ = f"t{i}"
        server.register_tool(fn)

# Page 1: tools 0-9, nextCursor="10"
result1 = await server.request_handlers[types.ListToolsRequest](
    types.ListToolsRequest(params=types.PaginatedRequestParams(cursor=None))
)
assert len(result1.root.tools) == 10 and result1.root.nextCursor == "10"

# Page 2: tools 10-19, nextCursor="20"
result2 = await server.request_handlers[types.ListToolsRequest](
    types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="10"))
)
assert len(result2.root.tools) == 10 and result2.root.nextCursor == "20"

# Page 3: tools 20-24 (partial), nextCursor=None
result3 = await server.request_handlers[types.ListToolsRequest](
    types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="20"))
)
assert len(result3.root.tools) == 5 and result3.root.nextCursor is None

# Past-end cursor: empty page, nextCursor=None
result4 = await server.request_handlers[types.ListToolsRequest](
    types.ListToolsRequest(params=types.PaginatedRequestParams(cursor="1000"))
)
assert len(result4.root.tools) == 0 and result4.root.nextCursor is None
```

The pattern applies identically to `resources/list`, `prompts/list`, and `roots/list`.

## Performance Notes

- **Memory**: OpenMCP loads all items before slicing. For tens of thousands of items, consider lazy generators or database cursors.
- **Latency**: Small pages (10-20) minimize per-request latency; large pages (100-200) reduce round-trips. Default (50) balances both.
- **Cursor Stability**: Integer offsets assume static collections. If items are added/removed during pagination, clients may skip or duplicate entries. Emit `notifications/tools/list_changed` to signal clients should restart.

## See Also

- **Specification**: https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/pagination
- **Tools Capability**: `docs/openmcp/tools.md` — tool listing and invocation
- **Resources Capability**: `docs/openmcp/resources.md` — resource listing and subscriptions
- **Prompts Capability**: `docs/openmcp/prompts.md` — prompt listing and retrieval
- **Roots Capability**: `docs/openmcp/roots.md` — client-advertised filesystem roots
- **Notifications**: `docs/openmcp/notifications.md` — `list_changed` events
- **Reference Implementation**: `src/openmcp/server/pagination.py` — `paginate_sequence` helper
- **Error Codes**: MCP JSON-RPC spec section on standard error codes
