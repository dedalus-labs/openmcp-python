# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for coroutine utility functions.

Exercises the maybe_await and maybe_await_with_args utilities from
utils/coro.py to ensure correct handling of sync/async callables and
already-evaluated values.
"""

from __future__ import annotations

import asyncio

import pytest

from openmcp.utils import maybe_await, maybe_await_with_args


@pytest.mark.asyncio
async def test_maybe_await_with_sync_callable() -> None:
    """maybe_await evaluates sync callables correctly."""
    def sync_fn() -> int:
        return 42

    result = await maybe_await(sync_fn)
    assert result == 42


@pytest.mark.asyncio
async def test_maybe_await_with_async_callable() -> None:
    """maybe_await evaluates async callables correctly."""
    async def async_fn() -> int:
        await asyncio.sleep(0)
        return 42

    result = await maybe_await(async_fn)
    assert result == 42


@pytest.mark.asyncio
async def test_maybe_await_with_direct_value() -> None:
    """maybe_await handles direct values correctly."""
    result = await maybe_await(42)
    assert result == 42


@pytest.mark.asyncio
async def test_maybe_await_with_coroutine() -> None:
    """maybe_await handles coroutines correctly."""
    async def async_fn() -> int:
        await asyncio.sleep(0)
        return 42

    coro = async_fn()
    result = await maybe_await(coro)
    assert result == 42


@pytest.mark.asyncio
async def test_maybe_await_with_args_sync_callable() -> None:
    """maybe_await_with_args evaluates sync callables with arguments."""
    def add(a: int, b: int) -> int:
        return a + b

    result = await maybe_await_with_args(add, 2, 3)
    assert result == 5


@pytest.mark.asyncio
async def test_maybe_await_with_args_async_callable() -> None:
    """maybe_await_with_args evaluates async callables with arguments."""
    async def add_async(a: int, b: int) -> int:
        await asyncio.sleep(0)
        return a + b

    result = await maybe_await_with_args(add_async, 4, 7)
    assert result == 11


@pytest.mark.asyncio
async def test_maybe_await_with_args_kwargs() -> None:
    """maybe_await_with_args handles keyword arguments."""
    def compute(a: int, b: int = 10) -> int:
        return a * b

    result = await maybe_await_with_args(compute, 3, b=5)
    assert result == 15


@pytest.mark.asyncio
async def test_maybe_await_with_args_async_kwargs() -> None:
    """maybe_await_with_args handles async with keyword arguments."""
    async def compute_async(a: int, b: int = 10) -> int:
        await asyncio.sleep(0)
        return a * b

    result = await maybe_await_with_args(compute_async, a=3, b=5)
    assert result == 15


@pytest.mark.asyncio
async def test_maybe_await_with_args_direct_value() -> None:
    """maybe_await_with_args handles direct values (ignores args)."""
    result = await maybe_await_with_args(42, "ignored", "args")
    assert result == 42


@pytest.mark.asyncio
async def test_maybe_await_with_args_coroutine() -> None:
    """maybe_await_with_args handles already-created coroutines."""
    async def async_fn(x: int) -> int:
        await asyncio.sleep(0)
        return x * 2

    coro = async_fn(5)
    result = await maybe_await_with_args(coro, "ignored")
    assert result == 10
