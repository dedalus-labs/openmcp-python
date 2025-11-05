# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Public dependency helpers for OpenMCP."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Sequence, get_origin

from .models import DependencyCall


def register_injectable_type(typ: type) -> None:
    """Register a type to be auto-injected in dependency resolution.

    Currently only Context is supported. This exists for future extensibility.
    """
    # For now, we only support Context, but this allows future types
    pass


def _find_context_param(func: Callable[..., Any]) -> str | None:
    """Inspect function signature to find a Context-typed parameter."""
    try:
        sig = inspect.signature(func)
    except (ValueError, TypeError):
        return None

    # Import here to avoid circular dependency
    from ...context import Context

    for param_name, param in sig.parameters.items():
        if param.annotation == inspect.Parameter.empty:
            continue

        # Handle generic aliases (e.g., Optional[Context])
        origin = get_origin(param.annotation)
        param_type = origin if origin is not None else param.annotation

        if param_type is Context:
            return param_name

    return None


class Depends:
    """Marks a callable as a dependency to be resolved by the framework.

    Supports both explicit subdependencies and automatic injection of
    registered types (like Context) based on type annotations.
    """

    __slots__ = ("call", "dependencies", "use_cache")

    def __init__(
        self,
        dependency: Callable[..., Any],
        *subdependencies: Callable[..., Any],
        use_cache: bool = True,
    ) -> None:
        if not callable(dependency):  # pragma: no cover - defensive guard
            raise TypeError("Depends() arguments must be callable")

        self.call: Callable[..., Any] = dependency
        self.dependencies: Sequence[Callable[..., Any]] = subdependencies
        self.use_cache: bool = use_cache

    def as_call(self) -> DependencyCall:
        nested = tuple(Depends(dep).as_call() if not isinstance(dep, Depends) else dep.as_call() for dep in self.dependencies)
        context_param_name = _find_context_param(self.call)
        return DependencyCall(self.call, nested, self.use_cache, context_param_name)


__all__ = ["Depends"]

