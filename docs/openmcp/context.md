# Request Context Helper

OpenMCP exposes the ambient MCP request context through `get_context()` and the
`Context` wrapper. The goal is to keep handler code on the OpenMCP surface while
complying with the logging and progress semantics defined by the Model Context
Protocol.

Spec receipts:

- `docs/mcp/capabilities/logging/index.md`
- `docs/mcp/core/progress/index.md`
- `docs/mcp/spec/schema-reference/notifications-progress.md`

## Usage

```python
from openmcp import get_context, tool

@tool(description="Example tool that logs and reports progress")
async def heavy_task(size: int) -> str:
    ctx = get_context()  # raises LookupError if no request is active
    await ctx.info("heavy_task started", data={"size": size})

    async with ctx.progress(total=size) as tracker:
        for idx in range(size):
            await do_chunk(idx)
            await tracker.advance(1, message=f"chunk {idx + 1}/{size}")

    await ctx.debug("heavy_task finished")
    return "done"
```

`get_context()` is only available during an MCP request (tool calls, resource
reads, prompt rendering, completions). Calling it outside that window raises
`LookupError` to signal the missing preconditions.

## Logging helper

`Context.log(level, message, *, logger=None, data=None)` mirrors the payload
structure expected by the logging capability. Convenience wrappers for the
standard levels are provided (`debug`, `info`, `warning`, `error`). The `data`
parameter accepts any mapping and is merged into the emitted payload, making it
straightforward to supply structured metadata alongside human-readable text.

```python
ctx = get_context()
await ctx.warning("rate limit approaching", data={"quota": remaining})
```

## Progress reporting

Call `ctx.progress()` to obtain the coalescing progress tracker implemented in
`openmcp.progress`. The helper enforces monotonic progress values, performs
best-effort retries, and coalesces high-frequency updates so they respect the
guidance in the spec. For simple fire-and-forget updates, use
`ctx.report_progress(progress, total=None, message=None)`—it silently returns if
no progress token was provided by the client.

```python
ctx = get_context()

async with ctx.progress(total=5) as tracker:
    for step in range(5):
        await tracker.advance(1, message=f"step {step + 1}/5")

await ctx.report_progress(5, total=5, message="complete")
```

## Advanced scenarios

- The underlying `RequestContext` is available via `Context.session` and
  `Context.request_id` for advanced scenarios such as per-session storage.
- Context lifetimes are scoped automatically by the server. When writing unit
  tests that invoke handlers directly, either mock `get_context()` or construct
  a synthetic request using the reference SDK’s test helpers before calling the
  handler.
- When the ambient SDK `request_ctx` is missing (for example when using
  `MCPServer.invoke_tool()` outside of an MCP transport), `get_context()` will
  fail. This guards against accidentally calling transport-only features from
  test harnesses that do not simulate the MCP handshake.
