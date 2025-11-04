# Ping & Heartbeat

**DRAFT**: This document describes the current OpenMCP heartbeat implementation and may change before public release.

**Problem**: Long-lived MCP sessions require keepalive probing to detect stale connections, but binary alive/dead decisions are fragile in networks with transient faults. Clients need adaptive failure detection that balances responsiveness with tolerance for intermittent delays.

**Solution**: Implement ping/pong with phi-accrual failure detection, which computes a continuous suspicion score instead of flipping between binary states. Combine this with exponentially weighted moving average (EWMA) round-trip time tracking, jittered heartbeats, and configurable thresholds to prevent premature session evictions.

**OpenMCP**: The `PingService` provides session registration, suspicion scoring, and an automatic heartbeat loop. Register sessions when they connect, optionally start a background heartbeat, and install callbacks for `on_suspect` and `on_down` events. The implementation follows the base spec at `https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping` while extending it with phi-accrual scoring (lines 236-278 in `src/openmcp/server/services/ping.py`) and EWMA RTT tracking for production-grade reliability.

---

## Specification

Per the MCP specification:
- **Ping request**: Client or server sends `ping` with no parameters.
- **Pong response**: Recipient returns empty result `{}` immediately.
- **Purpose**: Verify network path liveness and measure round-trip latency.

OpenMCP extends this foundation with adaptive failure detection to avoid false positives in unreliable networks and to provide gradual suspicion signals before declaring sessions dead.

Spec receipts: `docs/mcp/spec/schema-reference/utilities/ping.md`

---

## Phi-Accrual Failure Detection

Binary heartbeats force a hard cutoff: after *N* missed pings, the session is dead. This approach fails when networks exhibit transient delays—a slow ping might arrive just after the threshold, causing unnecessary disconnections.

**Phi (φ) accrual** computes a continuous suspicion score based on the probability distribution of inter-arrival times. As time passes without a successful ping, φ rises smoothly. When φ exceeds a threshold (default: 5.0), the session is considered suspect; when φ climbs further and consecutive failures accumulate, the session is marked down.

### How It Works

1. **Track inter-arrival intervals**: Record the time between consecutive successful pings.
2. **Model as exponential distribution**: Compute `λ = 1 / mean_interval`.
3. **Calculate CDF**: `P(T ≤ t) = 1 - exp(-λ * t)` gives the probability that the next ping arrives within `t` seconds.
4. **Suspicion score**: `φ = -log10(1 - CDF)`. Higher φ means higher suspicion.
5. **Threshold check**: When `φ > phi_threshold`, treat the session as suspect; when `consecutive_failures > failure_budget`, declare it down.

This formula adapts to each session's observed latency profile. A consistently fast session will show high φ after a short delay; a historically slow session tolerates longer gaps.

**Key Parameters**:
- `phi_threshold`: Default 3.0 (99.9% confidence). Higher values tolerate more variance.
- `failure_budget`: Default 3 consecutive failures before marking down.
- `history_size`: Default 32 intervals for rolling window.
- `ewma_alpha`: Default 0.2 for RTT smoothing.

Reference: Akka failure detector, Cassandra gossip protocols.

---

## Configuration

The `PingService` constructor accepts:

```python
PingService(
    notification_sink=None,          # For emitting structured logs
    logger=None,                     # Python logger for events
    ewma_alpha=0.2,                  # EWMA smoothing factor
    history_size=32,                 # Rolling window size
    failure_budget=3,                # Consecutive failures before down
    default_phi=5.0,                 # Suspicion threshold
    on_suspect=None,                 # Callback: fn(session, phi)
    on_down=None,                    # Callback: fn(session)
)
```

Heartbeat configuration (passed to `start_heartbeat`):

```python
start_heartbeat(
    task_group,                      # anyio.TaskGroup for background task
    interval=5.0,                    # Base interval in seconds
    jitter=0.2,                      # ±20% randomization
    timeout=2.0,                     # Per-ping timeout
    phi_threshold=None,              # Override default_phi
    max_concurrency=None,            # Optional semaphore limit
)
```

**Jitter**: Prevents synchronized probes across multiple sessions. With `jitter=0.2`, the next ping fires in `[interval * 0.8, interval * 1.2]`.

