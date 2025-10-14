# Transports

OpenMCP wraps the reference MCP SDK transports so applications can focus on tool
logic instead of connection plumbing. Two transports ship out of the box:

* **STDIO** – newline-delimited JSON-RPC over `stdin`/`stdout`
* **Streamable HTTP** – POST/GET endpoint with optional SSE streams

Both are registered with `MCPServer` automatically. You can switch between them
via the constructor or at call time:

```python
server = MCPServer("demo")              # defaults to streamable HTTP

await server.serve()                     # -> Streamable HTTP on 127.0.0.1:3000
await server.serve(transport="stdio")   # -> STDIO
```

## HTTP security defaults

To align with `docs/mcp/core/transports/streamable-http.md`, OpenMCP enables DNS
rebinding protection on the HTTP transport by default. The server validates the
`Host` and `Origin` headers against:

* `127.0.0.1:*` and `localhost:*`
* `https://as.dedaluslabs.ai` – our forthcoming central authorization service

Override the configuration when constructing the server:

```python
from mcp.server.transport_security import TransportSecuritySettings

security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["dashboard.dedaluslabs.ai:443"],
    allowed_origins=["https://dashboard.dedaluslabs.ai"],
)

server = MCPServer("demo", http_security=security)
```

Passing `http_security=None` leaves validation disabled (useful for tests).
Call `server.configure_streamable_http_security(new_settings)` at runtime to adjust the guard or pass `None` to restore defaults.

### Authorization gateway (roadmap)

`https://as.dedaluslabs.ai` is reserved for the Dedalus Labs authorization
server. The default allow-list already includes this origin so that client and
server upgrades can adopt the gateway without configuration churn.
Integration with that service will land in a future release; until then it simply acts as an allow-listed origin.

## Custom transports

`MCPServer` exposes a lightweight registry. Any callable returning a
`BaseTransport` can be registered under a name:

```python
from openmcp.server.transports import BaseTransport

class InMemoryTransport(BaseTransport):
    async def run(self, **kwargs):
        read_stream, write_stream = kwargs["streams"]
        await self.server.run(
            read_stream,
            write_stream,
            self.server.create_initialization_options(),
            stateless=True,
        )

server.register_transport("memory", lambda srv: InMemoryTransport(srv))

await server.serve(transport="memory", streams=my_streams)
```

Transports created this way gain access to the full server surface (tool
registration, initialization options, etc.). All core transports are registered
using the same mechanism (`stdio`, `streamable-http`, `http`, `shttp`).

## Client helpers

`openmcp.client` works with any transport that yields the reference SDK stream
pairs. For serverless deployments, `lambda_http_client` implements the
spec-compliant POST flow without the long-lived GET stream:

```python
from openmcp.client import MCPClient, lambda_http_client

async with lambda_http_client("https://server/mcp") as (read_stream, write_stream, get_session_id):
    async with MCPClient(read_stream, write_stream) as client:
        await client.ping()
```

For full SSE support you can continue using the SDK’s `streamable_http_client`.
