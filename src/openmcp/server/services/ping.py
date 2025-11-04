# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Ping helpers for MCP servers.

Implements ping/pong keepalive as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping

Includes phi-accrual failure detection for adaptive suspicion scoring and EWMA
RTT tracking beyond basic spec requirements.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable
import math
import time
from typing import TYPE_CHECKING
import weakref

import anyio
import anyio.abc


if TYPE_CHECKING:  # pragma: no cover - typing only
    from logging import Logger

    from mcp.server.session import ServerSession

    from ..notifications import NotificationSink

import secrets


class PingService:
    """Track active sessions, compute suspicion, and issue ping probes."""

    def __init__(
        self,
        *,
        notification_sink: NotificationSink | None = None,
        logger: Logger | None = None,
        ewma_alpha: float = 0.2,
        history_size: int = 32,
        failure_budget: int = 3,
        default_phi: float = 5.0,
        rng: Callable[[float, float], float] | None = None,
        on_suspect: Callable[[ServerSession, float], None] | None = None,
        on_down: Callable[[ServerSession], None] | None = None,
    ) -> None:
        self.notification_sink = notification_sink
        self._logger = logger
        self._sessions: weakref.WeakSet[ServerSession] = weakref.WeakSet()
        self._states: weakref.WeakKeyDictionary[ServerSession, _SessionState] = weakref.WeakKeyDictionary()
        self._ewma_alpha = ewma_alpha
        self._history_size = history_size
        self._failure_budget = failure_budget
        self._default_phi = default_phi
        self._heartbeat_config: _HeartbeatConfig | None = None
        self._rng = rng or _system_uniform
        self._on_suspect = on_suspect
        self._on_down = on_down

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def register(self, session: ServerSession) -> None:
        if session not in self._sessions:
            self._sessions.add(session)
            self._states[session] = _SessionState(history_size=self._history_size)

    def discard(self, session: ServerSession) -> None:
        self._sessions.discard(session)
        self._states.pop(session, None)

    def active(self) -> tuple[ServerSession, ...]:
        return tuple(self._sessions)

    def touch(self, session: ServerSession) -> None:
        self._state(session).touch(time.monotonic_ns())

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    def _state(self, session: ServerSession) -> _SessionState:
        state = self._states.get(session)
        if state is None:
            state = _SessionState(history_size=self._history_size)
            self._states[session] = state
        return state

    def round_trip_time(self, session: ServerSession) -> float | None:
        return self._state(session).ewma_rtt

    def suspicion(self, session: ServerSession, *, now: float | None = None) -> float:
        state = self._state(session)
        return state.phi(now=now)

    def is_alive(self, session: ServerSession, *, phi_threshold: float | None = None) -> bool:
        state = self._state(session)
        threshold = phi_threshold if phi_threshold is not None else self._default_phi
        return state.consecutive_failures <= self._failure_budget and state.phi() < threshold

    # ------------------------------------------------------------------
    # Ping execution
    # ------------------------------------------------------------------

    async def ping(self, session: ServerSession, *, timeout: float | None = None) -> bool:
        state = self._state(session)
        started_ns = time.monotonic_ns()
        try:
            if timeout is None:
                await session.send_ping()
            else:
                async with anyio.fail_after(timeout):
                    await session.send_ping()
        except (anyio.get_cancelled_exc_class(), KeyboardInterrupt):  # pragma: no cover - cancellation
            raise
        except Exception as exc:
            state.record_failure(time.monotonic_ns())
            self._log("ping-failed", session, error=str(exc))
            return False

        finished_ns = time.monotonic_ns()
        rtt_seconds = (finished_ns - started_ns) / 1_000_000_000
        state.record_success(finished_ns, rtt_seconds, self._ewma_alpha)
        self._log("ping-healthy", session, rtt_ms=rtt_seconds * 1000.0)
        return True

    async def ping_many(
        self,
        sessions: Iterable[ServerSession] | None = None,
        *,
        timeout: float | None = None,
        max_concurrency: int | None = None,
    ) -> dict[ServerSession, bool]:
        targets = tuple(sessions) if sessions is not None else self.active()
        results: dict[ServerSession, bool] = {}
        semaphore = anyio.Semaphore(max_concurrency) if max_concurrency else None

        async def _probe(target: ServerSession) -> None:
            if semaphore:
                async with semaphore:
                    results[target] = await self.ping(target, timeout=timeout)
            else:
                results[target] = await self.ping(target, timeout=timeout)

        async with anyio.create_task_group() as tg:
            for target in targets:
                tg.start_soon(_probe, target)

        return results

    # //////////////////////////////////////////////////////////////////
    # Heartbeat loop
    # //////////////////////////////////////////////////////////////////

    def start_heartbeat(
        self,
        task_group: anyio.abc.TaskGroup,
        *,
        interval: float = 5.0,
        jitter: float = 0.2,
        timeout: float = 2.0,
        phi_threshold: float | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        if self._heartbeat_config is not None:
            raise RuntimeError("Ping heartbeat already started")
        self._heartbeat_config = _HeartbeatConfig(
            interval=interval,
            jitter=jitter,
            timeout=timeout,
            phi_threshold=phi_threshold or self._default_phi,
            max_concurrency=max_concurrency,
        )
        task_group.start_soon(self._heartbeat_loop)

    async def _heartbeat_loop(self) -> None:
        assert self._heartbeat_config is not None  # for type checkers
        cfg = self._heartbeat_config
        while True:
            delay = cfg.interval
            if cfg.jitter:
                delta = cfg.jitter * cfg.interval
                delay = max(0.0, self._rng(cfg.interval - delta, cfg.interval + delta))
            await anyio.sleep(delay)

            if not self._sessions:
                continue

            results = await self.ping_many(timeout=cfg.timeout, max_concurrency=cfg.max_concurrency)

            now_ns = time.monotonic_ns()
            for session, ok in results.items():
                state = self._state(session)
                phi_now = state.phi(now=now_ns)
                alive = state.consecutive_failures <= self._failure_budget and phi_now < cfg.phi_threshold
                if alive:
                    self._log("ping-healthy", session, phi=phi_now)
                    continue

                self._log("ping-suspect", session, phi=phi_now, failures=state.consecutive_failures)
                if self._on_suspect:
                    self._on_suspect(session, phi_now)

                if state.consecutive_failures > self._failure_budget:
                    self._log("ping-down", session, phi=phi_now, failures=state.consecutive_failures)
                    if self._on_down:
                        self._on_down(session)
                    self.discard(session)

    # //////////////////////////////////////////////////////////////////
    # Internal utilities
    # //////////////////////////////////////////////////////////////////

    def _log(self, event: str, session: ServerSession, **extra: object) -> None:
        if not self._logger:
            return
        payload = {"event": event, "session_id": getattr(session, "id", None), **extra}
        level_map = {"ping-healthy": "debug", "ping-suspect": "info", "ping-failed": "warning", "ping-down": "error"}
        method = getattr(self._logger, level_map.get(event, "debug"), self._logger.debug)
        method("ping", extra=payload)


class _SessionState:
    __slots__ = ("consecutive_failures", "ewma_rtt", "history_size", "intervals", "last_failure_ns", "last_success_ns")

    def __init__(self, *, history_size: int) -> None:
        self.history_size = history_size
        self.intervals: deque[float] = deque(maxlen=history_size)
        self.last_success_ns: int = time.monotonic_ns()
        self.last_failure_ns: int | None = None
        self.ewma_rtt: float | None = None
        self.consecutive_failures: int = 0

    def record_success(self, timestamp_ns: int, rtt_seconds: float, alpha: float) -> None:
        if self.ewma_rtt is None:
            self.ewma_rtt = rtt_seconds
        else:
            self.ewma_rtt = self.ewma_rtt + alpha * (rtt_seconds - self.ewma_rtt)

        interval = (timestamp_ns - self.last_success_ns) / 1_000_000_000
        if interval > 0:
            self.intervals.append(interval)

        self.last_success_ns = timestamp_ns
        self.consecutive_failures = 0

    def record_failure(self, timestamp_ns: int) -> None:
        self.last_failure_ns = timestamp_ns
        self.consecutive_failures += 1

    def touch(self, timestamp_ns: int) -> None:
        interval = (timestamp_ns - self.last_success_ns) / 1_000_000_000
        if interval > 0:
            self.intervals.append(interval)
        self.last_success_ns = timestamp_ns
        self.consecutive_failures = 0

    def phi(self, *, now: float | None = None, now_ns: int | None = None) -> float:
        if not self.intervals:
            return 0.0
        mean = sum(self.intervals) / len(self.intervals)
        if mean <= 1e-6:
            return 0.0
        if now_ns is not None:
            delta = max(0.0, (now_ns - self.last_success_ns) / 1_000_000_000)
        else:
            now = now or time.monotonic()
            delta = max(0.0, now - (self.last_success_ns / 1_000_000_000))
        lambda_ = 1.0 / mean
        try:
            cdf = 1.0 - math.exp(-lambda_ * delta)
        except OverflowError:  # pragma: no cover - large delta safety
            return float("inf")
        cdf = min(max(cdf, 1e-12), 1 - 1e-12)
        return -math.log10(1.0 - cdf)


class _HeartbeatConfig:
    __slots__ = ("interval", "jitter", "max_concurrency", "phi_threshold", "timeout")

    def __init__(
        self, *, interval: float, jitter: float, timeout: float, phi_threshold: float, max_concurrency: int | None
    ) -> None:
        self.interval = interval
        self.jitter = jitter
        self.timeout = timeout
        self.phi_threshold = phi_threshold
        self.max_concurrency = max_concurrency


def _system_uniform(a: float, b: float) -> float:
    if a > b:
        a, b = b, a
    width = b - a
    if width <= 0:
        return a
    # 53 bits -> IEEE double mantissa
    return a + (secrets.randbits(53) / (1 << 53)) * width
