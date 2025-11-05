# Logging

**Problem**: MCP exposes a `logging/setLevel` request so clients can tune verbosity at runtime. Wiring this manually requires JSON-RPC plumbing and consistent logger configuration across transports.

**Design Principle**: Keep the framework lean. OpenMCP should never force third-party logging stacks (Rich, structlog, etc.) on host applications. Instead we provide stdlib defaults and clear hooks so projects can bring their own structured logging if they want.

**Solution**: Ship a minimal logging helper built on `logging` + MCP notifications and let applications layer richer tooling when needed. The logging service handles the MCP contract while `openmcp.utils.logger.setup_logger()` offers a single entry point for baseline configuration.

**OpenMCP**: `MCPServer` bundles a default `logging/setLevel` handler that maps MCP levels (`debug` → `emergency`) onto Python’s logging levels, updating both the root logger and the scoped logger returned by `openmcp.utils.get_logger`. The logging service also installs a lightweight handler that mirrors Python log records to `notifications/message` so any configured client receives log events, satisfying both [`logging/setLevel`](https://modelcontextprotocol.io/specification/2025-06-18/schema-reference/logging-setLevel) and [`notifications/message`](https://modelcontextprotocol.io/specification/2025-06-18/schema-reference/notifications-message) in the public spec.

```python
from openmcp import MCPServer
from openmcp.utils.logger import get_logger, setup_logger

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

- Spec receipts: [`server/utilities/logging`](https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/logging)
- Default behaviour relies solely on the Python standard library. Set `OPENMCP_LOG_LEVEL` or call `setup_logger(level="DEBUG")` to adjust verbosity.

## Minimalist by Default, Extensible by Design

`setup_logger()` sets up a single `StreamHandler` with a plain formatter. This keeps runtime dependencies at zero. If your project already configures logging, you can ignore the helper entirely and OpenMCP will respect your existing handlers.

Applications that want structured output can opt into JSON mode and supply their own serializer. The helper accepts any callable that turns a payload dict into a string, so you can wire `orjson`, `ujson`, etc., without OpenMCP bundling them:

```python
import json
from openmcp.utils.logger import setup_logger

try:
    import orjson
except ImportError:  # optional acceleration
    orjson = None


def serialize(payload: dict) -> str:
    if orjson is not None:
        return orjson.dumps(payload).decode()
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


setup_logger(
    use_json=True,
    json_serializer=serialize,
    payload_transformer=lambda payload: {
        **payload,
        "context": payload.get("context"),
    },
    force=True,  # rebuild handlers if setup_logger ran earlier
)
```

See `examples/advanced/custom_logging.py` for a runnable script that optionally wires the helper to `orjson` (falling back to `json` when unavailable), builds structured payloads with Pydantic, and emits MCP notifications.

If you need more control, build your own handler and still enjoy MCP notifications:

```python
import logging
from openmcp import MCPServer

server = MCPServer("custom-logging")

logging.basicConfig(
    level=logging.INFO,
    handlers=[logging.FileHandler("server.log")],
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# server.logging_service continues to mirror records to notifications/message.
```

## Takeaways

- OpenMCP stays dependency-light; you choose if/when to add richer logging stacks.
- MCP logging notifications continue to function regardless of how you configure Python’s logging module.
- `StructuredJSONFormatter` is exported for convenience if you want to reuse the minimal payload shape with a custom serializer.
