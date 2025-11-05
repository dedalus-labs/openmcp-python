# Notifications

> **DRAFT**: This document describes internal implementation details that may change before the 1.0 release.

## Overview

MCP notifications are one-way, fire-and-forget messages sent from server to client without expecting a response. OpenMCP provides a lightweight notification broadcasting architecture built around the **ObserverRegistry** pattern and the **NotificationSink** abstraction.

This document explains the internal plumbing that powers list-changed notifications, progress updates, and logging messages. Understanding this architecture is useful when:

- Implementing custom notification types
- Debugging notification delivery issues
- Integrating with custom transport layers
- Tuning notification behavior for high-throughput scenarios

## Specification

Notifications are defined in the MCP specification:

- **Base**: https://modelcontextprotocol.io/specification/2025-06-18/spec/overview/messages
- **Built-in types**: https://modelcontextprotocol.io/specification/2025-06-18/schema-reference/notifications-message (and related schema entries)

The spec requires that notifications:

1. Follow JSON-RPC 2.0 format without an `id` field
2. Are sent asynchronously without blocking request handling
3. Must not expect or receive responses
4. May be silently dropped if the recipient is unavailable

## Architecture

OpenMCP's notification system has two core abstractions:

### NotificationSink

The `NotificationSink` protocol defines how notifications reach sessions:

```python
from typing import Protocol, Any

class NotificationSink(Protocol):
    """Abstract destination for server-initiated notifications."""

    async def send_notification(
        self,
        session: Any,
        notification: types.ServerNotification
    ) -> None: ...
```

This abstraction allows different transport layers (stdio, HTTP, WebSocket) to handle notification delivery without coupling the notification logic to transport details.

**Default implementation**:

```python
class DefaultNotificationSink:
    """Fallback sink that sends notifications directly via the session object."""

    async def send_notification(
        self,
        session: Any,
        notification: types.ServerNotification
    ) -> None:
        await session.send_notification(notification)
```

The default sink delegates to the session's built-in `send_notification` method, which the MCP reference SDK provides.

### ObserverRegistry

The `ObserverRegistry` tracks which sessions are interested in receiving notifications and handles broadcasting to them:

```python
class ObserverRegistry:
    """Tracks sessions interested in list change notifications."""

    def __init__(self, sink: NotificationSink) -> None:
        self._observers: weakref.WeakSet[Any] = weakref.WeakSet()
        self._sink = sink
```

Key design decisions:

1. **Weak references**: Sessions are stored in a `weakref.WeakSet`, ensuring that closed sessions are automatically garbage collected without explicit cleanup
2. **Single sink per registry**: Each registry uses one sink for all notifications
3. **Session tracking**: Observers are automatically registered when they call list operations

#### Session Registration

Sessions are implicitly registered when they call list operations (e.g., `tools/list`, `resources/list`). The service calls `remember_current_session()`:

```python
def remember_current_session(self) -> None:
    try:
        context = request_ctx.get()
    except LookupError:  # No active request
        return
    self._observers.add(context.session)
```

This uses the MCP SDK's `request_ctx` context variable to retrieve the current session from the active request context. If called outside a request (e.g., during server initialization), the lookup fails gracefully and no session is registered.

#### Broadcasting

When a list changes, services call `broadcast()` to notify all registered observers:

```python
async def broadcast(self, notification, logger) -> None:
    if not self._observers:
        return

    stale: list[Any] = []
    for session in list(self._observers):
        try:
            await self._sink.send_notification(session, notification)
        except Exception as exc:
            logger.warning(
                "Failed to notify observer %s: %s",
                getattr(session, "name", repr(session)),
                exc
            )
            stale.append(session)
            await anyio.lowlevel.checkpoint()

    for session in stale:
        self._observers.discard(session)
```

Broadcasting is **best-effort**:

- Failed notifications are logged but don't stop other deliveries
- Stale sessions (those that raise exceptions) are removed after the broadcast completes
- An explicit `anyio.lowlevel.checkpoint()` prevents long-running broadcasts from starving other tasks

#### Cleanup

Manual cleanup is rarely needed due to weak references, but the registry provides:

```python
def clear(self) -> None:
    self._observers.clear()
```

This is primarily used in tests or when shutting down a server instance.

## Built-in Notifications

OpenMCP emits several notification types defined by the MCP spec:

### List Changed Notifications

Sent when the available set of tools, resources, prompts, or roots changes:

- **`notifications/tools/list_changed`**: Tool list was modified
- **`notifications/resources/list_changed`**: Resource list was modified
- **`notifications/prompts/list_changed`**: Prompt list was modified
- **`notifications/roots/list_changed`**: Root list was modified

These are sent via `ObserverRegistry.broadcast()` after registration/deregistration operations.

**Example from ToolsService**:

```python
async def _notify_list_changed(self) -> None:
    notification = types.ServerNotification(
        types.ToolListChangedNotification(params=None)
    )
    await self.observers.broadcast(notification, self._logger)
```

### Progress Notifications

Sent during long-running operations to report progress. The `openmcp.progress` module handles these with more sophisticated logic (coalescing, retries, monotonicity enforcement).

Progress notifications bypass `ObserverRegistry` entirely—they're sent directly via `session.send_progress_notification()` because they target a specific session identified by a `progressToken`, not a broadcast audience.

