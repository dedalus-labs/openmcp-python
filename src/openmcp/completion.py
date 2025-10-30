# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

# Copyright (c) Dedalus Labs, Inc. and affiliates.

"""Completion registration utilities.

Implements the ambient registration UX described in
``docs/mcp/capabilities/completion/index.md``.  Registered callables are used to
answer ``completion/complete`` requests as specified in
``docs/mcp/spec/schema-reference/completion-complete.md``.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable

    from . import types
    from .server import MCPServer

    if types:  # pragma: no cover - import guard for static analysers
        types.Completion  # noqa: B018


class CompletionFunction(Protocol):
    """Callable signature for completion providers.

    Providers accept the argument being completed and optional prior context,
    mirroring ``CompletionRequestParams`` in the spec.
    """

    def __call__(
        self, argument: types.CompletionArgument, context: types.CompletionContext | None
    ) -> (
        types.Completion
        | CompletionResult
        | Iterable[str]
        | None
        | Awaitable[types.Completion | CompletionResult | Iterable[str] | None]
    ): ...


@dataclass(slots=True)
class CompletionResult:
    """Lightweight completion payload.

    Maps directly to ``Completion`` from the spec while allowing optional
    ``total`` and ``hasMore`` fields.
    """

    values: Iterable[str]
    total: int | None = None
    has_more: bool | None = None


@dataclass(slots=True)
class CompletionSpec:
    """Registered completion provider.

    Attributes correspond to the reference tables in
    ``docs/mcp/capabilities/completion/protocol-messages.md``.
    """

    ref_type: str  # ``"prompt"`` or ``"resource"``
    key: str  # prompt name or resource template URI
    fn: CompletionFunction


_COMPLETION_ATTR = "__openmcp_completion__"
_ACTIVE_SERVER: ContextVar[MCPServer | None] = ContextVar("_openmcp_completion_server", default=None)


def get_active_server() -> MCPServer | None:
    return _ACTIVE_SERVER.get()


def set_active_server(server: MCPServer) -> object:
    return _ACTIVE_SERVER.set(server)


def reset_active_server(token: object) -> None:
    _ACTIVE_SERVER.reset(token)


def completion(
    *, prompt: str | None = None, resource: str | None = None
) -> Callable[[CompletionFunction], CompletionFunction]:
    """Register a completion provider.

    Exactly one of ``prompt`` or ``resource`` must be supplied.  This mirrors
    the ``PromptReference`` and ``ResourceTemplateReference`` types in the
    completion spec.
    """
    if (prompt is None) == (resource is None):  # pragma: no cover - defensive
        raise ValueError("Provide exactly one of 'prompt' or 'resource'.")

    ref_type = "prompt" if prompt is not None else "resource"
    key = prompt or resource  # type: ignore[arg-type]

    def decorator(fn: CompletionFunction) -> CompletionFunction:
        spec = CompletionSpec(ref_type=ref_type, key=key, fn=fn)
        setattr(fn, _COMPLETION_ATTR, spec)

        server = get_active_server()
        if server is not None:
            server.register_completion(spec)

        return fn

    return decorator


def extract_completion_spec(fn: CompletionFunction) -> CompletionSpec | None:
    spec = getattr(fn, _COMPLETION_ATTR, None)
    if isinstance(spec, CompletionSpec):
        return spec
    return None


__all__ = [
    "completion",
    "CompletionSpec",
    "CompletionResult",
    "extract_completion_spec",
    "set_active_server",
    "reset_active_server",
]
