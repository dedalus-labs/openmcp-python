# Performance Optimizations

OpenMCP is designed to be fast out of the box while keeping the core minimal. Advanced performance features are available as optional extras.

## Default Optimizations

These are always enabled:

- **Bytecode compilation** - 10-20% faster startup via `uv compile-bytecode`
- **Hardlink caching** - Fastest dependency resolution (macOS/Linux)
- **Minimal dependencies** - Only Pydantic and MCP SDK in core

## Optional Performance Extras

Install performance optimizations:

```bash
uv add "openmcp[opt]"
```

This adds:

### uvloop (2-4x faster event loop)

Drop-in replacement for asyncio's event loop, implemented in Cython. Provides:
- 2-4x faster async I/O operations
- Lower latency for network calls
- Better throughput for concurrent tasks
- Unix/Linux only (automatically skipped on Windows)

**Auto-detected**: OpenMCP automatically uses uvloop when installed. Check logs:

```python
import os
os.environ["OPENMCP_LOG_LEVEL"] = "DEBUG"

from openmcp import MCPServer

server = MCPServer("my-server")
# Logs: "Event loop: uvloop" or "Event loop: asyncio"
```

**No code changes needed** - just install the extra and it's active.

### orjson (Faster JSON)

Rust-based JSON serialization, ~2x faster than stdlib `json`:

```python
from openmcp.utils.logger import setup_logger

# Use orjson for structured logging
import orjson

setup_logger(
    use_json=True,
    json_serializer=lambda p: orjson.dumps(p).decode()
)
```

## Benchmarks

Performance gains with `openmcp[opt]` on typical workloads:

| Scenario | Default | With uvloop | Speedup |
|----------|---------|-------------|---------|
| Tool invocation (sync) | ~0.5ms | ~0.5ms | None* |
| Tool invocation (async I/O) | ~10ms | ~3-4ms | 2-3x |
| Concurrent requests (100) | ~150ms | ~50ms | 3x |
| JSON logging (1000 msgs) | ~80ms | ~40ms** | 2x |

\* Sync functions have no event loop overhead
\*\* With orjson serializer

## When to Use Performance Extras

**Use `openmcp[opt]` when:**
- Production deployment with high request volume
- Latency-sensitive applications (<10ms target)
- Async-heavy workloads (network, database, file I/O)
- Running on Unix/Linux servers

**Skip `openmcp[opt]` when:**
- Development/prototyping
- Windows deployment (uvloop unavailable)
- Minimal dependencies required
- CPU-bound workloads (sync tools)

## Philosophy

Following OpenMCP's "dependency discipline" (CLAUDE.md):

> Every new dependency must justify its byte cost.

Performance optimizations are **optional extras** rather than core dependencies. This keeps:
- Minimal installation size (~2MB vs ~4MB)
- Fast installation time
- Broad compatibility (Windows, embedded systems)
- Zero mandatory compiled dependencies

Production users opt-in explicitly when performance matters.

## See Also

- [uvloop documentation](https://github.com/MagicStack/uvloop)
- [orjson documentation](https://github.com/ijl/orjson)
- `examples/advanced/custom_logging.py` - orjson integration example
