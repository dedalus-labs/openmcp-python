# OpenMCP

OpenMCP is a lightweight, spec-aligned framework for building Model Context
Protocol (MCP) servers. It reuses the official reference SDK to ensure full
protocol compliance while layering an ergonomic developer experience on top.

## Features

- Ambient tool/resource/prompt registration via ``@tool``, ``@resource`` and
  ``@prompt`` inside ``server.collecting`` (see
  `docs/mcp/spec/schema-reference/tools-list.md`,
  `docs/mcp/spec/schema-reference/resources-list.md`, and
  `docs/mcp/spec/schema-reference/prompts-list.md`).
- Built-in ``@completion`` decorator for `completion/complete` requests as
  defined in `docs/mcp/spec/schema-reference/completion-complete.md`.
- Resource subscriptions, with default handlers for
  ``resources/subscribe``/``resources/unsubscribe`` and
  ``server.notify_resource_updated(uri)`` to emit
  `notifications/resources/updated`.
- Logging capability wired into ``logging/setLevel``; the default handler maps
  protocol levels to Python logging levels. See
  `docs/openmcp/logging.md` and `docs/mcp/spec/schema-reference/logging-setlevel.md`.
- Roots capability for client-defined workspace boundaries. Configure roots via
  ``server.set_roots([...])`` and emit ``notifications/roots/list_changed`` when
  ``NotificationFlags(roots_changed=True)`` is enabled. See
  `docs/openmcp/roots.md` and `docs/mcp/capabilities/roots`.
- Allow-list gating and per-tool enable predicates.
- Automatic JSON Schema inference from function signatures via Pydantic
  ``TypeAdapter``.
- Optional logging helpers that mirror the shared logger from `api-final`.
- Compatible with the reference `mcp` SDK shipping in `_references/python-sdk`.
- Transport selection via `MCPServer(..., transport="stdio")` +
  `server.serve()` convenience method (Streamable HTTP is the default per the
  latest spec).

## Quickstart

1. **Install dependencies**

   ```bash
   uv pip install --system -e references/python-sdk
   uv pip install --system pytest pytest-asyncio pytest-cov pytest-xdist
   ```

2. **Create `demo_server.py`**

   ```python
   from openmcp import MCPServer, completion, prompt, resource, tool
   from openmcp.utils import get_logger

   log = get_logger(__name__)
   server = MCPServer("demo", instructions="Example MCP server")

   with server.collecting():
       @tool(description="Adds two numbers")
       def add(a: int, b: int) -> int:
           log.info("add called with %s + %s", a, b)
           return a + b

       @tool(description="Echo text back to the caller")
       def echo(text: str) -> str:
           return text

        @resource("resource://demo/greeting", description="Simple greeting")
        def greeting() -> str:
            return "Hello from OpenMCP"

        @prompt(
            "hello",
            description="Greets the supplied user",
            arguments=[{"name": "name", "required": True}],
        )
        def hello_prompt(args: dict[str, str]):
            return [("assistant", "You are a friendly concierge."), ("user", f"Greet {args['name']}")]

        @completion(prompt="hello")
        def hello_name(argument, _context):
            return ["Ada", "Grace", "Linus"]

   if __name__ == "__main__":
       import asyncio
       asyncio.run(server.serve())
   ```

3. **Run the server**

```bash
PYTHONPATH=src uv run --python 3.12 demo_server.py
```

This boots a Streamable HTTP server on `http://127.0.0.1:3000/mcp` with two
callable tools (`add` and `echo`), a prompt (`hello`), and completions for the
prompt arguments. Clients discover them using `tools/list`, `prompts/list`, and
invoke them with `tools/call` / `prompts/get` per the spec receipts above.

To target STDIO explicitly:

```python
server = MCPServer("demo", transport="stdio")
...
asyncio.run(server.serve())  # or server.serve(transport="stdio")
```

## Transport selection

Set the default transport when constructing the server and call
`await server.serve(...)`.  For alternative transports you can override the
argument (e.g., `await server.serve(transport="stdio")`) or invoke
transport-specific helpers directly (such as `serve_stdio`).

## Testing

```bash
PYTHONPATH=src uv run --python 3.12 python -m pytest
```

The suite targets protocol receipts directly: resource reads (text + binary),
tool invocation, prompt rendering, and completion limits.

## Logging

Use `openmcp.utils.get_logger` to obtain a configured logger. Override the log
level with the `OPENMCP_LOG_LEVEL` environment variable.

## Roadmap

- Plugin discovery via `importlib.metadata.entry_points`
- Schema inference via Pydantic `TypeAdapter`
- TypeScript/Go ports following the same semantics
- Support for additional transports (HTTP/SSE) using the reference SDK helpers

## Spec Receipts

- **Lifecycle**: `docs/mcp/core/lifecycle/lifecycle-phases.md`
- **Tools**: `docs/mcp/spec/schema-reference/tools-list.md`,
  `docs/mcp/spec/schema-reference/tools-call.md`
- **Resources**: `docs/mcp/spec/schema-reference/resources-list.md`,
  `docs/mcp/spec/schema-reference/resources-read.md`
- **Prompts**: `docs/mcp/spec/schema-reference/prompts-list.md`,
  `docs/mcp/spec/schema-reference/prompts-get.md`
- **Completions**: `docs/mcp/spec/schema-reference/completion-complete.md`

Notifications such as `resources/listChanged` remain opt-in; we only advertise
them when the corresponding handler is registered, matching the optional
capabilities described in `docs/mcp/capabilities/resources/capabilities.md`.
