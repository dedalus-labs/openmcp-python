# Cancellation

**DRAFT**: This document describes cancellation support in OpenMCP as of the 2025-06-18 spec revision. The client/server APIs are stable, but ergonomic helpers and integration patterns may evolve based on feedback.

**Problem**: Long-running MCP operations (file scans, database queries, LLM calls) can block indefinitely. Clients need a standard mechanism to cancel in-flight requests without leaking resources or corrupting server state.

**Solution**: The MCP specification defines `notifications/cancelled` as a standard notification that either party can send to signal cancellation of an in-progress request. The notification carries the request ID and an optional reason string.

**OpenMCP**: Clients call `cancel_request(request_id, reason)` to emit `notifications/cancelled`. Server implementations should check for cancellation during long operations and clean up resources when interrupted. Use anyio cancellation scopes (`move_on_after`, `fail_after`, `CancelScope`) to implement timeouts and integrate with the async cancellation protocol.

## Overview

Cancellation enables clean teardown of operations that:
- Execute for extended periods (minutes to hours)
- May become obsolete before completion (user changed requirements)
- Consume significant resources (memory, file handles, network connections)
- Risk timing out due to network latency or processing delays

The spec defines cancellation as **advisory**: the receiver SHOULD stop processing but MAY have already completed before the notification arrives. Both sides must handle race conditions gracefully.

## Specification

Per [`https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation`](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation):

- Either party can send `notifications/cancelled` with `requestId` and optional `reason` fields
- The request SHOULD still be in-flight, but MAY have already finished due to communication latency
- A client MUST NOT cancel its `initialize` request
- The receiving party SHOULD cease processing and MAY discard partial results
- No acknowledgment or error response is required

Spec receipts:
- `docs/mcp/spec/schema-reference/notifications-cancelled.md` (schema)
- `docs/mcp/core/cancellation/cancellation-flow.md` (flow diagrams)
- `docs/mcp/core/cancellation/timing-considerations.md` (race conditions)

## Client-Side Cancellation

OpenMCP clients expose `cancel_request()` to emit cancellation notifications:

```python
from openmcp import MCPClient, types
from openmcp.client import transports
import anyio

async with transports.streamable_http_client("http://127.0.0.1:8000/mcp") as (reader, writer, _):
    async with MCPClient(reader, writer) as client:
        # Issue a long-running request
        request = types.ClientRequest(
            types.CallToolRequest(name="analyze_logs", arguments={"path": "/var/log"})
        )

        # Cancel after 5 seconds
        async with anyio.create_task_group() as tg:
            async def invoke():
                result = await client.send_request(request, types.CallToolResult)
                print("Completed:", result)

            tg.start_soon(invoke)
            await anyio.sleep(5.0)
            await client.cancel_request(request.id, reason="user timeout")
            tg.cancel_scope.cancel()  # Also cancel local task
```

**Best practices**:
- Call `cancel_request()` before canceling the local task group to notify the server first
- Include a descriptive `reason` for debugging and telemetry
- Expect that the request MAY complete normally despite cancellation
- Do not retry the same `request.id` after cancellation

## Server-Side Handling

Servers receive cancellation notifications via the protocol layer but do not get automatic callbacks. Long-running operations should check for interruptions explicitly or integrate with anyio cancellation scopes.

### Explicit Timeout Patterns

Use `anyio.fail_after()` or `anyio.move_on_after()` to enforce operation deadlines:

```python
from openmcp import MCPServer, tool, types
from openmcp.errors import McpError
import anyio

server = MCPServer("file-processor")

with server.binding():
    @tool(description="Scan directory tree for matches")
    async def scan_directory(path: str, pattern: str, timeout_seconds: float = 30.0) -> dict:
        """Cancellable directory scanner with timeout."""
        try:
            async with anyio.fail_after(timeout_seconds):
                matches = []
                async for entry in walk_filesystem(path):
                    if pattern_matches(entry, pattern):
                        matches.append(entry)
                    # Periodic yield for cooperative cancellation
                    await anyio.sleep(0)
                return {"matches": matches, "count": len(matches)}
        except TimeoutError:
            raise McpError(
                types.ErrorCode.REQUEST_TIMEOUT,
                f"Scan exceeded {timeout_seconds}s timeout"
            )
```

**Key points**:
- `fail_after()` raises `TimeoutError` on expiry, which propagates to the client as an error result
- `move_on_after()` returns silently, allowing the handler to return partial results
- Periodic `await anyio.sleep(0)` checkpoints enable cooperative cancellation
- Convert timeouts into `REQUEST_TIMEOUT` errors for spec compliance

### Resource Cleanup

Use context managers and `try/finally` to ensure cleanup regardless of cancellation:

```python
from openmcp import tool
import anyio
import tempfile
import os

with server.binding():
    @tool(description="Process large file with cleanup")
    async def process_file(url: str) -> str:
        temp_path = None
        try:
            # Acquire resource
            temp_path = await download_to_temp(url)

            # Long-running operation with timeout
            async with anyio.move_on_after(60.0) as scope:
                result = await analyze_file(temp_path)

            if scope.cancel_called:
                return "Analysis incomplete (timed out)"
            return result
        finally:
            # Guaranteed cleanup
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
```

### Progress Tracking with Cancellation

Combine progress notifications with cancellation awareness:

