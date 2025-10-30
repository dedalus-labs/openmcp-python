# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""OpenMCP framework primitives."""

from __future__ import annotations

from ._sdk_loader import ensure_sdk_importable


ensure_sdk_importable()

from . import types
from .client import MCPClient
from .completion import CompletionResult, completion
from .context import Context, get_context
from .progress import progress
from .prompt import prompt
from .resource import resource
from .resource_template import resource_template
from .server import MCPServer, NotificationFlags
from .server.authorization import AuthorizationConfig
from .tool import tool


__all__ = [
    "NotificationFlags",
    "MCPClient",
    "MCPServer",
    "tool",
    "resource",
    "completion",
    "CompletionResult",
    "prompt",
    "resource_template",
    "progress",
    "types",
    "Context",
    "get_context",
    "AuthorizationConfig",
]
