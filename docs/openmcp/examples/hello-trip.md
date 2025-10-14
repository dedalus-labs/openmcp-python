# Hello Trip Example

This example stitches together the concepts from
``docs/mcp/core/understanding-mcp-servers`` and
``docs/mcp/core/understanding-mcp-clients``. It showcases how to build and use a
minimal MCP server with OpenMCP.

## Files

* ``examples/hello_trip/server.py`` – Registers a tool, resource, and prompt.
  Demonstrates `get_context()` for logging and progress reporting. Runs over
  either STDIO or Streamable HTTP.
* ``examples/hello_trip/client.py`` – Connects via the POST-only HTTP client,
  lists tools/resources, calls a tool, and fetches a prompt.

## Running the demo

In one terminal start the server (Streamable HTTP by default):

```bash
uv run python examples/hello_trip/server.py
```

In another terminal run the client:

```bash
uv run python examples/hello_trip/client.py
```

You should see output similar to:

```
Connected. Protocol version: 2025-06-18
Tools: ['plan_trip']
plan_trip result: {'summary': 'Plan: 5 days in Barcelona with budget $2500.00.', 'suggestion': 'Remember to book tickets early!'}
Resources: ['travel://tips/barcelona']
Prompt messages: [...]
```

To experiment with STDIO transports:

```bash
uv run python examples/hello_trip/server.py --transport stdio
```

and pair it with any MCP-compatible stdio client.

## Context helper in action

The `plan_trip` tool fetches the ambient request context, emits structured log
messages, and streams progress updates using the coalescing helper from
`docs/mcp/core/progress/index.md`. This mirrors the guidance in
`docs/mcp/capabilities/logging/index.md` while keeping handler code inside the
OpenMCP surface.