**Timeout**: Each `ping()` wraps the `session.send_ping()` call in `anyio.fail_after(timeout)`, raising `TimeoutError` if the pong doesn't arrive.

---

## Heartbeat Setup

### Basic Usage

```python
from openmcp.server.services.ping import PingService
import anyio

ping_service = PingService(logger=my_logger)

# Register sessions as they connect
ping_service.register(session)

# Start background heartbeat
async with anyio.create_task_group() as tg:
    ping_service.start_heartbeat(
        tg,
        interval=30.0,
        jitter=0.1,
        timeout=10.0,
        phi_threshold=3.0,
    )
    # ... run server ...
```

The heartbeat loop:
1. Sleeps for `interval ± jitter`.
2. Calls `ping_many()` on all registered sessions.
3. Computes φ for each session.
4. Logs `ping-healthy`, `ping-suspect`, or `ping-down` events.
5. Invokes `on_suspect` / `on_down` callbacks.
6. Discards sessions that exceed `failure_budget`.

### Manual Pinging

For fine-grained control, invoke `ping()` or `ping_many()` directly:

```python
# Ping a single session
ok = await ping_service.ping(session, timeout=5.0)

# Ping multiple sessions in parallel
results = await ping_service.ping_many(
    sessions=[session_a, session_b],
    timeout=10.0,
    max_concurrency=4,  # Limit concurrent probes
)
# results: {session_a: True, session_b: False}
```

---

## Callbacks

Install custom failure handlers via constructor arguments:

```python
def on_suspect(session: ServerSession, phi: float) -> None:
    print(f"Session {session.id} is suspect (φ={phi:.2f})")
    # Emit alert, log to external service, etc.

def on_down(session: ServerSession) -> None:
    print(f"Session {session.id} is down")
    # Clean up resources, notify operators, etc.

ping_service = PingService(on_suspect=on_suspect, on_down=on_down)
```

Callbacks run synchronously during the heartbeat loop. Keep them lightweight or dispatch to a background queue.

---

## Metrics API

Query session health at runtime:

```python
# Current suspicion score
phi = ping_service.suspicion(session)

# EWMA round-trip time (seconds)
rtt = ping_service.round_trip_time(session)

# Alive check
alive = ping_service.is_alive(session, phi_threshold=4.0)

# Registered sessions
sessions = ping_service.active()
```

Use these for dashboards, health checks, or adaptive load balancing.

---

## Tuning Guide

### Default Values (Production-Ready)

```python
interval=30.0       # Ping every 30s
jitter=0.1          # ±10% randomization
timeout=10.0        # 10s per-ping timeout
phi_threshold=3.0   # 99.9% confidence
failure_budget=3    # 3 consecutive failures
history_size=32     # 32-interval rolling window
ewma_alpha=0.2      # 20% weight on latest RTT
```

These defaults balance responsiveness (detect failures within ~90s) with tolerance for transient delays.

### When to Tune

| Scenario | Adjustment | Rationale |
|----------|------------|-----------|
| Low-latency LAN | `phi_threshold=2.0` | Faster eviction for consistently fast network |
| High-latency WAN | `phi_threshold=5.0` | Tolerate variance in intercontinental paths |
| Aggressive eviction | `failure_budget=1` | Declare down after single failure |
| Slow-start connections | `history_size=64` | Longer learning period for new sessions |
| Frequent jitter | `jitter=0.3` | Wider spread to desynchronize probes |
| Memory-constrained | `history_size=16` | Smaller rolling window per session |

### φ Interpretation

| φ Value | Interpretation |
|---------|----------------|
| < 1.0 | Healthy (90% confidence) |
| 1.0–2.0 | Slightly delayed (90%–99%) |
| 2.0–3.0 | Moderately suspect (99%–99.9%) |
| > 3.0 | Highly suspect (>99.9%) |
| > 5.0 | Effectively down (>99.999%) |

In practice, `phi_threshold=3.0` means "raise suspicion when there's less than 0.1% chance the next ping arrives on time."

---

## Examples

### Example 1: Basic Heartbeat

