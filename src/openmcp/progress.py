# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Progress utilities for emitting MCP-compliant telemetry.

Implements progress notifications as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress
  (progress notification semantics, token requirements, progress flow)

Compared to the reference SDK helper, this implementation adds:

* Monotonicity enforcement so progress never regresses (per spec).
* Coalescing with configurable emission cadence and jitter to provide
  gentle backpressure while keeping latency low.
* At-least-once delivery with retry and final flush semantics.
* Optional telemetry hooks for observability and integration with
  tracing/metrics stacks.

Usage::

    async with progress(total=10) as tracker:
        await tracker.advance(3, message="Parsing")
        await tracker.set(7, message="Executing")
        await tracker.advance(3)

Handlers must only call :func:`progress` when the inbound request included a
``_meta.progressToken``. The helper raises :class:`ValueError` when the token is
absent per the MCP specification.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging
import math
import random
import time
from typing import Any

import anyio

from ._sdk_loader import ensure_sdk_importable
from .utils.logger import get_logger


ensure_sdk_importable()

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from mcp.shared.session import BaseSession
from mcp.types import ProgressToken, RequestId


__all__ = [
    "progress",
    "ProgressTracker",
    "ProgressConfig",
    "ProgressTelemetry",
    "ProgressLifecycleEvent",
    "ProgressEmitEvent",
    "ProgressThrottleEvent",
    "ProgressErrorEvent",
    "ProgressCloseEvent",
    "set_default_progress_config",
    "set_default_progress_telemetry",
]


_LOGGER = get_logger("openmcp.progress")
_SYSTEM_RANDOM = random.SystemRandom()


@dataclass(slots=True, frozen=True)
class ProgressConfig:
    """behavioral tuning knobs for progress emission.

    ``emit_hz`` controls the maximum emission frequency. Values ``<= 0``
    disable throttling, causing each update to send immediately. The
    ``retry_backoff`` window governs the sleep interval (in seconds) between
    retry attempts when a notification send fails.
    """

    emit_hz: float = 8.0
    retry_backoff: tuple[float, float] = (0.05, 0.25)

    @property
    def min_interval_ns(self) -> int:
        if self.emit_hz <= 0:
            return 0
        return int(1_000_000_000 / self.emit_hz)


@dataclass(slots=True, frozen=True)
class ProgressLifecycleEvent:
    """Lifecycle metadata emitted when a tracker starts."""

    token: ProgressToken
    request_id: RequestId
    total: float | None


@dataclass(slots=True, frozen=True)
class ProgressEmitEvent:
    """Event emitted after successfully sending a notification."""

    token: ProgressToken
    request_id: RequestId
    progress: float
    total: float | None
    message: str | None
    attempt: int
    duplicate: bool


@dataclass(slots=True, frozen=True)
class ProgressThrottleEvent:
    """Event raised when an update is coalesced due to rate limiting."""

    token: ProgressToken
    request_id: RequestId
    pending_updates: int
    latest_progress: float
    latest_total: float | None


@dataclass(slots=True, frozen=True)
class ProgressErrorEvent:
    """Event raised when sending a notification fails."""

    token: ProgressToken
    request_id: RequestId
    progress: float
    total: float | None
    message: str | None
    exception: BaseException


@dataclass(slots=True, frozen=True)
class ProgressCloseEvent:
    """Event raised when the tracker finishes and the emitter drains."""

    token: ProgressToken
    request_id: RequestId
    final_progress: float | None
    final_total: float | None
    final_message: str | None
    emitted: int


@dataclass(slots=True)
class ProgressTelemetry:
    """Container for optional instrumentation callbacks.

    Each callback receives one of the event dataclasses defined above. Users
    can supply any subset of callbacks; unspecified hooks default to no-ops.
    """

    on_start: Callable[[ProgressLifecycleEvent], None] | None = None
    on_emit: Callable[[ProgressEmitEvent], None] | None = None
    on_throttle: Callable[[ProgressThrottleEvent], None] | None = None
    on_error: Callable[[ProgressErrorEvent], None] | None = None
    on_close: Callable[[ProgressCloseEvent], None] | None = None

    def emit_start(self, event: ProgressLifecycleEvent) -> None:
        if self.on_start is not None:
            self.on_start(event)

    def emit_success(self, event: ProgressEmitEvent) -> None:
        if self.on_emit is not None:
            self.on_emit(event)

    def emit_throttle(self, event: ProgressThrottleEvent) -> None:
        if self.on_throttle is not None:
            self.on_throttle(event)

    def emit_error(self, event: ProgressErrorEvent) -> None:
        if self.on_error is not None:
            self.on_error(event)

    def emit_close(self, event: ProgressCloseEvent) -> None:
        if self.on_close is not None:
            self.on_close(event)


_DEFAULT_CONFIG = ProgressConfig()
_DEFAULT_TELEMETRY = ProgressTelemetry()


def set_default_progress_config(config: ProgressConfig) -> None:
    """Override the module-level default progress configuration."""
    global _DEFAULT_CONFIG
    _DEFAULT_CONFIG = config


