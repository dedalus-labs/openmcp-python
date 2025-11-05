# Performance Quick Start

## Installation

```bash
# Default (minimal)
uv add openmcp

# With performance optimizations (recommended for production)
uv add "openmcp[opt]"
```

## What You Get

Installing `openmcp[opt]` adds:

1. **uvloop** - 2-4x faster event loop (Unix/Linux only)
2. **orjson** - 2x faster JSON serialization (optional, for logging)

## Verification

Check if uvloop is active:

```bash
export OPENMCP_LOG_LEVEL=DEBUG
python your_server.py
```

Look for: `Event loop: uvloop` or `Event loop: asyncio`

## Zero Code Changes

uvloop is automatically installed and activated when available. Your code stays the same:

```python
from openmcp import MCPServer, tool

server = MCPServer("my-server")

@tool()
async def my_tool() -> str:
    return "works with both asyncio and uvloop"

# Same code, faster execution with openmcp[opt]
```

## Performance Impact

Expect 2-4x speedup on async-heavy workloads (network, database, file I/O). Sync tools see no difference.

See `docs/openmcp/performance.md` for detailed benchmarks and usage patterns.
