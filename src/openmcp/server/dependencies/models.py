# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Internal models used by the dependency resolver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Sequence


class DependencyResolutionError(Exception):
    """Raised when a dependency cannot be resolved."""
    pass


class CircularDependencyError(DependencyResolutionError):
    """Raised when circular dependencies are detected."""
    pass


@dataclass(frozen=True)
class DependencyCall:
    """Represents a dependency callable and its nested dependencies.

    The context_param_name field stores the parameter name for auto-injecting
    the Context object at resolution time.
    """

    callable: Callable[..., Any]
    dependencies: Sequence[DependencyCall] = field(default_factory=tuple)
    use_cache: bool = True
    context_param_name: str | None = None


@dataclass
class ResolvedDependency:
    """Holds the cached value of a dependency for the current scope."""

    value: Any


CacheKey = tuple[int, ...]

