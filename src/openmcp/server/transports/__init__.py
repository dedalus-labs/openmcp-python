# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Transport adapters for OpenMCP servers.

These thin wrappers isolate the reference SDK's transport primitives so that
applications can swap or extend them without touching the core server class.
"""

from __future__ import annotations

from ._asgi import ASGIRunConfig, ASGITransportConfig
from .base import BaseTransport, TransportFactory
from .stdio import StdioTransport
from .streamable_http import StreamableHTTPTransport

__all__ = [
    "ASGIRunConfig",
    "ASGITransportConfig",
    "BaseTransport",
    "StdioTransport",
    "StreamableHTTPTransport",
    "TransportFactory",
]
