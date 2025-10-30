# OpenMCP Cookbook

Copy-paste examples. Self-contained.

## Server

### Minimal
```python
from openmcp import MCPServer, tool

server = MCPServer("my-server")

with server.binding():
    @tool(description="Echo text")
    def echo(text: str) -> str:
        return text

if __name__ == "__main__":
    import asyncio
    asyncio.run(server.serve())
```

### Schema Inference
```python
from typing import Literal

@tool(description="Search with filters")
def search(query: str, category: Literal["web", "images"] = "web", limit: int = 10) -> dict:
    return {"query": query, "category": category, "limit": limit}
```

### Allow-Lists
```python
from openmcp import allow_tools

with server.binding():
    @tool(description="Admin only")
    def delete_all() -> str: ...

    @tool(description="Public")
    def search() -> str: ...

allow_tools(server, ["search"])
```

## Resources

### Static
```python
from openmcp import resource

@resource("config://app/settings", name="App Settings", mime_type="application/json")
def settings() -> dict:
    return {"theme": "dark", "timeout": 30}
```

### Templates
```python
from openmcp import resource_template

@resource_template(
    uri_template="file://logs/{date}/{level}",
    name="Log files",
    mime_type="text/plain"
)
def logs(date: str, level: str) -> str:
    return f"Logs for {date} at {level}"
```

### Subscriptions
```python
from openmcp import resource, MCPServer

server = MCPServer("watcher")

@resource("data://metrics", mime_type="application/json")
def metrics() -> dict:
    return {"cpu": 45, "memory": 78}

async def on_change():
    await server.notify_resource_updated("data://metrics")
```

## Prompts

### Arguments
```python
from openmcp import prompt, types

@prompt(
    name="code-review",
    arguments=[
        types.PromptArgument(name="language", required=True),
        types.PromptArgument(name="style", required=False),
    ]
)
def review(args: dict[str, str]) -> list[tuple[str, str]]:
    lang = args["language"]
    style = args.get("style", "concise")
    return [("assistant", f"{style} reviewer for {lang}"), ("user", "Review code.")]
```

### Completions
```python
from openmcp import completion

@completion(prompt="code-review")
async def review_completions(argument: types.CompletionArgument, ctx) -> list[str]:
    if argument.name == "language":
        return ["Python", "JavaScript", "Rust", "Go"]
    if argument.name == "style":
        return ["concise", "detailed", "beginner-friendly"]
    return []
```

## Progress & Logging

### Progress
```python
from openmcp import tool, get_context

@tool
async def batch_process(items: list[str]) -> dict:
    ctx = get_context()
    async with ctx.progress(total=len(items)) as tracker:
        results = []
        for item in items:
            results.append(await process_item(item))
            await tracker.advance(1, message=f"Processed {item}")
    return {"count": len(results), "items": results}
```

### Logging
```python
from openmcp import tool, get_context

@tool
async def debug_tool(input: str) -> str:
    ctx = get_context()
    await ctx.debug("Starting", data={"input": input})
    try:
        result = risky_operation(input)
        await ctx.debug("Success", data={"result": result})
        return result
    except Exception as e:
        await ctx.error("Failed", data={"error": str(e)})
        raise
```

## Client

### Minimal
```python
from openmcp import MCPClient
from openmcp.client import lambda_http_client

async def main():
    async with lambda_http_client("http://127.0.0.1:8000/mcp") as (r, w, _):
        async with MCPClient(r, w) as client:
            tools = await client.session.list_tools()
            result = await client.session.call_tool("echo", {"text": "hello"})
```

### Capabilities
```python
from openmcp import MCPClient, ClientCapabilitiesConfig, types

async def sampling_handler(ctx, params):
    return types.CreateMessageResult(
        role="assistant",
        content=types.TextContent(type="text", text="AI response"),
        model="gpt-4"
    )

async def elicitation_handler(ctx, params):
    return types.ElicitResult(action="accept", fields={"confirmation": True})

config = ClientCapabilitiesConfig(
    sampling=sampling_handler,
    elicitation=elicitation_handler,
    enable_roots=True,
    initial_roots=[types.Root(uri="file:///workspace", name="Workspace")]
)

async with MCPClient(read_stream, write_stream, capabilities=config) as client:
    pass
```

## Roots

### Decorator
```python
from openmcp import tool, require_within_roots
from pathlib import Path

@tool
@require_within_roots()
async def read_file(path: str) -> str:
    return Path(path).read_text()
```

### Manual
```python
from openmcp.server.services.roots import RootGuard

async def safe_operation(path: str):
    guard = RootGuard(await server._roots.snapshot())
    if not await guard.is_within_roots(path):
        raise ValueError(f"Path {path} outside roots")
```

## Transports

### STDIO
```python
await server.serve(transport="stdio")

from mcp.client.stdio import stdio_client
async with stdio_client(["python", "server.py", "--transport", "stdio"]) as (r, w):
    async with MCPClient(r, w) as client:
        ...
```

### Lambda HTTP
```python
from openmcp.client import lambda_http_client

async with lambda_http_client("https://api.example.com/mcp") as (r, w, _):
    async with MCPClient(r, w) as client:
        result = await client.session.call_tool("process", args)
```

### Custom
```python
from openmcp.server.transports import register_transport

class MyTransport:
    def __init__(self, server):
        self.server = server
    async def run(self, **options):
        pass

register_transport("my-transport", lambda s: MyTransport(s), aliases=["mt"])
await server.serve(transport="my-transport")
```

## Authorization

### Provider
```python
from openmcp.server.authorization import AuthorizationProvider, AuthorizationContext

class MyAuthProvider(AuthorizationProvider):
    async def validate(self, token: str) -> AuthorizationContext:
        if token == "secret":
            return AuthorizationContext(
                subject="user-123",
                scopes=["read", "write"],
                claims={"org": "acme"}
            )
        raise ValueError("Invalid token")

server = MCPServer(
    "secure",
    authorization=AuthorizationConfig(enabled=True, required_scopes=["read"], fail_open=False)
)
server.set_authorization_provider(MyAuthProvider())
```

### Context
```python
from openmcp import tool, get_context

@tool
async def user_operation() -> dict:
    auth = get_context().session.app.auth
    return {"user": auth.subject, "scopes": auth.scopes, "org": auth.claims.get("org")}
```

## Advanced

### Notifications
```python
from openmcp import MCPServer, NotificationFlags

server = MCPServer(
    "dynamic",
    notification_flags=NotificationFlags(tools_changed=True, resources_changed=True, prompts_changed=True)
)

server.register_tool(new_tool_spec)
```

### Heartbeat
```python
server._ping.configure(interval=10.0, jitter=2.0, timeout=5.0, phi_threshold=8.0)
server._ping.on_suspect = lambda sid, phi: print(f"Suspected: {sid}")
server._ping.on_down = lambda sid: print(f"Down: {sid}")
```

### Schema Cache
```python
server._tools._schema_cache.clear()
```

## Testing

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_tool():
    @tool
    async def my_tool(x: int) -> int:
        return x * 2

    mock_ctx = AsyncMock()
```

## References

- `examples/` - Full examples
- `docs/openmcp/manual/server.md` - Server guide
- `docs/openmcp/manual/client.md` - Client guide
- `docs/openmcp/features.md` - Feature matrix
