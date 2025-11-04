# Subscriptions

**DRAFT**: This capability is stable in the MCP 2025-06-18 specification but internal
APIs may change before 1.0 release.

---

## Overview

The subscription system enables clients to receive real-time notifications when
resources change. Rather than polling for updates, clients subscribe to specific
resource URIs and the server broadcasts `notifications/resources/updated` messages
when those resources are modified.

The `SubscriptionManager` implements a bidirectional index architecture that
provides O(1) lookup performance for both "which sessions are subscribed to this
resource?" and "which resources is this session subscribed to?" queries. This
dual-index design enables efficient broadcast notifications and automatic cleanup
when sessions disconnect.

**Key characteristics:**

- **O(1) lookup**: Dictionary-based bidirectional indexes eliminate linear scans
- **Thread-safe**: All operations protected by `anyio.Lock`
- **Automatic cleanup**: Weak references detect garbage-collected sessions
- **Stale session detection**: Failed notification delivery triggers pruning
- **Memory efficient**: `WeakSet` and `WeakKeyDictionary` prevent leaks

---

## Specification

The subscription capability is defined in the MCP 2025-06-18 specification:

- **Core capability**: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- **Subscribe operation**: https://modelcontextprotocol.io/specification/2025-06-18/basic/messages/resources-subscribe
- **Unsubscribe operation**: https://modelcontextprotocol.io/specification/2025-06-18/basic/messages/resources-unsubscribe
- **Update notification**: https://modelcontextprotocol.io/specification/2025-06-18/basic/messages/resources-updated

The spec requires:

1. Clients send `resources/subscribe` with a resource URI
2. Server tracks the subscription relationship
3. When the resource changes, server sends `notifications/resources/updated` to all subscribers
4. Clients send `resources/unsubscribe` to cancel subscription
5. Server must handle session cleanup gracefully

---

## Architecture

### Bidirectional Indexes

The `SubscriptionManager` maintains two complementary indexes:

```python
# Resource → Sessions (who is subscribed to this resource?)
_by_uri: dict[str, weakref.WeakSet[Any]]

# Session → Resources (what is this session subscribed to?)
_by_session: weakref.WeakKeyDictionary[Any, set[str]]
```

**Why bidirectional?**

- **Broadcasting**: When a resource updates, `_by_uri` provides instant access to all
  subscribers without scanning every session
- **Cleanup**: When a session disconnects, `_by_session` provides instant access to all
  its subscriptions so we can remove it from the corresponding `_by_uri` entries
- **Memory**: Weak references allow garbage collection of dead sessions without explicit
  unsubscribe calls

### Data Structure Choices

**`WeakSet` for subscribers:**

```python
subscribers = self._by_uri[uri]  # weakref.WeakSet[Session]
```

- Automatically removes garbage-collected sessions
- No manual cleanup required for normal disconnect cases
- Empty sets are removed from `_by_uri` to conserve memory

**`WeakKeyDictionary` for session tracking:**

```python
uris = self._by_session[session]  # set[str]
```

- Session object is the weak key; automatically removed when session dies
- Values are regular sets (URIs are strings, not weak references)
- Enables reverse lookup: "What is this session subscribed to?"

**Trade-offs:**

- **Pro**: Automatic memory management, no lingering references to dead sessions
- **Pro**: O(1) lookup in both directions (no list comprehensions or filters)
- **Con**: Weak references add slight overhead vs raw dicts
- **Con**: Must use `anyio.Lock` to prevent race conditions during GC

---

## Thread Safety

All public methods acquire `self._lock` (an `anyio.Lock`) before accessing the
indexes. This prevents data races in concurrent environments:

```python
async with self._lock:
    subscribers = self._by_uri[uri]
    subscribers.add(context.session)
    # ...
```

**Why `anyio.Lock` instead of `asyncio.Lock`?**

- OpenMCP uses `anyio` for transport-agnostic async I/O
- Compatible with both `asyncio` and `trio` backends
- Provides consistent semantics across environments

**Critical sections:**

- `subscribe_current` / `unsubscribe_current`: Modify both indexes atomically
- `prune_session`: Remove session from all URIs it's subscribed to
- `subscribers`: Return snapshot of current subscribers
- `snapshot`: Return shallow copies for debugging/testing

---

## Lifecycle

### Subscribe Flow

When a client sends `resources/subscribe`:

