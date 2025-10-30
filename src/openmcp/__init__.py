"""OpenMCP framework primitives."""

from __future__ import annotations

from ._sdk_loader import ensure_sdk_importable

ensure_sdk_importable()

from . import types
from .context import Context, get_context
from .client import MCPClient
from .server import NotificationFlags, MCPServer
from .server.authorization import AuthorizationConfig
from .tool import tool
from .resource import resource
from .completion import completion, CompletionResult
from .prompt import prompt
from .resource_template import resource_template
from .progress import progress

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
