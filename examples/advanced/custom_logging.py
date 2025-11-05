"""Demonstrate custom logging configuration for OpenMCP.

This example keeps the framework dependency-light while showing how an
application can opt into structured JSON logging using ``orjson`` and
structured payloads built with Pydantic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, ClassVar, cast

from pydantic import BaseModel

from openmcp import MCPServer, tool
from openmcp.utils.logger import ColoredFormatter, OpenMCPHandler, get_logger, setup_logger


try:
    import orjson  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - optional dependency
    orjson = None


class LogEvent(BaseModel):
    stage: str
    message: str
    severity: str


def _serialize(payload: dict[str, Any]) -> str:
    """Serialize payload using fastest available encoder."""
    if orjson is not None:
        encoded = orjson.dumps(payload, option=orjson.OPT_APPEND_NEWLINE)
        return cast("bytes", encoded).decode()

    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


setup_logger(
    use_json=True,
    json_serializer=_serialize,
    payload_transformer=lambda payload: {
        **payload,
        "context": LogEvent(**payload.get("context", {})).model_dump() if payload.get("context") else None,
    },
    force=True,
)

log = get_logger(__name__)
server = MCPServer("custom-logging")


@tool()
async def echo(message: str) -> str:
    event = LogEvent(stage="echo", message=message, severity="info")
    log.info("tool-invoked", **event.model_dump())
    return message


# ==============================================================================
# Additional Examples: Color Customization and Handler Extension
# ==============================================================================

def example_custom_colors() -> None:
    """Override colors by subclassing ColoredFormatter (pastel scheme)."""
    class CustomColors(ColoredFormatter):
        """Pastel color scheme."""
        LEVEL_COLORS: ClassVar[dict[str, str]] = {
            "DEBUG": "\033[38;5;117m",   # Light blue
            "INFO": "\033[38;5;156m",    # Light green
            "WARNING": "\033[38;5;222m", # Light orange
            "ERROR": "\033[38;5;210m",   # Light red
            "CRITICAL": "\033[38;5;201m",# Bright pink
        }

    setup_logger(level=logging.DEBUG, force=True)
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(CustomColors(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))

    logger = get_logger("example.custom")
    logger.debug("Debug: Pastel light blue")
    logger.info("Info: Pastel light green")
    logger.warning("Warning: Pastel orange")
    logger.error("Error: Pastel light red")
    logger.critical("Critical: Bright pink")


def example_custom_handler() -> None:
    """Subclass OpenMCPHandler to add filtering logic."""
    class FilteredHandler(OpenMCPHandler):
        """Handler that filters out debug messages from specific modules."""

        def emit(self, record: logging.LogRecord) -> None:
            if record.levelno == logging.DEBUG and "noisy" in record.name:
                return
            super().emit(record)

    handler = FilteredHandler()
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(ColoredFormatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.handlers.clear()
    root.addHandler(handler)

    logger = get_logger("example.filtered")
    noisy_logger = get_logger("example.noisy")

    logger.debug("This will show")
    noisy_logger.debug("This is filtered out")
    logger.info("Info messages always show")


async def main() -> None:
    """Run MCP server with custom JSON logging."""
    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve_stdio(validate=False))


def example_default_colors() -> None:
    """Show our default color scheme."""
    setup_logger(level=logging.DEBUG, force=True)
    logger = get_logger("default")
    logger.debug("Debug: Cyan")
    logger.info("Info: Green")
    logger.warning("Warning: Yellow")
    logger.error("Error: Red")
    logger.critical("Critical: Magenta")


def example_python_colors() -> None:
    """Python 3.13+ style: bright red/magenta for errors."""
    class PythonColors(ColoredFormatter):
        """Python-style bright colors for errors."""
        LEVEL_COLORS: ClassVar[dict[str, str]] = {
            "DEBUG": "\033[36m",      # Cyan (normal)
            "INFO": "\033[32m",       # Green (normal)
            "WARNING": "\033[33m",    # Yellow (normal)
            "ERROR": "\033[1;31m",    # Bold bright red (like Python exceptions)
            "CRITICAL": "\033[1;35m", # Bold bright magenta (like Python error spans)
        }

    setup_logger(level=logging.DEBUG, force=True)
    root = logging.getLogger()
    for handler in root.handlers:
        handler.setFormatter(PythonColors(
            fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))

    logger = get_logger("python-style")
    logger.debug("Debug: Cyan")
    logger.info("Info: Green")
    logger.warning("Warning: Yellow")
    logger.error("Error: BOLD BRIGHT RED (Python exception style)")
    logger.critical("Critical: BOLD BRIGHT MAGENTA (Python error span style)")


if __name__ == "__main__":
    import sys

    if "--examples" in sys.argv or "--demo" in sys.argv:
        # Run standalone examples (no server)
        print("\n=== Our Default Colors ===")
        example_default_colors()

        print("\n=== Python 3.13+ Style (Bright Errors) ===")
        example_python_colors()

        print("\n=== Custom Pastel Colors ===")
        example_custom_colors()

        print("\n=== Custom Handler (Filtering) ===")
        example_custom_handler()
    else:
        # Run as MCP server (use with MCP client)
        asyncio.run(main())