```python
async def subscribe_current(self, uri: str) -> None:
    context = _require_context()  # Extract session from request context
    async with self._lock:
        # 1. Add session to URI's subscriber set
        subscribers = self._by_uri[uri]  # defaultdict creates if missing
        subscribers.add(context.session)

        # 2. Add URI to session's subscription set
        uris = self._by_session.setdefault(context.session, set())
        uris.add(uri)
```

**Key details:**

- `_require_context()` extracts the session from `request_ctx` (a `ContextVar` set by
  the MCP transport layer during request handling)
- `defaultdict(weakref.WeakSet)` automatically creates a new `WeakSet` on first access
- Both indexes updated atomically within the lock

### Unsubscribe Flow

When a client sends `resources/unsubscribe`:

```python
async def unsubscribe_current(self, uri: str) -> None:
    context = _require_context()
    async with self._lock:
        # 1. Remove session from URI's subscriber set
        subscribers = self._by_uri.get(uri)
        if subscribers is not None:
            subscribers.discard(context.session)
            if not subscribers:  # If last subscriber, remove URI entry
                self._by_uri.pop(uri, None)

        # 2. Remove URI from session's subscription set
        uris = self._by_session.get(context.session)
        if uris is not None:
            uris.discard(uri)
            if not uris:  # If last URI, remove session entry
                with contextlib.suppress(KeyError):
                    del self._by_session[context.session]
```

**Key details:**

- `discard()` is used instead of `remove()` (no-op if session already gone)
- Empty sets are immediately removed to conserve memory
- Graceful handling if session or URI doesn't exist

### Notification Broadcasting

When a resource changes, the server calls `notify_resource_updated()` via
`ResourcesService`:

```python
async def notify_updated(self, uri: str) -> None:
    # 1. Get current subscribers (O(1) lookup)
    subscribers = await self._subscriptions.subscribers(uri)
    if not subscribers:
        return

    # 2. Build notification message
    notification = types.ServerNotification(
        types.ResourceUpdatedNotification(
            params=types.ResourceUpdatedNotificationParams(uri=uri)
        )
    )

    # 3. Broadcast to all subscribers, track failures
    stale: list[Any] = []
    for session in subscribers:
        try:
            await self._sink.send_notification(session, notification)
        except Exception as exc:
            self._logger.warning("Failed to notify subscriber: %s", exc)
            stale.append(session)

    # 4. Prune stale sessions
    for session in stale:
        await self._subscriptions.prune_session(session)
```

**Key details:**

- `subscribers()` returns a snapshot (list copy) to avoid holding lock during I/O
- Stale detection: If `send_notification()` fails, session is pruned
- Pruning removes session from all URIs it's subscribed to (see below)

### Session Pruning

When a session is detected as stale (notification delivery failed) or explicitly
disconnected:

```python
async def prune_session(self, session: Any) -> None:
    async with self._lock:
        # 1. Get all URIs this session is subscribed to
        uris = self._by_session.pop(session, None)
        if not uris:
            return

        # 2. Remove session from each URI's subscriber set
        for uri in uris:
            subscribers = self._by_uri.get(uri)
            if subscribers is not None:
                subscribers.discard(session)
                if not subscribers:  # Last subscriber for this URI
                    self._by_uri.pop(uri, None)
```

**Key details:**

- Single lock acquisition for entire operation (efficient bulk cleanup)
- Reverse lookup via `_by_session` provides O(1) access to all subscriptions
- Automatically removes empty URI entries

---

## Weak References and Cleanup

### Automatic GC Integration

Weak references allow Python's garbage collector to reclaim session objects even if
subscriptions still exist:

```python
# Session object is eligible for GC even though subscriptions exist
session = SomeSessionType()
await subscription_manager.subscribe_current("resource://demo")
# When session goes out of scope and is GC'd, WeakSet/WeakKeyDictionary
# automatically remove the references
```

**Why this matters:**

- Prevents memory leaks if client disconnects without unsubscribing
- No explicit cleanup code required in normal disconnect path
- Background GC handles removal asynchronously

### Manual Cleanup

For immediate cleanup (e.g., when connection closes), use `prune_session()`:

```python
async def on_disconnect(session: Any) -> None:
    await subscription_manager.prune_session(session)
```

This is more aggressive than relying on GC and ensures subscription state is
immediately consistent.

---

## Session Context Requirement

Subscription operations require an active request context:

```python
def _require_context():
    try:
        return request_ctx.get()  # ContextVar from mcp.server.lowlevel.server
    except LookupError as exc:
        err_msg = "Subscription operations require an active request context."
        raise RuntimeError(err_msg) from exc
```

