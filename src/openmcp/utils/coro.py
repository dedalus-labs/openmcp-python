"""Coroutine helpers shared across OpenMCP services.

These utilities collapse the "maybe await" pattern that appears throughout the
framework: callables may be synchronous, asynchronous, or already-evaluated
values.  Centralising the logic keeps capability services tidy and avoids
re-implementing the same inspect/await checks repeatedly.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar, overload

T = TypeVar("T")


async def noop_coroutine() -> None:
    """Return immediately; useful as a default awaitable."""


@overload
async def maybe_await(value: T) -> T:
    ...


@overload
async def maybe_await(value: Callable[[], T]) -> T:
    ...


async def maybe_await(value: T | Callable[[], T]) -> T:
    """Evaluate *value* and await the result if necessary."""

    if callable(value):
        value = value()
    if inspect.isawaitable(value):
        value = await value  # type: ignore[assignment]
    return value  # type: ignore[return-value]


@overload
async def maybe_await_with_args(value: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    ...


@overload
async def maybe_await_with_args(value: Awaitable[T] | T, /, *args: Any, **kwargs: Any) -> T:
    ...


async def maybe_await_with_args(
    value: Callable[..., T] | Awaitable[T] | T,
    /,
    *args: Any,
    **kwargs: Any,
) -> T:
    """Variant of :func:`maybe_await` that forwards ``*args`` / ``**kwargs``."""

    if callable(value):
        value = value(*args, **kwargs)
    if inspect.isawaitable(value):
        value = await value  # type: ignore[assignment]
    return value  # type: ignore[return-value]


__all__ = ["noop_coroutine", "maybe_await", "maybe_await_with_args"]