```python
from openmcp import tool, get_context
import anyio

with server.binding():
    @tool(description="Batch processor with progress")
    async def batch_process(items: list[str], timeout: float = 120.0) -> dict:
        ctx = get_context()
        processed = 0
        errors = []

        try:
            async with ctx.progress(total=len(items)) as tracker:
                async with anyio.move_on_after(timeout) as scope:
                    for item in items:
                        try:
                            await process_item(item)
                            processed += 1
                            await tracker.advance(1, message=f"Processed {item}")
                        except Exception as e:
                            errors.append({"item": item, "error": str(e)})
                        # Cooperative cancellation checkpoint
                        await anyio.sleep(0)

                if scope.cancel_called:
                    await ctx.warning("Batch processing timed out", data={
                        "processed": processed,
                        "total": len(items),
                        "completion_pct": processed / len(items) * 100
                    })
        finally:
            pass  # Cleanup if needed

        return {
            "processed": processed,
            "failed": len(errors),
            "errors": errors[:10],  # Limit error verbosity
            "timed_out": scope.cancel_called if 'scope' in locals() else False
        }
```

## Long-Running Operations

For operations exceeding typical request timeouts (>30s), consider these patterns:

### 1. Chunked Processing

Break work into smaller units and check for cancellation between chunks:

```python
@tool(description="Process large dataset in chunks")
async def process_dataset(dataset_id: str, chunk_size: int = 1000) -> dict:
    ctx = get_context()
    total = await get_dataset_size(dataset_id)

    async with ctx.progress(total=total) as tracker:
        async with anyio.move_on_after(300.0) as scope:
            offset = 0
            while offset < total:
                chunk = await fetch_chunk(dataset_id, offset, chunk_size)
                await process_chunk(chunk)
                offset += len(chunk)
                await tracker.advance(len(chunk))

                # Check for external cancellation signal
                if scope.cancel_called:
                    break

            return {
                "processed": offset,
                "total": total,
                "complete": offset >= total
            }
```

### 2. Background Tasks with Polling

For truly long operations (hours), start a background task and provide a status endpoint:

```python
import uuid
from collections import defaultdict

# In-memory task registry (production: use Redis/DB)
active_tasks = defaultdict(dict)

@tool(description="Start long analysis job")
async def start_analysis(config: dict) -> dict:
    task_id = str(uuid.uuid4())

    async def run():
        try:
            active_tasks[task_id]["status"] = "running"
            result = await long_analysis(config)
            active_tasks[task_id]["result"] = result
            active_tasks[task_id]["status"] = "complete"
        except Exception as e:
            active_tasks[task_id]["error"] = str(e)
            active_tasks[task_id]["status"] = "failed"

    async with anyio.create_task_group() as tg:
        tg.start_soon(run)

    return {"task_id": task_id, "status_endpoint": f"resource://tasks/{task_id}"}

@tool(description="Check analysis status")
async def check_status(task_id: str) -> dict:
    if task_id not in active_tasks:
        raise McpError(types.ErrorCode.INVALID_PARAMS, "Unknown task_id")
    return active_tasks[task_id]
```

### 3. Streaming Results

Return partial results incrementally so clients get value even if interrupted:

```python
@tool(description="Stream search results")
async def search_stream(query: str, limit: int = 100) -> dict:
    ctx = get_context()
    results = []

    async with ctx.progress(total=limit) as tracker:
        async with anyio.move_on_after(30.0):
            async for result in search_engine(query):
                results.append(result)
                await tracker.advance(1)

                if len(results) >= limit:
                    break

    # Always return what we found, even if incomplete
    return {
        "results": results,
        "count": len(results),
        "complete": len(results) < limit
    }
```

## Examples

### Example 1: Cancellable Client Request

Complete client that cancels a slow tool invocation:

```python
import anyio
from openmcp import MCPClient, types
from openmcp.client import transports

async def main() -> None:
    async with transports.streamable_http_client("http://127.0.0.1:8000/mcp") as (reader, writer, _):
        async with MCPClient(reader, writer) as client:
            # Request that will take 10+ seconds
            request = types.ClientRequest(
                types.CallToolRequest(name="sleep", arguments={"seconds": 10})
            )

            async def invoke():
                try:
                    result = await client.send_request(request, types.CallToolResult)
                    print("Completed:", result)
                except Exception as e:
                    print("Failed:", e)

            # Cancel after 2 seconds
            async with anyio.create_task_group() as tg:
                tg.start_soon(invoke)
                await anyio.sleep(2.0)

                # Notify server first
                await client.cancel_request(request.id, reason="user timeout")
                print("Cancellation sent to server")

                # Then cancel local task
                tg.cancel_scope.cancel()

if __name__ == "__main__":
    anyio.run(main)
```

### Example 2: Server Tool with Timeout

Server implementing a cancellable sleep tool:

```python
from openmcp import MCPServer, tool
import anyio

server = MCPServer("demo")

with server.binding():
    @tool(description="Sleep with cancellation support")
    async def sleep(seconds: float) -> str:
        """Sleeps for the specified duration, respecting cancellation."""
        try:
            # Use fail_after to enforce hard timeout
            async with anyio.fail_after(seconds):
                await anyio.sleep(seconds)
            return f"Slept for {seconds}s"
        except TimeoutError:
            # This should not happen if seconds is correct, but handle anyway
            return f"Sleep interrupted after timeout"
        except anyio.get_cancelled_exc_class():
            # Explicit cancellation from task group
            return "Sleep cancelled by client"

# Run server (streamable HTTP transport)
if __name__ == "__main__":
    import anyio

    async def main() -> None:
        await server.serve_streamable_http(host="127.0.0.1", port=8000, log_level="info")

    anyio.run(main)
```

## See Also

- `docs/openmcp/tools.md` - Tool registration and execution
- `docs/openmcp/context.md` - Progress tracking and logging during tool execution
- `docs/openmcp/manual/client.md` - Client lifecycle and capability configuration
- `docs/mcp/core/cancellation/` - Official spec documentation on cancellation semantics
