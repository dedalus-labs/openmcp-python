# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Prompt registration utilities.

Implements the prompts capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
  (prompts capability, list and get operations, argument handling)

Supports the ambient authoring pattern where decorated callables are registered
as prompt templates with the MCP server.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from . import types


if types:  # pragma: no cover - import guard for static analysis
    types.GetPromptResult  # noqa: B018

if TYPE_CHECKING:  # pragma: no cover
    from .server import MCPServer


class PromptFunction(Protocol):
    """Callable signature for prompt renderers."""

    def __call__(
        self, arguments: Mapping[str, str] | None
    ) -> types.GetPromptResult | Iterable[Any] | Mapping[str, Any] | None: ...


PromptArgumentLike = Mapping[str, Any] | types.PromptArgument
IconLike = Mapping[str, Any] | types.Icon


@dataclass(slots=True)
class PromptSpec:
    """Metadata describing a registered prompt."""

    name: str
    fn: PromptFunction
    description: str | None = None
    title: str | None = None
    arguments: list[types.PromptArgument] | None = None
    icons: list[types.Icon] | None = None
    meta: Mapping[str, Any] | None = None


_PROMPT_ATTR = "__openmcp_prompt__"
_ACTIVE_SERVER: ContextVar[MCPServer | None] = ContextVar("_openmcp_prompt_server", default=None)


def get_active_server() -> MCPServer | None:
    return _ACTIVE_SERVER.get()


def set_active_server(server: MCPServer) -> object:
    return _ACTIVE_SERVER.set(server)


def reset_active_server(token: object) -> None:
    _ACTIVE_SERVER.reset(token)


def prompt(
    name: str,
    *,
    description: str | None = None,
    title: str | None = None,
    arguments: Iterable[PromptArgumentLike] | None = None,
    icons: Iterable[IconLike] | None = None,
    meta: Mapping[str, Any] | None = None,
) -> Callable[[PromptFunction], PromptFunction]:
    """Register a prompt renderer.

    See: https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
    """

    def decorator(fn: PromptFunction) -> PromptFunction:
        spec = PromptSpec(
            name=name,
            fn=fn,
            description=description,
            title=title,
            arguments=[_coerce_argument(arg) for arg in (arguments or [])] or None,
            icons=[_coerce_icon(icon) for icon in (icons or [])] or None,
            meta=meta,
        )
        setattr(fn, _PROMPT_ATTR, spec)

        server = get_active_server()
        if server is not None:
            server.register_prompt(spec)

        return fn

    return decorator


def extract_prompt_spec(fn: PromptFunction) -> PromptSpec | None:
    spec = getattr(fn, _PROMPT_ATTR, None)
    if isinstance(spec, PromptSpec):
        return spec
    return None


def _coerce_argument(value: PromptArgumentLike) -> types.PromptArgument:
    if isinstance(value, types.PromptArgument):
        return value
    if not isinstance(value, Mapping):  # pragma: no cover - defensive
        raise TypeError("Prompt argument must be mapping or PromptArgument")
    return types.PromptArgument(**value)


def _coerce_icon(value: IconLike) -> types.Icon:
    if isinstance(value, types.Icon):
        return value
    if not isinstance(value, Mapping):  # pragma: no cover - defensive
        raise TypeError("Icon must be mapping or Icon instance")
    return types.Icon(**value)


__all__ = ["prompt", "PromptSpec", "extract_prompt_spec", "set_active_server", "reset_active_server"]
