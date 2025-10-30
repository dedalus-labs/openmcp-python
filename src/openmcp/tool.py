# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tool registration utilities for OpenMCP.

This module implements the ambient registration pattern discussed in the
framework design notes.  When an :class:`~openmcp.server.MCPServer`
instance enters its :meth:`binding <openmcp.server.MCPServer.binding>`
context, decorated functions are automatically registered as MCP tools.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from . import types
from .utils.schema import resolve_input_schema, resolve_output_schema


if types:  # keep pydoc happy when mcp.types is unavailable during static checks
    types.Tool  # noqa: B018

from typing import TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover - type-checking helpers only
    from .server import MCPServer

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

ToolFn = Callable[..., Any]


@dataclass(slots=True)
class ToolSpec:
    """In-memory representation of a tool definition."""

    name: str
    fn: ToolFn
    description: str = ""
    tags: set[str] = field(default_factory=set)
    input_schema: dict[str, Any] | None = None
    enabled: Callable[[MCPServer], bool] | None = None
    title: str | None = None
    output_schema: dict[str, Any] | None = None
    annotations: dict[str, Any] | None = None
    icons: list[Any] | None = None


_TOOL_ATTR = "__openmcp_tool__"
_ACTIVE_SERVER: ContextVar[MCPServer | None] = ContextVar("_openmcp_active_server", default=None)


def get_active_server() -> MCPServer | None:
    """Return the server currently binding tool definitions, if any."""
    return _ACTIVE_SERVER.get()


def set_active_server(server: MCPServer) -> Any:
    """Activate a server for ambient registration (internal helper)."""
    return _ACTIVE_SERVER.set(server)


def reset_active_server(token: Any) -> None:
    """Reset the active server context (internal helper)."""
    _ACTIVE_SERVER.reset(token)


def _coerce_tags(tags: Iterable[str] | None) -> set[str]:
    if not tags:
        return set()
    result = {str(tag).strip() for tag in tags if str(tag).strip()}
    return result


def tool(
    name: str | None = None,
    *,
    description: str | None = None,
    tags: Iterable[str] | None = None,
    input_schema: dict[str, Any] | None = None,
    enabled: Callable[[MCPServer], bool] | None = None,
    title: str | None = None,
    output_schema: dict[str, Any] | None = None,
    annotations: dict[str, Any] | None = None,
    icons: Iterable[Any] | None = None,
) -> Callable[[ToolFn], ToolFn]:
    """Decorator that marks a callable as an MCP tool.

    The decorator attaches a :class:`ToolSpec` to the function and, if a server
    is actively binding, registers it immediately.
    """

    def decorator(fn: ToolFn) -> ToolFn:
        desc = (description if description is not None else (fn.__doc__ or "")).strip()

        resolved_input_schema = None
        if input_schema is not None:
            resolved_input_schema = resolve_input_schema(input_schema)

        resolved_output_schema = None
        if output_schema is not None:
            resolved_output_schema = resolve_output_schema(output_schema).schema

        spec = ToolSpec(
            name=name or fn.__name__ or "anonymous",
            fn=fn,
            description=desc,
            tags=_coerce_tags(tags),
            input_schema=resolved_input_schema,
            enabled=enabled,
            title=title,
            output_schema=resolved_output_schema,
            annotations=annotations,
            icons=list(icons) if icons is not None else None,
        )
        setattr(fn, _TOOL_ATTR, spec)

        server = get_active_server()
        if server is not None:
            server.register_tool(spec)

        return fn

    return decorator


def extract_tool_spec(fn: ToolFn) -> ToolSpec | None:
    """Return the attached :class:`ToolSpec` for *fn*, if present."""
    spec = getattr(fn, _TOOL_ATTR, None)
    if spec is None:
        return None
    if not isinstance(spec, ToolSpec):
        return None
    return spec


__all__ = [
    "ToolSpec",
    "ToolFn",
    "tool",
    "extract_tool_spec",
    "get_active_server",
    "set_active_server",
    "reset_active_server",
]
