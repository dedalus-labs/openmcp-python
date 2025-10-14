# Logging

**Problem**: MCP exposes a `logging/setLevel` request so clients can tune verbosity at runtime. Wiring this manually requires JSON-RPC plumbing and consistent logger configuration across transports.

**Solution**: Provide a reusable logging setup that defaults to structured, colorized output and implement the `logging/setLevel` handler so clients can switch levels without restarting the server.

**OpenMCP**: `MCPServer` bundles a default `logging/setLevel` handler that maps MCP levels (`debug` → `emergency`) onto Python’s logging levels, updating both the root logger and the scoped logger returned by `openmcp.utils.get_logger`. The logging service also installs a lightweight handler that mirrors Python log records to `notifications/message` so any configured client receives structured log events, satisfying both `docs/mcp/spec/schema-reference/logging-setlevel.md` and `docs/mcp/spec/schema-reference/notifications-message.md`.

```python
from openmcp import MCPServer
from openmcp.utils import get_logger

server = MCPServer("logging-demo")
log = get_logger("demo")

async def do_work():
    log.info("Hello from the server")           # mirrored to notifications/message
    await server.log_message(
        "warning",
        {"stage": "encoder", "message": "CPU spike detected"},
        logger="demo",
    )

# Optional override if you need extra side effects when clients call setLevel.
# The default implementation already updates the root + scoped logger levels
# and records the requesting session’s threshold.
#
# @server.set_logging_level()
# async def adjust(level: str) -> None:
#     log.info("Client tightened log level to %s", level)
```

- Spec receipts: `docs/mcp/spec/schema-reference/logging-setlevel.md`, `docs/mcp/capabilities/logging`
- Color scheme mirrors `api-final/src/common/logger.py`; override via `OPENMCP_LOG_LEVEL` or your own `logging` config if desired.
