# Progress Reporting

OpenMCP ships a dedicated progress helper that implements the semantics outlined
in [docs/mcp/core/progress/progress-flow.md](../mcp/core/progress/progress-flow.md)
and the `notifications/progress` schema documented in
[docs/mcp/spec/schema-reference/notifications-progress.md](../mcp/spec/schema-reference/notifications-progress.md).

## Usage

```python
from openmcp.progress import progress

@server.call_tool()
async def long_running(name: str, arguments: dict[str, object] | None):
    async with progress(total=5) as tracker:
        await tracker.advance(1, "downloaded corpus")
        await tracker.advance(3, "training model")
        await tracker.set(5, message="done")
```

The caller **must** have supplied `_meta.progressToken` on the request. When the
token is absent the helper raises `ValueError`, which surfaces to the client as
an MCP error response, matching the MCP requirements that tokens reference
active requests.

## behavioral Guarantees

* **Monotonic progress** – attempting to regress the progress value raises
  `ValueError` so the wire traffic always satisfies the MCP "progress must
  increase" rule.
* **Coalesced emission** – updates are sent at most `emit_hz` times per second
  (default 8 Hz). Bursty writers are coalesced and the final update is flushed
  on exit to provide at-least-once delivery.
* **Retry + jitter** – failed sends retry with a jittered backoff sourced from
  `SystemRandom`, avoiding correlated retries when multiple trackers emit
  concurrently.
* **Final flush** – the last progress sample is re-sent during shutdown even if
  the handler exits before the next scheduled emission, ensuring subscribers see
  the latest state.

## Instrumentation Hooks

`ProgressTelemetry` allows observability systems (OpenTelemetry, PostHog, custom
metrics) to attach callbacks:

```python
from openmcp.progress import ProgressTelemetry, progress

telemetry = ProgressTelemetry(
    on_start=lambda evt: meter.counter("progress_started").add(1, {"token": evt.token}),
    on_emit=lambda evt: meter.gauge("progress_value").record(evt.progress),
    on_close=lambda evt: logger.info("progress stream closed", extra={"emitted": evt.emitted}),
)

async with progress(total=100, telemetry=telemetry):
    ...
```

All callbacks are optional and fire synchronously on the worker task. The module
also exposes `set_default_progress_telemetry()` and
`set_default_progress_config()` to set global defaults at application start.

## Configuration

`ProgressConfig` tunes emission frequency and retry behavior:

```python
from openmcp.progress import ProgressConfig, progress

custom = ProgressConfig(emit_hz=4, retry_backoff=(0.1, 0.5))

async with progress(total=None, config=custom):
    ...
```

An `emit_hz` of `0` disables throttling (every update is sent immediately). The
helper uses `time.monotonic_ns()` to avoid clock skew and relies on AnyIO's
scheduling primitives so it behaves consistently across asyncio and Trio
backends.

## Usage Notes

`ProgressTracker` now exposes the explicit `advance` and `set` helpers only.
Legacy call sites that relied on `tracker.progress(...)` should be updated to
`tracker.advance(...)` for increments or `tracker.set(...)` when supplying an
absolute value. When working inside a tool, resource, or prompt, prefer
`get_context().progress(...)` so you stay within the OpenMCP surface without
referencing the SDK's `request_ctx` directly (see `docs/openmcp/context.md`).
