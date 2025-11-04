# Ambient Registration Pattern

**Status**: DRAFT (implementation complete, DX may evolve before publication)

**Problem**: The MCP spec doesn't mandate *how* servers register tools, resources, and prompts—only what JSON-RPC messages they must answer. Most frameworks force you to call instance methods (`server.add_tool(fn)`), leaking server references into module globals or entangling registration with object lifetime. Multi-server scenarios become messy, and testability suffers when decorators hard-bind to a singleton.

**Solution**: Ambient registration via `ContextVar` scoping. Decorators (`@tool`, `@resource`, `@prompt`) attach metadata to functions *without* binding them to a server instance. When you enter `with server.binding():`, that server becomes the active context, and any decorated function defined in that scope automatically registers itself. Outside the context, the same function can be re-registered to a different server or remain unattached. This approach separates *declaration* (what the function is) from *registration* (which server it serves).

**OpenMCP**: The `@tool`, `@resource`, `@prompt`, `@resource_template`, and `@completion` decorators use per-capability `ContextVar` tokens to track the active server. Inside `server.binding()`, decorators immediately call the server's registration methods. Outside that scope, decorators only attach metadata attributes (`__openmcp_tool__`, `__openmcp_resource__`, etc.). You control registration timing and scope explicitly via the binding context manager.

## Design Rationale

### Why Ambient Over Instance Decorators?

Instance decorators (`@server.tool`) couple the function to the server at decoration time, which happens at module import. This creates several problems:

1. **Import-time side effects**: The server must exist before you can import the module containing your tools. Circular dependencies proliferate.
2. **Single-server coupling**: The function is permanently bound to one server instance. Testing with mock servers or serving the same function from multiple servers requires awkward workarounds.
3. **Global state leakage**: Frameworks typically use a singleton pattern to make `server` available everywhere. This makes testing harder and violates separation of concerns.
4. **Unclear ownership**: When `@server.tool` executes at import time, the server's lifecycle is unclear. Did someone start it already? Is it safe to mutate?

Ambient registration inverts this: decorators attach metadata, and the server *pulls* that metadata when you explicitly enter its binding scope. Benefits:

- **Explicit registration timing**: `with server.binding():` is a visible, testable boundary.
- **Multi-server support**: The same decorated function can be registered to multiple servers by using multiple binding blocks.
- **No import-time dependencies**: Decorators don't need the server to exist yet. Registration happens later, when you control it.
- **Thread/task isolation**: Each async task can bind to a different server without global state conflicts.

## ContextVar Mechanics

Python's `contextvars.ContextVar` provides task-local storage that works with both threading and `asyncio`. Each capability (tools, resources, prompts, completions, resource templates) maintains its own `ContextVar` token to track the currently active server:

```python
# From src/openmcp/tool.py
from contextvars import ContextVar

_ACTIVE_SERVER: ContextVar[MCPServer | None] = ContextVar(
    "_openmcp_active_server", default=None
)

def get_active_server() -> MCPServer | None:
    return _ACTIVE_SERVER.get()

def set_active_server(server: MCPServer) -> Any:
    return _ACTIVE_SERVER.set(server)

def reset_active_server(token: Any) -> None:
    _ACTIVE_SERVER.reset(token)
```

When a decorator executes:

1. It checks `get_active_server()` to see if any server is currently binding.
2. If found, it immediately calls the server's registration method (e.g., `server.register_tool(spec)`).
3. If not found, it only attaches the metadata to the function and returns.

This deferred registration pattern keeps decoration and binding separate.

## Binding Scope Semantics

The `MCPServer.binding()` method is a context manager that activates the server for all capability types:

```python
# From src/openmcp/server/app.py
@contextmanager
def binding(self):
    tool_token = set_tool_server(self)
    resource_token = set_resource_server(self)
    completion_token = set_completion_server(self)
    prompt_token = set_prompt_server(self)
    template_token = set_resource_template_server(self)
    try:
        yield self
    finally:
        reset_tool_server(tool_token)
        reset_resource_server(resource_token)
        reset_completion_server(completion_token)
        reset_prompt_server(prompt_token)
        reset_resource_template_server(template_token)
```

