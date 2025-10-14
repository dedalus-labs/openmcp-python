"""Transport adapters for OpenMCP servers.

These thin wrappers isolate the reference SDK's transport primitives so that
applications can swap or extend them without touching the core server class.
"""

from __future__ import annotations

from .base import BaseTransport, TransportFactory
from .stdio import StdioTransport
from .streamable_http import StreamableHTTPTransport

__all__ = [
    "BaseTransport",
    "TransportFactory",
    "StdioTransport",
    "StreamableHTTPTransport",
]
