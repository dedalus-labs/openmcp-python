# OpenMCP

> Minimal, spec-faithful Python framework for building Model Context Protocol (MCP) servers and clients.

[![Y Combinator S25](https://img.shields.io/badge/Y%20Combinator-S25-orange?style=flat&logo=ycombinator&logoColor=white)](https://www.ycombinator.com/launches/Od1-dedalus-labs-build-deploy-complex-agents-in-5-lines-of-code)

OpenMCP wraps the official MCP reference SDK with ergonomic decorators, automatic schema inference, and production-grade operational features—while maintaining 98% protocol compliance with MCP 2025-06-18.

**Philosophy**: Lightweight, extensible foundation. Batteries excluded unless performance-critical (phi-accrual failure detection, schema caching). Build your workflows—we're unopinionated except for `server.binding()` and spec-receipted patterns.

## Why it feels different

- Ambient registration is real: drop a `@tool` inside `with server.binding():` and it lands on *that* server, nothing global, no reload dance.
- You can change your mind at runtime—call `allow_tools`, re-run a binding block from a webhook, emit the spec’s listChanged notification, and clients stay in sync.
- Decorators store concrete `ToolSpec` objects, so the same function can be registered on multiple servers (or tenants) without hidden state.
- Every control surface points back to a spec citation (`docs/mcp/...`) so you can check what behavior we’re matching before you ship it.
- Transports and services are just factories; if you don’t like ours, register your own without forking the server.
- Context objects are plain async helpers (`get_context().progress()`, `get_context().info()`), not opaque singletons, so you can stub them in tests.

## Features

**Architecture**: Composable (injected services, swappable transports), one module per concern. Extend via custom services/transports/auth providers without touching core. [`CLAUDE.md`](CLAUDE.md) details design principles.

**Protocol**: MCP 2025-06-18, 98% compliant. All 9 capabilities (tools, resources, prompts, completion, logging, sampling, roots, elicitation). Lifecycle: initialize → initialized → operation. Every feature cites spec clause in `docs/mcp/spec/`.

**DX**: Ambient `@tool`/`@resource`/`@prompt` registration, Pydantic schema inference from type hints, sync/async tool support (transparent via `utils.maybe_await_with_args`), allow-lists, `get_context()` for progress/logging.

**Operational**: Progress coalescing, phi-accrual failure detection (adaptive vs binary alive/dead), thread-safe subscriptions (weak refs, auto-cleanup), request cancellation, schema caching.

**Transports**: Streamable HTTP (SSE) with DNS rebinding protection, STDIO. Custom via `register_transport()`. OAuth 2.1 framework (provider interface, no default).

**Types**: Full hints (mypy/pyright validated), Pydantic models for protocol types.

## Installation

```bash
# Install reference SDK
uv pip install -e references/python-sdk

# Or use your package manager
pip install -e references/python-sdk
```

## Quickstart

### Server

```python
from openmcp import MCPServer, tool

server = MCPServer("my-server")

with server.binding():
    @tool(description="Add two numbers")
    def add(a: int, b: int) -> int:
        return a + b

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.serve())  # Streamable HTTP on :8000
```

### Client

```python
from openmcp import MCPClient
from openmcp.client import lambda_http_client

async def main():
    async with lambda_http_client("http://127.0.0.1:8000/mcp") as (r, w, _):
        async with MCPClient(r, w) as client:
            # List tools
            tools = await client.session.list_tools()

            # Call tool
            result = await client.session.call_tool("add", {"a": 5, "b": 3})
            print(result.content)

import asyncio
asyncio.run(main())
```

## Capabilities

### Tools

```python
from typing import Literal

# Sync: pure computation, fast operations
@tool(description="Validate email")
def validate(email: str) -> bool:
    return "@" in email

# Async: I/O, network, database
@tool(description="Fetch data")
async def fetch(url: str) -> dict:
    async with httpx.AsyncClient() as client:
        return (await client.get(url)).json()

# Both work transparently - framework handles sync/async via utils.maybe_await_with_args
```

`tools/list`, `tools/call`, sync/async support, list change notifications, allow-lists, progress tracking. [`docs/openmcp/tools.md`](docs/openmcp/tools.md) | [`examples/hello_trip/server.py`](examples/hello_trip/server.py) | [`examples/tools/mixed_sync_async.py`](examples/tools/mixed_sync_async.py)

### Resources

```python
@resource("config://app/settings", mime_type="application/json")
def settings() -> dict:
    return {"theme": "dark"}

@resource_template("file://logs/{date}/{level}", mime_type="text/plain")
def logs(date: str, level: str) -> str:
    return f"Logs for {date} at {level}"

await server.notify_resource_updated("config://app/settings")  # Push to subscribers
```

Static resources, URI templates, subscriptions (`subscribe`/`unsubscribe`/`updated` notifications), text/blob content. [`docs/openmcp/resources.md`](docs/openmcp/resources.md) | [`examples/hello_trip/server.py`](examples/hello_trip/server.py)

### Prompts

```python
@prompt(name="code-review", arguments=[types.PromptArgument(name="language", required=True)])
def review(args: dict[str, str]) -> list[tuple[str, str]]:
    return [("assistant", f"You are a {args['language']} reviewer."), ("user", "Review code.")]
```

Reusable templates, typed arguments (required/optional), message coercion (tuples/dicts → `PromptMessage`). [`docs/openmcp/prompts.md`](docs/openmcp/prompts.md) | [`examples/hello_trip/server.py`](examples/hello_trip/server.py)

### Completion

```python
@completion(prompt="code-review")
async def review_completions(argument, ctx) -> list[str]:
    return ["Python", "JavaScript", "Rust"] if argument.name == "language" else []
```

Argument autocompletion for prompts/resource templates, 100-item limit enforced. [`docs/openmcp/completions.md`](docs/openmcp/completions.md) | [`examples/full_demo/server.py`](examples/full_demo/server.py)

### Progress & Logging

```python
@tool(description="Process batch")
async def process(items: list[str]) -> dict:
    ctx = get_context()
    async with ctx.progress(total=len(items)) as tracker:
        for item in items:
            await work(item)
            await tracker.advance(1, message=f"Processed {item}")
            await ctx.info("Item done", data={"item": item})
    return {"count": len(items)}
```

Token-based progress tracking (coalesced to prevent flooding), `logging/setLevel` with per-session levels (debug → emergency). [`docs/openmcp/progress.md`](docs/openmcp/progress.md) | [`docs/openmcp/context.md`](docs/openmcp/context.md)

### Sampling

```python
async def sampling_handler(ctx, params):
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text="AI response"),
        model="gpt-4"
    )

config = ClientCapabilitiesConfig(sampling=sampling_handler)
async with MCPClient(r, w, capabilities=config) as client:
    pass  # Handles sampling/createMessage from server
```

Servers request LLM completions via client. Concurrency semaphore (default: 4), circuit breaker (3 failures → 30s cooldown), 60s timeout. [`docs/openmcp/manual/client.md`](docs/openmcp/manual/client.md) | [`examples/full_demo/server.py`](examples/full_demo/server.py)

### Roots

```python
config = ClientCapabilitiesConfig(
    enable_roots=True,
    initial_roots=[types.Root(uri="file:///workspace", name="Workspace")]
)

@tool
@require_within_roots()
async def read_file(path: str) -> str:
    return Path(path).read_text()  # Path validated against roots, prevents traversal
```

Filesystem boundaries, `RootGuard` prevents path traversal, symlink resolution, versioned caching. [`docs/openmcp/manual/server.md`](docs/openmcp/manual/server.md)

### Elicitation

```python
async def elicitation_handler(ctx, params):
    return types.ElicitResult(action="accept", fields={"confirm": True})

config = ClientCapabilitiesConfig(elicitation=elicitation_handler)
```

Servers request structured user input. Schema validation (top-level properties only), 60s timeout, actions: accept/decline/cancel. NEW in MCP 2025-06-18. [`docs/openmcp/manual/client.md`](docs/openmcp/manual/client.md) | [`examples/full_demo/server.py`](examples/full_demo/server.py)

## Transports

**Streamable HTTP** (default): `await server.serve()` → `http://127.0.0.1:8000/mcp`. SSE streaming, DNS rebinding protection, origin validation, host allowlists, OAuth metadata endpoint.

**STDIO**: `await server.serve(transport="stdio")` for subprocess communication.

**Custom**: `register_transport("name", factory, aliases=["n"])` → `await server.serve(transport="name")`.

[`docs/openmcp/transports.md`](docs/openmcp/transports.md)

## Authorization

```python
class MyAuthProvider(AuthorizationProvider):
    async def validate(self, token: str) -> AuthorizationContext:
        return AuthorizationContext(subject="user-123", scopes=["read", "write"])

server = MCPServer(
    "secure-server",
    authorization=AuthorizationConfig(enabled=True, required_scopes=["read"], fail_open=False)
)
server.set_authorization_provider(MyAuthProvider())
```

OAuth 2.1 framework (RFC 9068 JWT profile), provider protocol, bearer token validation, scopes, WWW-Authenticate headers, metadata endpoint. No default provider—bring your own. [`docs/openmcp/design/authorization.md`](docs/openmcp/design/authorization.md) | [`examples/auth_stub/server.py`](examples/auth_stub/server.py)

## Examples

[`examples/`](examples/) contains runnable demos:

- [`hello_trip/`](examples/hello_trip/) - Server + client, tools/resources/prompts/transports
- [`full_demo/`](examples/full_demo/) - All capabilities, Brave Search integration
- [`auth_stub/`](examples/auth_stub/) - Authorization with custom provider
- [`progress_logging.py`](examples/progress_logging.py) - Context API, progress
- [`cancellation.py`](examples/cancellation.py) - Request cancellation
- [`advanced/custom_logging.py`](examples/advanced/custom_logging.py) - Structured log forwarding, color customization, enterprise log sinks
- [`advanced/feature_flag_server.py`](examples/advanced/feature_flag_server.py) - Dynamic tool registry with guardrails + feature flags

Start with `hello_trip/`, then `full_demo/` for advanced patterns.

**Extending**: Add custom services in `src/openmcp/server/services/`, transports via `register_transport()`, auth providers via `AuthorizationProvider` protocol. Existing implementations serve as templates.

## Documentation

| Document | Description |
|----------|-------------|
| [`examples/`](examples/) | **Start here**: Runnable examples for all features |
| [`docs/openmcp/features.md`](docs/openmcp/features.md) | Complete feature matrix with 98% compliance status |
| [`docs/openmcp/manual/server.md`](docs/openmcp/manual/server.md) | Server configuration and capability services |
| [`docs/openmcp/manual/client.md`](docs/openmcp/manual/client.md) | Client API and capability configuration |
| [`docs/openmcp/manual/security.md`](docs/openmcp/manual/security.md) | Security safeguards and authorization |
| [`docs/openmcp/transports.md`](docs/openmcp/transports.md) | Transport details and custom implementations |
| [`docs/openmcp/design/authorization.md`](docs/openmcp/design/authorization.md) | OAuth 2.1 authorization design |
| [`docs/mcp/spec/`](docs/mcp/spec/) | MCP protocol specification (receipts) |

**Quick reference**: [`docs/openmcp/cookbook.md`](docs/openmcp/cookbook.md) has isolated code snippets for copy-paste.

## Testing

```bash
PYTHONPATH=src uv run --python 3.12 python -m pytest
```

Covers: protocol lifecycle, registration, schema inference, subscriptions, pagination, authorization framework.

## Compliance

**MCP 2025-06-18**: 98% compliant. All mandatory features, all 9 optional capabilities (5 server, 4 client). 2% gap: authorization provider is plugin-based (framework exists, no default).

[`docs/openmcp/features.md`](docs/openmcp/features.md) has detailed matrix.

## Design

[`CLAUDE.md`](CLAUDE.md) details:

1. **Spec-first**: Every feature cites MCP clause in `docs/mcp/spec/`
2. **Minimal surface**: Full protocol, no batteries unless performance-critical
3. **Receipt-based**: Docstrings reference spec paths
4. **Single responsibility**: One module per concern (e.g., `services/tools.py`)
5. **Composable**: Injected services, swappable transports
6. **SDK delegation**: Reuse reference SDK for JSON-RPC/transport
7. **Dependency discipline**: Pydantic (schemas), anyio (async), starlette/uvicorn (HTTP). Optional extras (e.g., `orjson`, `rich`) stay out of the core to keep installs lean.

**Extend**: Add services in `src/openmcp/server/services/`, transports via `register_transport()`, auth via `AuthorizationProvider`.

## License

MIT
