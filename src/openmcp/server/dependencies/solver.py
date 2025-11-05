# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Minimal dependency resolver used by the OpenMCP server."""

from __future__ import annotations

from typing import Any, Callable, Dict, Set

from ...context import get_context
from .models import CircularDependencyError, DependencyCall, DependencyResolutionError, ResolvedDependency
from ...utils import maybe_await_with_args
from . import Depends


def _get_callable_name(call: DependencyCall) -> str:
    """Extract a human-readable name from a DependencyCall for error messages."""
    fn = call.callable
    if hasattr(fn, "__name__"):
        return fn.__name__
    if hasattr(fn, "__class__"):
        return fn.__class__.__name__
    return repr(fn)




async def _resolve_dependency(
    call: DependencyCall,
    cache: Dict[DependencyCall, ResolvedDependency] | None = None,
    seen: Set[int] | None = None,
) -> Any:
    cache = cache if cache is not None else {}
    seen = seen if seen is not None else set()

    # Cycle detection
    call_id = id(call)
    if call_id in seen:
        name = _get_callable_name(call)
        raise CircularDependencyError(
            f"Circular dependency detected: {name} depends on itself (directly or indirectly)"
        )

    # Check cache before adding to seen set
    if call.use_cache and call in cache:
        return cache[call].value

    # Mark as being resolved
    seen.add(call_id)

    try:
        # Resolve subdependencies
        resolved_args = []
        for subcall in call.dependencies:
            resolved_args.append(await _resolve_dependency(subcall, cache=cache, seen=seen))

        # Build kwargs for auto-injected parameters
        injectable_kwargs = {}
        if call.context_param_name:
            injectable_kwargs[call.context_param_name] = get_context()

        # Call the dependency with resolved args and injectable kwargs
        try:
            value = await maybe_await_with_args(call.callable, *resolved_args, **injectable_kwargs)
        except Exception as e:
            name = _get_callable_name(call)
            raise DependencyResolutionError(
                f"Failed to resolve dependency '{name}': {e}"
            ) from e

        if call.use_cache:
            cache[call] = ResolvedDependency(value)
        return value
    finally:
        # Remove from seen set after resolution (allows reuse in sibling branches)
        seen.discard(call_id)


async def resolve(
    dependency: Callable[..., Any] | Depends | DependencyCall,
) -> Any:
    """Resolve *dependency* inside the active request scope."""

    if isinstance(dependency, Depends):
        call = dependency.as_call()
    elif isinstance(dependency, DependencyCall):
        call = dependency
    else:
        call = DependencyCall(dependency)

    cache = None
    try:
        ctx = get_context()
    except LookupError:
        ctx = None

    if ctx is not None:
        cache = ctx.dependency_cache
        if cache is None:
            cache = ctx.dependency_cache = {}

    return await _resolve_dependency(call, cache=cache)