```python
import anyio
from openmcp import MCPServer
from openmcp.server.services.ping import PingService

server = MCPServer("demo")
ping_service = PingService(logger=server.logger)

async def main():
    async with anyio.create_task_group() as tg:
        # Start heartbeat before accepting connections
        ping_service.start_heartbeat(
            tg,
            interval=30.0,
            jitter=0.1,
            timeout=10.0,
            phi_threshold=3.0,
        )

        # Run server (registers sessions via ping_service.register)
        await server.run()

anyio.run(main)
```

### Example 2: Custom Failure Callbacks

```python
from logging import getLogger

logger = getLogger(__name__)

def alert_ops(session: ServerSession, phi: float) -> None:
    logger.warning(f"Session {session.id} suspect: φ={phi:.2f}")
    # Send PagerDuty alert, emit Prometheus metric, etc.

def cleanup_session(session: ServerSession) -> None:
    logger.error(f"Session {session.id} declared down, cleaning up")
    # Close database connections, cancel background tasks, etc.

ping_service = PingService(
    logger=logger,
    on_suspect=alert_ops,
    on_down=cleanup_session,
)
```

### Example 3: Manual Probing with Metrics

```python
async def health_check():
    for session in ping_service.active():
        phi = ping_service.suspicion(session)
        rtt = ping_service.round_trip_time(session)
        alive = ping_service.is_alive(session)

        print(f"Session {session.id}: φ={phi:.2f}, RTT={rtt*1000:.1f}ms, alive={alive}")

        if phi > 2.0:
            # Manually probe suspicious session
            ok = await ping_service.ping(session, timeout=5.0)
            if not ok:
                print(f"Manual ping failed for {session.id}")
```

### Example 4: Jittered Multi-Session Probe

```python
async def probe_all():
    # Ping all active sessions with concurrency limit
    results = await ping_service.ping_many(
        timeout=10.0,
        max_concurrency=8,  # At most 8 concurrent pings
    )

    for session, ok in results.items():
        if ok:
            rtt = ping_service.round_trip_time(session)
            print(f"{session.id}: OK (RTT={rtt*1000:.1f}ms)")
        else:
            phi = ping_service.suspicion(session)
            print(f"{session.id}: FAIL (φ={phi:.2f})")
```

---

## Advanced: Adaptive Thresholds

For dynamic environments, compute φ thresholds based on observed variance:

```python
def adaptive_phi(session: ServerSession) -> float:
    state = ping_service._state(session)
    if len(state.intervals) < 10:
        return 5.0  # Conservative during learning phase

    mean = sum(state.intervals) / len(state.intervals)
    variance = sum((x - mean)**2 for x in state.intervals) / len(state.intervals)
    stddev = variance ** 0.5

    # Lower threshold for low-variance sessions
    return 2.0 if stddev < mean * 0.1 else 4.0

# Use in custom health checks
alive = ping_service.suspicion(session) < adaptive_phi(session)
```

This pattern lowers the threshold for stable connections (fast eviction) while tolerating variance for unstable ones.

---

## Integration Notes

- **Session lifecycle**: Call `ping_service.register(session)` when a session connects and `ping_service.discard(session)` on graceful shutdown. The heartbeat loop automatically discards sessions that exceed `failure_budget`.
- **Touch API**: For protocols that use out-of-band activity (e.g., receiving a notification), call `ping_service.touch(session)` to reset the suspicion clock without sending a ping.
- **Weak references**: `PingService` uses `weakref.WeakSet` and `weakref.WeakKeyDictionary` for session tracking, so garbage-collected sessions clean themselves up.
- **Thread safety**: All methods are async-safe via `anyio`. Concurrent `ping_many()` calls are serialized per-session but parallelized across sessions.

---

## See Also

- **Specification**: `https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping`
- **Reference Implementation**: `src/openmcp/server/services/ping.py` (phi-accrual at lines 236-278)
- **Lifecycle**: `docs/mcp/core/lifecycle/lifecycle-phases.md` (session initialization hooks)
- **Cancellation**: `docs/openmcp/cancellation.md` (handling ping timeouts gracefully)
- **Notifications**: `docs/openmcp/notifications.md` (emitting structured ping events)

---

**DRAFT NOTICE**: This document describes OpenMCP's ping implementation as of 2025-01-XX. The API surface is production-ready but may evolve before the 1.0 release. Consult the reference implementation at `src/openmcp/server/services/ping.py` for authoritative behavior.
