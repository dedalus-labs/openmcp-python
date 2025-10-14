"""Request context helpers for OpenMCP handlers.

The utilities in this module provide a stable surface over the reference
SDK's ``request_ctx`` primitive so application code can access
capabilities such as logging and progress without importing SDK internals.

Spec receipts referenced throughout the implementation:

* ``docs/mcp/capabilities/logging/index.md``
* ``docs/mcp/core/progress/index.md``
* ``docs/mcp/spec/schema-reference/notifications-progress.md``
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterator, Mapping

from ._sdk_loader import ensure_sdk_importable

ensure_sdk_importable()

from mcp.server.lowlevel.server import request_ctx
from mcp.shared.context import RequestContext
from mcp.types import LoggingLevel, ProgressToken

from .progress import ProgressConfig, ProgressTelemetry, ProgressTracker, progress as progress_manager

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mcp.server.session import ServerSession


_CURRENT_CONTEXT: ContextVar["Context | None"] = ContextVar("openmcp_current_context", default=None)


def get_context() -> "Context":
    """Return the active :class:`Context`.

    Raises:
        LookupError: If called outside of an MCP request handler.

    Example::

        from openmcp import get_context, tool

        @tool(description="Reports its own request id")
        async def whoami() -> str:
            ctx = get_context()
            await ctx.info("Handling whoami request")
            return ctx.request_id
    """

    ctx = _CURRENT_CONTEXT.get()
    if ctx is None:
        raise LookupError(
            "No active context; use get_context() from within a request handler",
        )
    return ctx


@dataclass(slots=True)
class Context:
    """Lightweight façade over the SDK request context.

    This wrapper keeps OpenMCP applications within the framework surface
    while still enabling access to logging and progress utilities mandated
    by the MCP specification.
    """

    _request_context: RequestContext

    # ------------------------------------------------------------------
    # Introspection helpers
    # ------------------------------------------------------------------

    @property
    def request_id(self) -> str:
        """Return the request identifier assigned by the SDK."""

        return str(self._request_context.request_id)

    @property
    def session(self) -> "ServerSession":
        """Expose the underlying session for advanced scenarios."""

        return self._request_context.session

    @property
    def progress_token(self) -> ProgressToken | None:
        """Return the progress token supplied by the client, if any."""

        meta = self._request_context.meta
        return None if meta is None else getattr(meta, "progressToken", None)

    # ------------------------------------------------------------------
    # Logging conveniences (docs/mcp/capabilities/logging/index.md)
    # ------------------------------------------------------------------

    async def log(
        self,
        level: LoggingLevel | str,
        message: str,
        *,
        logger: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Send a log message to the client.

        Args:
            level: Severity level defined by the MCP logging capability.
            message: Human-readable message describing the event.
            logger: Optional logger name for client-side routing.
            data: Optional structured payload merged into the log body.
        """

        payload: dict[str, Any] = {"msg": message}
        if data:
            payload.update(dict(data))

        await self._request_context.session.send_log_message(
            level=level,
            data=payload,
            logger=logger,
        )

    async def debug(self, message: str, *, logger: str | None = None, data: Mapping[str, Any] | None = None) -> None:
        await self.log("debug", message, logger=logger, data=data)

    async def info(self, message: str, *, logger: str | None = None, data: Mapping[str, Any] | None = None) -> None:
        await self.log("info", message, logger=logger, data=data)

    async def warning(self, message: str, *, logger: str | None = None, data: Mapping[str, Any] | None = None) -> None:
        await self.log("warning", message, logger=logger, data=data)

    async def error(self, message: str, *, logger: str | None = None, data: Mapping[str, Any] | None = None) -> None:
        await self.log("error", message, logger=logger, data=data)

    # ------------------------------------------------------------------
    # Progress helpers (docs/mcp/core/progress/index.md)
    # ------------------------------------------------------------------

    async def report_progress(
        self,
        progress: float,
        *,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        """Emit a single progress notification if the client requested one."""

        token = self.progress_token
        if token is None:
            return

        await self._request_context.session.send_progress_notification(
            progress_token=token,
            progress=progress,
            total=total,
            message=message,
        )

    def progress(
        self,
        total: float | None = None,
        *,
        config: ProgressConfig | None = None,
        telemetry: ProgressTelemetry | None = None,
    ) -> AsyncIterator[ProgressTracker]:
        """Return the coalescing progress context manager for this request."""

        return progress_manager(total=total, config=config, telemetry=telemetry)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_request_context(cls, request_context: RequestContext) -> "Context":
        """Build a :class:`Context` from the SDK request context."""

        return cls(_request_context=request_context)


def _activate_request_context() -> Token["Context | None"]:
    """Populate the ambient context var from the SDK request context."""

    request_context = request_ctx.get()
    context = Context.from_request_context(request_context)
    return _CURRENT_CONTEXT.set(context)


def _reset_context(token: Token["Context | None"]) -> None:
    """Restore the previous context after a handler completes."""

    _CURRENT_CONTEXT.reset(token)


@contextmanager
def context_scope() -> Iterator[Context]:
    """Context manager that activates the current request context."""

    token = _activate_request_context()
    try:
        yield get_context()
    finally:
        _reset_context(token)


__all__ = ["Context", "get_context", "context_scope"]