def set_default_progress_telemetry(telemetry: ProgressTelemetry) -> None:
    """Override the module-level default telemetry hooks."""
    global _DEFAULT_TELEMETRY
    _DEFAULT_TELEMETRY = telemetry


@dataclass(slots=True, frozen=True)
class _ProgressState:
    progress: float
    total: float | None
    message: str | None
    timestamp_ns: int


class _ProgressEmitter:
    """Internal helper that coalesces progress updates and emits them."""

    def __init__(
        self,
        *,
        session: BaseSession[Any, Any, Any, Any, Any],
        token: ProgressToken,
        request_id: RequestId,
        total: float | None,
        logger: logging.Logger,
        telemetry: ProgressTelemetry,
        config: ProgressConfig,
    ) -> None:
        self._session = session
        self._token = token
        self._request_id = request_id
        self._default_total = total
        self._logger = logger
        self._telemetry = telemetry
        self._config = config

        self._lock = anyio.Lock()
        self._latest: _ProgressState | None = None
        self._last_emitted: _ProgressState | None = None
        self._last_emit_ns: int = 0
        self._closed = False
        self._pending_updates = 0
        self._event = anyio.Event()
        self._drained = anyio.Event()
        self._emitted_count = 0

    @property
    def token(self) -> ProgressToken:
        return self._token

    @property
    def request_id(self) -> RequestId:
        return self._request_id

    async def advance(self, amount: float, *, message: str | None = None, total: float | None = None) -> float:
        if not math.isfinite(amount):
            raise ValueError("progress increment must be a finite number")
        async with self._lock:
            base = self._current_progress_locked()
            target = base + amount
            _, throttled = self._store_state_locked(target, message=message, total_override=total)
        self._post_update(throttled)
        return target

    async def set(self, progress: float, *, message: str | None = None, total: float | None = None) -> None:
        if not math.isfinite(progress):
            raise ValueError("progress value must be finite")
        async with self._lock:
            _, throttled = self._store_state_locked(progress, message=message, total_override=total)
        self._post_update(throttled)

    async def close(self) -> None:
        async with self._lock:
            if not self._closed:
                if self._latest is None and self._last_emitted is not None:
                    # Re-emit the final state to guarantee at-least-once delivery.
                    self._latest = self._last_emitted
                self._closed = True
        self._event.set()
        await self._drained.wait()

    async def run(self) -> None:
        try:
            while True:
                await self._event.wait()
                while True:
                    async with self._lock:
                        state = self._latest
                        closed = self._closed
                        self._pending_updates = 0
                        if state is None:
                            if closed:
                                self._drained.set()
                                return
                            self._event = anyio.Event()
                            break
                        self._latest = None
                        delay = self._compute_delay(state.timestamp_ns)
                    if delay:
                        await anyio.sleep(delay)
                    await self._send_with_retry(state)
                    if closed:
                        async with self._lock:
                            if self._latest is None and self._closed:
                                self._drained.set()
                                return
                # loop continues when new updates arrive
        finally:
            if not self._drained.is_set():
                self._drained.set()

    def _current_progress_locked(self) -> float:
        if self._latest is not None:
            return self._latest.progress
        if self._last_emitted is not None:
            return self._last_emitted.progress
        return 0.0

    def _store_state_locked(
        self, progress: float, *, message: str | None, total_override: float | None
    ) -> tuple[_ProgressState, bool]:
        previous = self._latest or self._last_emitted
        if previous and progress < previous.progress:
            raise ValueError(
                "progress must be monotonically increasing per MCP specification "
                "(https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress)"
            )
        total = (
            total_override
            if total_override is not None
            else self._default_total
            if self._default_total is not None
            else previous.total
            if previous
            else None
        )
        state = _ProgressState(progress=progress, total=total, message=message, timestamp_ns=time.monotonic_ns())
        throttled = False
        min_interval_ns = self._config.min_interval_ns
        if min_interval_ns and self._last_emit_ns:
            elapsed = state.timestamp_ns - self._last_emit_ns
            if elapsed < min_interval_ns:
                throttled = True
                self._pending_updates += 1
        self._latest = state
        return state, throttled

    def _post_update(self, throttled: bool) -> None:
        if throttled and self._latest is not None:
            self._telemetry.emit_throttle(
                ProgressThrottleEvent(
                    token=self._token,
                    request_id=self._request_id,
                    pending_updates=self._pending_updates,
                    latest_progress=self._latest.progress,
                    latest_total=self._latest.total,
                )
            )
        self._event.set()

    def _compute_delay(self, timestamp_ns: int) -> float:
        min_interval_ns = self._config.min_interval_ns
        if not min_interval_ns or not self._last_emit_ns:
            return 0.0
        elapsed = timestamp_ns - self._last_emit_ns
        if elapsed >= min_interval_ns:
            return 0.0
        return (min_interval_ns - elapsed) / 1_000_000_000

    async def _send_with_retry(self, state: _ProgressState) -> None:
        attempt = 1
        duplicate = self._last_emitted is not None and (
            state.progress == self._last_emitted.progress
            and state.total == self._last_emitted.total
            and state.message == self._last_emitted.message
        )
        while True:
            try:
                await self._session.send_progress_notification(
                    self._token, state.progress, total=state.total, message=state.message
                )
            except (anyio.get_cancelled_exc_class(), KeyboardInterrupt):  # pragma: no cover - cancellation path
                raise
            except Exception as exc:  # pragma: no cover - network faults are rare in tests
                self._logger.warning(
                    "progress notification send failed; retrying",
                    exc_info=exc,
                    extra={
                        "progress_token": self._token,
                        "request_id": self._request_id,
                        "progress": state.progress,
                        "attempt": attempt,
                    },
                )
                self._telemetry.emit_error(
                    ProgressErrorEvent(
                        token=self._token,
                        request_id=self._request_id,
                        progress=state.progress,
                        total=state.total,
                        message=state.message,
                        exception=exc,
                    )
                )
                low, high = self._config.retry_backoff
                await anyio.sleep(_SYSTEM_RANDOM.uniform(low, high))
                attempt += 1
                continue
            else:
                async with self._lock:
                    self._last_emitted = state
                    self._last_emit_ns = time.monotonic_ns()
                self._emitted_count += 1
                self._logger.debug(
                    "progress emitted",
                    extra={
                        "progress_token": self._token,
                        "request_id": self._request_id,
                        "progress": state.progress,
                        "total": state.total,
                        "progress_message": state.message,
                        "attempt": attempt,
                        "duplicate": duplicate,
                    },
                )
                self._telemetry.emit_success(
                    ProgressEmitEvent(
                        token=self._token,
                        request_id=self._request_id,
                        progress=state.progress,
                        total=state.total,
                        message=state.message,
                        attempt=attempt,
                        duplicate=duplicate,
                    )
                )
                return

    def emit_close_telemetry(self) -> None:
        final_state = self._last_emitted or self._latest
        self._telemetry.emit_close(
            ProgressCloseEvent(
                token=self._token,
                request_id=self._request_id,
                final_progress=final_state.progress if final_state else None,
                final_total=final_state.total if final_state else None,
                final_message=final_state.message if final_state else None,
                emitted=self._emitted_count,
            )
        )