**Why context is required:**

- The session object is not passed explicitly to resource handlers
- MCP transport layer sets `request_ctx` during request processing
- This provides ambient access to session without threading it through every call

**When context is available:**

- During `resources/subscribe` request handling
- During `resources/unsubscribe` request handling
- During `resources/read` if client subscribed

**When context is NOT available:**

- Outside request handling (background tasks)
- During server initialization
- In tests (unless manually injected)

---

## Debugging and Testing

### Snapshot API

The `snapshot()` method provides shallow copies of internal state for debugging:

```python
async def snapshot(self) -> tuple[dict[str, list[Any]], dict[Any, set[str]]]:
    """Return shallow copies for debugging/testing."""
    async with self._lock:
        by_uri = {uri: list(sessions) for uri, sessions in self._by_uri.items()}
        by_session = {session: set(uris) for session, uris in self._by_session.items()}
    return by_uri, by_session
```

**Usage in tests:**

```python
by_uri, by_session = await subscription_manager.snapshot()
assert "resource://demo" in by_uri
assert len(by_uri["resource://demo"]) == 2  # Two subscribers
```

**Important:**

- Returns copies, not live views (state may change after return)
- Acquires lock (don't call in hot paths)
- Intended for tests and debugging, not production code

---

## Examples

### Example 1: Basic Subscription Lifecycle

```python
from openmcp import MCPServer, resource

server = MCPServer("demo")

with server.binding():
    @resource("resource://demo/counter", description="A counter resource")
    def counter() -> str:
        return "counter value"

async def demo_lifecycle():
    # 1. Start server (sets up subscription manager)
    async with anyio.create_task_group() as tg:
        tg.start_soon(server.serve_stdio)

        # 2. Client subscribes (handled by transport layer)
        #    → SubscriptionManager.subscribe_current("resource://demo/counter")

        # 3. Resource changes
        await server.notify_resource_updated("resource://demo/counter")
        #    → ResourcesService.notify_updated() calls SubscriptionManager.subscribers()
        #    → Broadcasts notifications/resources/updated to all subscribers

        # 4. Client unsubscribes
        #    → SubscriptionManager.unsubscribe_current("resource://demo/counter")

        # 5. Resource changes again (no notifications sent)
        await server.notify_resource_updated("resource://demo/counter")
```

### Example 2: Stale Session Detection

```python
from openmcp import MCPServer, resource

server = MCPServer("demo")

with server.binding():
    @resource("resource://demo/data", description="Data resource")
    def data() -> str:
        return "data payload"

async def demo_stale_detection():
    # Client subscribes
    # ...

    # Notification fails (network error, client crashed, etc.)
    await server.notify_resource_updated("resource://demo/data")
    # → ResourcesService catches exception during send_notification()
    # → Adds session to stale list
    # → Calls subscription_manager.prune_session(stale_session)
    # → Session removed from all URI subscriptions
```

### Example 3: Testing Subscriptions

```python
import pytest
from mcp.client.session import ClientSession
from openmcp import MCPServer, resource, types

@pytest.mark.anyio
async def test_subscription_flow():
    server = MCPServer("test")

    with server.binding():
        @resource("resource://test/data", description="Test resource")
        def data() -> str:
            return "test data"

    # Set up client/server transport (see test_integration_subscriptions.py)
    # ...

    async with session:
        # Subscribe
        await session.send_request(
            types.ClientRequest(
                types.SubscribeRequest(
                    params=types.SubscribeRequestParams(uri="resource://test/data")
                )
            ),
            types.EmptyResult
        )

        # Trigger update
        await server.notify_resource_updated("resource://test/data")

        # Verify notification received
        assert notifications[-1].root.method == "notifications/resources/updated"
        assert notifications[-1].root.params.uri == "resource://test/data"

        # Unsubscribe
        await session.send_request(
            types.ClientRequest(
                types.UnsubscribeRequest(
                    params=types.UnsubscribeRequestParams(uri="resource://test/data")
                )
            ),
            types.EmptyResult
        )

        # Trigger update again (no notification)
        await server.notify_resource_updated("resource://test/data")
```

---

## See Also

- **Resources Guide**: `/docs/openmcp/resources.md` — Resource registration and listing
- **MCP Specification**: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
- **Integration Tests**: `/tests/test_integration_subscriptions.py` — End-to-end examples
- **Implementation**: `/src/openmcp/server/subscriptions.py` — Source code
