# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Sampling capability adapter for MCP servers.

Implements the sampling capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/client/sampling
  (sampling capability, createMessage request for LLM interaction)

Provides adapter interface for servers to handle client LLM sampling requests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import anyio
from mcp.server.lowlevel.server import request_ctx
from mcp.shared.exceptions import McpError

from ... import types
from ...utils import get_logger


DEFAULT_TIMEOUT = 60.0
MAX_CONCURRENT = 4
FAILURE_THRESHOLD = 3
COOLDOWN_SECONDS = 30.0


@dataclass
class _SessionState:
    semaphore: asyncio.Semaphore
    consecutive_failures: int = 0
    cooldown_until: float = 0.0


class SamplingService:
    """Proxy for ``sampling/createMessage`` requests.

        See: https://modelcontextprotocol.io/specification/2025-06-18/client/sampling
    """

    def __init__(self, *, timeout: float = DEFAULT_TIMEOUT, max_concurrent: int = MAX_CONCURRENT) -> None:
        self._timeout = timeout
        self._max_concurrent = max(1, max_concurrent)
        self._states: dict[Any, _SessionState] = {}
        self._logger = get_logger("openmcp.sampling")

    async def create_message(self, params: types.CreateMessageRequestParams) -> types.CreateMessageResult:
        session = self._current_session()

        if not session.check_client_capability(types.ClientCapabilities(sampling=types.SamplingCapability())):
            raise McpError(
                types.ErrorData(
                    code=types.METHOD_NOT_FOUND, message="Client does not advertise the sampling capability"
                )
            )

        state = self._states.setdefault(session, _SessionState(asyncio.Semaphore(self._max_concurrent)))
        async with state.semaphore:
            await self._enforce_cooldown(state)
            metadata = (params.metadata or {}).copy()  # type: ignore[attr-defined]
            if "requestId" not in metadata:
                metadata["requestId"] = (
                    f"sampling-{id(self)}-{state.semaphore._value}"  # pragma: no cover - best effort
                )
            params.metadata = metadata  # type: ignore[attr-defined]

            try:
                with anyio.fail_after(self._timeout):
                    request = types.ServerRequest(types.CreateMessageRequest(params=params))
                    result = await session.send_request(request, types.CreateMessageResult)
            except TimeoutError:
                state.consecutive_failures += 1
                state.cooldown_until = anyio.current_time() + COOLDOWN_SECONDS
                raise McpError(
                    types.ErrorData(code=types.INTERNAL_ERROR, message="sampling request timed out")
                ) from None
            except McpError as exc:
                state.consecutive_failures += 1
                raise exc
            else:
                state.consecutive_failures = 0
                return result

    async def _enforce_cooldown(self, state: _SessionState) -> None:
        if state.consecutive_failures < FAILURE_THRESHOLD:
            return
        remaining = state.cooldown_until - anyio.current_time()
        if remaining > 0:
            raise McpError(
                types.ErrorData(
                    code=types.SERVICE_UNAVAILABLE, message="sampling temporarily unavailable; please retry later"
                )
            )
        state.consecutive_failures = 0

    def _current_session(self):
        try:
            ctx = request_ctx.get()
        except LookupError as exc:
            raise RuntimeError("Sampling requests require an active MCP session") from exc
        return ctx.session


__all__ = ["SamplingService"]