class ProgressTracker:
    """Object handed back to tool handlers to report progress."""

    def __init__(self, emitter: _ProgressEmitter) -> None:
        self._emitter = emitter

    @property
    def token(self) -> ProgressToken:
        return self._emitter.token

    @property
    def request_id(self) -> RequestId:
        return self._emitter.request_id

    async def advance(self, amount: float, message: str | None = None) -> float:
        """Advance progress by ``amount`` and return the new value."""
        return await self._emitter.advance(amount, message=message)

    async def set(self, progress: float, *, message: str | None = None, total: float | None = None) -> None:
        """Set progress explicitly.

        ``progress`` must be monotonically increasing as mandated by the MCP
        specification. ``total`` overrides the configured total for this update.
        """
        await self._emitter.set(progress, message=message, total=total)


def _resolve_request_context() -> RequestContext[BaseSession[Any, Any, Any, Any, Any], Any, Any]:
    try:
        ctx = request_ctx.get()
    except LookupError as exc:  # pragma: no cover - defensive
        raise RuntimeError("progress() requires an active request context") from exc
    if ctx.meta is None or ctx.meta.progressToken is None:
        raise ValueError(
            "progress() requires the caller to supply _meta.progressToken per MCP specification "
            "(https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/progress)"
        )
    return ctx


@asynccontextmanager
async def progress(
    total: float | None = None,
    *,
    config: ProgressConfig | None = None,
    telemetry: ProgressTelemetry | None = None,
    logger: logging.Logger | None = None,
) -> AsyncIterator[ProgressTracker]:
    """Return an async context manager for emitting MCP progress notifications.

    The returned tracker exposes :meth:`advance` and :meth:`set` helpers. This
    context manager must be used within an active MCP request handler so that
    ``request_ctx`` is available, mirroring the behavior of the reference SDK.

    """
    ctx = _resolve_request_context()
    session = ctx.session
    progress_token = ctx.meta.progressToken  # type: ignore[assignment]
    assert progress_token is not None  # for type checkers

    config = config or _DEFAULT_CONFIG
    telemetry = telemetry or _DEFAULT_TELEMETRY
    logger = logger or _LOGGER

    emitter = _ProgressEmitter(
        session=session,
        token=progress_token,
        request_id=ctx.request_id,
        total=total,
        logger=logger,
        telemetry=telemetry,
        config=config,
    )

    telemetry.emit_start(ProgressLifecycleEvent(token=progress_token, request_id=ctx.request_id, total=total))

    tracker = ProgressTracker(emitter)

    async with anyio.create_task_group() as tg:
        tg.start_soon(emitter.run)
        try:
            yield tracker
        finally:
            await emitter.close()
            emitter.emit_close_telemetry()
            tg.cancel_scope.cancel()
