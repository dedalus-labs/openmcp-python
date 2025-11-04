# Client Guide

`openmcp.client.MCPClient` wraps the reference SDK’s `ClientSession` to provide capability registration,
root management, cancellation, and the groundwork for authorization.

## Creating a Client

```python
from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, open_connection

async with open_connection(
    "https://localhost:8000/mcp",
    transport="streamable-http",
    capabilities=ClientCapabilitiesConfig(
        enable_roots=True,
        initial_roots=[{"uri": "file:///workspace"}],
        sampling=my_sampling_handler,
        elicitation=my_elicitation_handler,
        logging=my_logging_handler,
    ),
    client_info=types.Implementation(name="demo-client", version="0.1.0"),
) as client:
    await client.ping()
    tools = await client.send_request(
        types.ClientRequest(types.ListToolsRequest()),
        types.ListToolsResult,
    )
```

`open_connection()` wraps transport selection plus `MCPClient` construction into one `async with`
block. The name intentionally mirrors `asyncio.open_connection()` and `httpx.AsyncClient`’s
`aclose()` semantics so asynchronous Python developers recognize the pattern without extra
learning.[^open-connection-naming]

### Capability Configuration

| Attribute         | Purpose                                                  |
| ----------------- | -------------------------------------------------------- |
| `enable_roots`    | Advertises `roots/list`; enables root callbacks.         |
| `initial_roots`   | Seeds the root list before the first request.            |
| `sampling`        | Coroutine or function invoked when the server calls `sampling/createMessage`. |
| `elicitation`     | Handler invoked for `elicitation/create` requests.       |
| `logging`         | Optional observer for server `logging/message` notifications. |

Handlers receive the raw MCP models (`types.CreateMessageRequestParams`, etc.). Return the matching
result models (`types.CreateMessageResult`, `types.ElicitResult`).

### Roots API

- `await client.update_roots([...], notify=True)` replaces the root set and optionally emits
  `roots/list_changed`.
- `await client.list_roots()` returns a deep copy of the current list.
- Version numbers are tracked via `client.roots_version()`.

### Sending Requests

- `send_request(request, result_type, progress_callback=None)` is a thin proxy to
  `ClientSession.send_request`.
- `cancel_request(request_id, reason=None)` sends `notifications/cancelled` as per the MCP cancellation
  spec.

### Cancellation Flow

```python
request = types.ClientRequest(types.CallToolRequest(name="slow", arguments={}))
result_task = anyio.create_task_group()

with anyio.move_on_after(2.0) as scope:
    response = await client.send_request(request, types.CallToolResult)
if scope.cancel_called:
    await client.cancel_request(request.id, reason="timeout")
```

### Transport Helpers

| Helper                              | behavior |
| ----------------------------------- | --------- |
| `transports.stdio_client(cmd)`      | Spawns a child process and connects via STDIO. |
| `transports.streamable_http_client(url)` | Opens a persistent HTTP connection (POST + SSE GET). |
| `transports.lambda_http_client(url)` | Provides short-lived POST-only helper (no GET/SSE). |

Each helper returns `(reader, writer, get_session_id)` so `MCPClient` can be constructed easily.

[^open-connection-naming]: The helper mirrors established async APIs such as `asyncio.open_connection()`,
signalling that the call opens a live connection that should be managed via the surrounding context manager.

### Authorization Hooks (Preview)

The client-side authorization flow (PRM discovery, AS metadata caching, PKCE, token storage) will sit
behind a forthcoming `ClientAuthorizationConfig`. Until the authorization server is live the hooks are
no-ops. Once implemented, the wrapper will automatically:

1. Parse `WWW-Authenticate` challenges from 401 responses.
2. Discover PRM + AS metadata with cache-aside and single-flight fetches.
3. Perform dynamic client registration (RFC 7591) if enabled.
4. Run the authorization-code-with-PKCE flow using host callbacks.
5. Manage access/refresh tokens via a pluggable `TokenStore`.

The design is detailed in `docs/openmcp/design/authorization.md`. No client changes are required until
those features land.

## Example: Reading a Resource

```python
result = await client.send_request(
    types.ClientRequest(
        types.ReadResourceRequest(params=types.ReadResourceRequestParams(uri="travel://tips/barcelona"))
    ),
    types.ReadResourceResult,
)
for content in result.contents:
    if isinstance(content, types.TextResourceContents):
        print(content.text)
```

Refer to `docs/openmcp/manual/examples.md` for complete scripts demonstrating tools invocation,
resource reads, sampling callbacks, and cancellation.