**Spec**: https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress

### Message Notifications (Logging)

Sent when server code logs messages. The `LoggingService` implements custom filtering and routing logic:

```python
async def _broadcast(
    self,
    level: types.LoggingLevel,
    numeric_level: int,
    data: Any,
    logger_name: str | None
) -> None:
    async with self._lock:
        targets = list(self._session_levels.items())

    if not targets:
        return

    params = types.LoggingMessageNotificationParams(
        level=level, logger=logger_name, data=data
    )
    notification = types.ServerNotification(
        types.LoggingMessageNotification(params=params)
    )

    stale: list[Any] = []
    for session, threshold in targets:
        if numeric_level < threshold:
            continue  # Don't send if below session's configured level
        try:
            await self._sink.send_notification(session, notification)
        except Exception:
            stale.append(session)

    # Cleanup stale sessions...
```

The logging service maintains per-session log level thresholds and only sends messages that meet or exceed each session's configured level.

**Spec**: https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging

## Stale Session Cleanup

Both `ObserverRegistry` and `LoggingService` implement a consistent stale session cleanup pattern:

1. Collect sessions that fail notification delivery into a `stale` list
2. After attempting all notifications, remove stale sessions from tracking structures
3. Use weak references to ensure sessions are garbage collected

This ensures that closed or disconnected sessions don't accumulate indefinitely in memory.

## Custom Notifications

To emit custom notifications from your server code:

### 1. Define the notification type

Custom notifications must follow the MCP notification schema. If using the reference SDK's type system:

```python
from mcp import types

# Custom notification params
class CustomNotificationParams(types.BaseModel):
    event_type: str
    payload: dict[str, Any]

# Custom notification wrapper
class CustomNotification(types.BaseModel):
    method: str = "notifications/custom/event"
    params: CustomNotificationParams
```

### 2. Access the session from request context

Use the MCP SDK's `request_ctx` to get the current session:

```python
from mcp.server.lowlevel.server import request_ctx

try:
    context = request_ctx.get()
    session = context.session
except LookupError:
    # Called outside request context
    return
```

### 3. Send the notification

Send directly via the session or use a `NotificationSink`:

```python
# Direct send
notification = types.ServerNotification(
    CustomNotification(
        params=CustomNotificationParams(
            event_type="threshold_exceeded",
            payload={"value": 42, "threshold": 10}
        )
    )
)
await session.send_notification(notification)

# Via sink (if you have one)
await sink.send_notification(session, notification)
```

### Complete Example

```python
from mcp import types
from mcp.server.lowlevel.server import request_ctx
from openmcp import tool

class ThresholdEventParams(types.BaseModel):
    value: float
    threshold: float
    exceeded_at: str

class ThresholdNotification(types.BaseModel):
    method: str = "notifications/threshold/exceeded"
    params: ThresholdEventParams

@tool()
async def check_threshold(value: float, threshold: float = 10.0):
    """Check if value exceeds threshold and emit notification."""
    if value > threshold:
        # Emit custom notification
        try:
            context = request_ctx.get()
            notification = types.ServerNotification(
                ThresholdNotification(
                    params=ThresholdEventParams(
                        value=value,
                        threshold=threshold,
                        exceeded_at=datetime.utcnow().isoformat()
                    )
                )
            )
            await context.session.send_notification(notification)
        except LookupError:
            pass  # No active request context

    return {"exceeded": value > threshold}
```

**Important notes**:

- Custom notifications are not part of the MCP spec and may not be understood by all clients
- Use well-documented method names (e.g., `notifications/<domain>/<event>`)
- Consider whether your use case would be better served by returning data in the response instead
- Progress and logging use specialized helpers (`progress()` and `LoggingService`) rather than raw notifications

## Performance Considerations

### Broadcast Overhead

Broadcasting scales linearly with the number of registered sessions: O(n) where n is the number of observers. For most applications this is acceptable, but high-frequency notifications to hundreds of sessions may require optimization:

1. **Batching**: Accumulate changes and broadcast once per time window
2. **Filtering**: Only register sessions that explicitly opt in
3. **Tiering**: Separate "critical" from "informational" notification channels

### Weak References

Using `weakref.WeakSet` provides automatic cleanup but has trade-offs:

- **Pros**: No explicit session lifecycle management, prevents memory leaks
- **Cons**: Slight overhead on each access, non-deterministic cleanup timing

If deterministic cleanup is critical (e.g., for external resource management), add explicit session teardown hooks instead.

### Coalescing

Progress notifications implement coalescing to reduce notification volume. List-changed notifications currently do not coalesce, but `RootsService` implements debouncing for `roots/list_changed` with a 250ms delay.

If you need similar behavior for custom notifications, implement a debouncing wrapper around the registry.

## See Also

- [Progress](./progress.md) — Progress notification implementation with coalescing
- [Ping & Heartbeat](./ping.md) — Keepalive notifications
- [Cancellation](./cancellation.md) — Cancellation notification handling
- [Logging](../manual/logging.md) — Logging capability and message notifications
- [Subscriptions](./subscriptions.md) — Resource update notifications
- MCP Spec: [Notifications](https://modelcontextprotocol.io/specification/2025-06-18/spec/overview/messages#notifications)
