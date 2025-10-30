# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Pagination helpers for MCP list responses."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from mcp.shared.exceptions import McpError

from .. import types


T = TypeVar("T")


def paginate_sequence(items: Sequence[T], cursor: str | None, *, limit: int) -> tuple[list[T], str | None]:
    """Slice *items* according to *cursor* and *limit*.

    Raises :class:`McpError` if the cursor cannot be interpreted as an integer,
    matching the ``INVALID_PARAMS`` contract described in the pagination spec.
    """
    start = 0
    if cursor:
        try:
            start = max(0, int(cursor))
        except ValueError as exc:  # pragma: no cover - defensive
            raise McpError(types.ErrorData(code=types.INVALID_PARAMS, message="Invalid cursor provided")) from exc

    end = start + limit
    page = list(items[start:end])
    next_cursor = str(end) if end < len(items) else None
    return page, next_cursor
