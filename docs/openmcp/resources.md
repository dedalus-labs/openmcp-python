# Resources

**Problem**: MCP resources must support both text and binary payloads, respect optional subscription semantics, and advertise metadata consistently across `resources/list`, `resources/read`, and related endpoints.

**Solution**: Centralize resource registration so every definition captures URI, friendly name, MIME type, and runtime callable, while providing hooks for subscribe/unsubscribe handlers when servers opt into change notifications.

**OpenMCP**: Decorate callables with `@resource` to expose text or binary content. Pagination for `resources/list` follows the spec receipts (`docs/mcp/capabilities/pagination`) by returning `nextCursor` tokens via the shared helper—invalid cursors raise `INVALID_PARAMS` (-32602) and the absence of `nextCursor` signals completion. OpenMCP normalizes return values for `resources/read` (text vs. base64 blob) and rehydrates capability metadata during initialization. Register subscription handlers via `@server.subscribe_resource()` / `@server.unsubscribe_resource()` to flip the `resources.subscribe` flag.

```python
from openmcp import MCPServer, resource

server = MCPServer("files")

with server.binding():
    @resource("resource://demo/readme", description="Project README")
    def readme() -> str:
        return "Welcome to the project!"

    @resource("resource://demo/logo", mime_type="application/octet-stream")
    def logo() -> bytes:
        with open("logo.bin", "rb") as fh:
            return fh.read()

@server.subscribe_resource()
async def on_subscribe(uri: str) -> None:
    print(f"client subscribed to {uri}")

@server.unsubscribe_resource()
async def on_unsubscribe(uri: str) -> None:
    print(f"client unsubscribed from {uri}")

async def refresh_index() -> None:
    # After mutating resource contents, notify subscribers.
    await server.notify_resource_updated("resource://demo/readme")
```

- Spec receipts: `docs/mcp/spec/schema-reference/resources-list.md`, `resources-read.md`, `resources-subscribe.md`
- Binary results are base64-encoded automatically (see `BlobResourceContents` behaviour in the reference SDK).
- `server.notify_resource_updated(uri)` emits `notifications/resources/updated` to every subscriber; invoke it from your mutation hooks or background tasks. See `docs/openmcp/hook-patterns.md` for webhook/background-watcher patterns.
- To support template discovery (`resources/templates/list`), implement ambient registration for templates or document the omission explicitly.
- Integration TODO: add transport-level tests (STDIO + Streamable HTTP) to
  assert notifications flow end-to-end under load (tracked in
  `tests/test_integration_subscriptions.py`).
- Resource handlers can import `get_context()` to emit logs or progress while
  serving the payload; see `docs/openmcp/context.md` for the helper API.