**Key properties**:

1. **Explicit scope**: Only code inside `with server.binding():` registers automatically.
2. **Nested-safe**: If you nest binding blocks (don't), the innermost wins. Each reset correctly restores the previous token.
3. **Exception-safe**: The `finally` block guarantees cleanup even if registration code raises.
4. **Multi-server safe**: Different tasks/threads can bind different servers without interference because `ContextVar` is task-local.

## When Binding Matters

### During Server Initialization

Binding is relevant **only** when you're defining the server's capabilities, typically at startup:

```python
from openmcp import MCPServer, tool

server = MCPServer("example")

# Outside binding: decorator attaches metadata but doesn't register
@tool()
def orphan() -> str:
    return "not registered yet"

# Inside binding: decorator registers immediately
with server.binding():
    @tool()
    def attached() -> str:
        return "registered to server"

print(server.tool_names)  # ["attached"]
```

### Not During Request Handling

Once the server is running and handling requests, binding is irrelevant. The registration phase is over. Request handlers execute in the context of an active session (via the SDK's `request_ctx`), not a binding context.

```python
# INCORRECT: Don't re-bind during request handling
@server.list_tools()
async def list_handler(request):
    with server.binding():  # Wrong! This is not a request context
        @tool()
        def dynamic() -> str:
            return "confused"
    # ...
```

Dynamic tool registration (adding tools after startup) is possible but requires explicit calls outside the binding context:

```python
# Correct: Manual registration after binding phase
def add_tool_at_runtime():
    @tool()
    def late_arrival() -> str:
        return "added later"

    spec = extract_tool_spec(late_arrival)
    server.register_tool(spec)
    await server.notify_tools_list_changed()  # if notifications enabled
```

## Comparison to Global Registration

Some frameworks use global registries where decorators append to a module-level list:

```python
# Hypothetical global pattern
_TOOLS = []

def tool(fn):
    _TOOLS.append(fn)
    return fn

# Later, server imports and consumes _TOOLS
server.load_tools(_TOOLS)
```

**Problems**:

- **Hidden state**: The list persists across test runs unless manually cleared.
- **Single registry**: You can't isolate tools for different servers without complex registry multiplexing.
- **Import order matters**: If the server imports the module before tools are decorated, the list is empty.

Ambient registration fixes this by making the server the source of truth. No global state accumulates; registration only happens when you explicitly bind.

## Same Function on Multiple Servers

Because decorators attach metadata to functions without binding them, you can register the same function to multiple servers by binding each one in sequence:

```python
from openmcp import MCPServer, tool

# Define the function once
@tool(description="Shared multiplication")
def multiply(a: int, b: int) -> int:
    return a * b

# Register to multiple servers
server_a = MCPServer("service-a")
server_b = MCPServer("service-b")

with server_a.binding():
    # Manually register to server_a
    server_a.register_tool(multiply)

with server_b.binding():
    # Manually register to server_b
    server_b.register_tool(multiply)

print(server_a.tool_names)  # ["multiply"]
print(server_b.tool_names)  # ["multiply"]
```

Alternatively, define the function inside each binding block to auto-register:

```python
with server_a.binding():
    @tool(description="Shared multiplication")
    def multiply(a: int, b: int) -> int:
        return a * b

with server_b.binding():
    # Re-use the same name; each server gets its own registration
    @tool(description="Shared multiplication")
    def multiply(a: int, b: int) -> int:
        return a * b
```

Both approaches work. Choose based on whether you want a single function object (explicit `register_tool`) or duplicate definitions (implicit auto-registration).

## Thread and Task Safety

`ContextVar` provides task-local (and thread-local) storage, meaning each async task or thread has its own view of the active server. This guarantees:

1. **No cross-task interference**: If task A binds `server_a` and task B binds `server_b`, they see different active servers.
2. **No race conditions**: Setting the active server doesn't mutate global state; it only affects the current task's context.
3. **Async-safe**: `asyncio` automatically propagates `ContextVar` values to child tasks created via `asyncio.create_task`, so nested async operations inherit the binding.

Example with concurrent tasks:

```python
import asyncio
from openmcp import MCPServer, tool

async def setup_server(name: str):
    server = MCPServer(name)
    with server.binding():
        @tool()
        def echo(text: str) -> str:
            return f"[{name}] {text}"
    print(f"{name} has tools: {server.tool_names}")

async def main():
    await asyncio.gather(
        setup_server("alice"),
        setup_server("bob"),
    )

asyncio.run(main())
# Output:
# alice has tools: ['echo']
# bob has tools: ['echo']
```

Each task's `with server.binding():` operates independently. No shared state leaks between them.

## Examples

### Multi-Server Registration

Register shared utilities across multiple services:

```python
from openmcp import MCPServer, tool

@tool(description="Get current Unix timestamp")
def timestamp() -> int:
    from time import time
    return int(time())

# Service 1: Internal utilities
internal_server = MCPServer("internal-tools")
with internal_server.binding():
    internal_server.register_tool(timestamp)

    @tool(description="Restart a service")
    def restart_service(name: str) -> str:
        # Only on internal server
        return f"Restarting {name}..."

# Service 2: Public API
public_server = MCPServer("public-api")
with public_server.binding():
    public_server.register_tool(timestamp)  # Reuse timestamp

    @tool(description="Get API version")
    def version() -> str:
        return "v1.2.3"

print(internal_server.tool_names)  # ["timestamp", "restart_service"]
print(public_server.tool_names)    # ["timestamp", "version"]
```

### Dynamic Tool Registration

Add tools after the server starts:

```python
from openmcp import MCPServer, tool, extract_tool_spec
import asyncio

server = MCPServer("dynamic")

with server.binding():
    @tool(description="Always available")
    def base_tool() -> str:
        return "base"

async def add_tool_at_runtime():
    # Define outside binding
    @tool(description="Added later")
    def dynamic_tool() -> str:
        return "dynamic"

    # Manually register
    spec = extract_tool_spec(dynamic_tool)
    server.register_tool(spec)

    # Notify clients if notifications enabled
    await server.notify_tools_list_changed()

async def main():
    print("Initial tools:", server.tool_names)  # ["base_tool"]

    await add_tool_at_runtime()

    print("After dynamic add:", server.tool_names)  # ["base_tool", "dynamic_tool"]

asyncio.run(main())
```

### Conditional Registration

Register tools based on environment or config:

```python
from openmcp import MCPServer, tool
import os

server = MCPServer("conditional")

with server.binding():
    @tool(description="Production-safe operation")
    def safe_op() -> str:
        return "safe"

    if os.getenv("ENABLE_DEBUG") == "1":
        @tool(description="Dangerous debug operation")
        def debug_op() -> str:
            return "debugging"

# Only registers debug_op if ENABLE_DEBUG=1
```

### Testing with Isolated Servers

Each test case gets a fresh server without shared state:

```python
from openmcp import MCPServer, tool
import pytest

@tool(description="Test fixture tool")
def test_tool() -> str:
    return "test"

@pytest.mark.asyncio
async def test_tool_registration():
    server = MCPServer("test-server")
    with server.binding():
        server.register_tool(test_tool)

    assert "test_tool" in server.tool_names

    result = await server.invoke_tool("test_tool")
    assert result.content[0].text == "test"

@pytest.mark.asyncio
async def test_another_server():
    # Completely isolated from the previous test
    another_server = MCPServer("another-test")
    with another_server.binding():
        server.register_tool(test_tool)

    assert "test_tool" in another_server.tool_names
```

### Cross-Module Registration

Organize tools in separate modules and register them all at once:

```python
# tools/math.py
from openmcp import tool

@tool(description="Add two numbers")
def add(a: int, b: int) -> int:
    return a + b

@tool(description="Multiply two numbers")
def multiply(a: int, b: int) -> int:
    return a * b

# tools/text.py
from openmcp import tool

@tool(description="Convert to uppercase")
def uppercase(text: str) -> str:
    return text.upper()

# server.py
from openmcp import MCPServer, extract_tool_spec
from tools import math, text

server = MCPServer("multi-module")

with server.binding():
    # Register all tools from math module
    for name in ["add", "multiply"]:
        fn = getattr(math, name)
        spec = extract_tool_spec(fn)
        if spec:
            server.register_tool(spec)

    # Register all tools from text module
    for name in ["uppercase"]:
        fn = getattr(text, name)
        spec = extract_tool_spec(fn)
        if spec:
            server.register_tool(spec)

print(server.tool_names)  # ["add", "multiply", "uppercase"]
```

## Internal Implementation Details

### Decorator Execution Flow

When you write `@tool()`, the decorator factory returns a closure that wraps your function:

```python
# Simplified from src/openmcp/tool.py
def tool(name=None, *, description=None, ...):
    def decorator(fn):
        spec = ToolSpec(name=name or fn.__name__, fn=fn, description=description, ...)
        setattr(fn, "__openmcp_tool__", spec)  # Attach metadata

        server = get_active_server()  # Check ContextVar
        if server is not None:
            server.register_tool(spec)  # Auto-register if binding

        return fn
    return decorator
```

Key steps:

1. Create a `ToolSpec` dataclass with the function and metadata.
2. Attach the spec to the function as `__openmcp_tool__` (similar attributes for other capabilities).
3. Query the `ContextVar` to see if a server is binding.
4. If yes, immediately call the server's registration method.
5. Return the original function unchanged (no wrapping).

### Binding Context Manager

The `server.binding()` method sets all five capability `ContextVar` tokens at once:

```python
# From src/openmcp/server/app.py (simplified)
@contextmanager
def binding(self):
    # Set each capability's active server
    tool_token = tool.set_active_server(self)
    resource_token = resource.set_active_server(self)
    prompt_token = prompt.set_active_server(self)
    completion_token = completion.set_active_server(self)
    template_token = resource_template.set_active_server(self)

    try:
        yield self
    finally:
        # Restore previous values (usually None)
        tool.reset_active_server(tool_token)
        resource.reset_active_server(resource_token)
        prompt.reset_active_server(prompt_token)
        completion.reset_active_server(completion_token)
        resource_template.reset_active_server(template_token)
```

Each `set_active_server` call returns a token representing the previous value. The `reset_active_server` calls in the `finally` block restore those previous values, ensuring nested contexts work correctly.

### Manual Registration Without Binding

If you want full control, skip the binding context and call registration methods directly:

```python
from openmcp import MCPServer, tool, extract_tool_spec

@tool(description="Manually registered")
def manual() -> str:
    return "manual"

server = MCPServer("manual-reg")

# No binding context; decorator only attached metadata
spec = extract_tool_spec(manual)
server.register_tool(spec)

print(server.tool_names)  # ["manual"]
```

This is useful when registration logic is complex (e.g., conditional, lazy, or driven by configuration files).

## See Also

- [Tools](tools.md) - Using the `@tool` decorator and schema inference
- [Resources](resources.md) - Using the `@resource` decorator for content serving
- [Prompts](prompts.md) - Using the `@prompt` decorator for template authoring
- [Schema Inference](schema-inference.md) - How OpenMCP generates JSON schemas from type hints
- [Result Normalization](result-normalization.md) - How function return values become MCP responses
- Official spec: [MCP Server Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
- Official spec: [MCP Server Resources](https://modelcontextprotocol.io/specification/2025-06-18/server/resources)
- Official spec: [MCP Server Prompts](https://modelcontextprotocol.io/specification/2025-06-18/server/prompts)
