# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Utility helpers for OpenMCP."""

from __future__ import annotations

from .coro import maybe_await, maybe_await_with_args, noop_coroutine
from .logger import get_logger, setup_logger


__all__ = [
    "setup_logger",
    "get_logger",
    "noop_coroutine",
    "maybe_await",
    "maybe_await_with_args",
]
