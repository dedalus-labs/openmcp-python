# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Runtime protocols describing mandatory service behaviour.

The Model Context Protocol defines capability-specific invariants that servers
MUST uphold (see https://modelcontextprotocol.io/specification/2025-06-18/).
OpenMCP uses these protocols to validate that swappable service implementations
still conform to the required surface area before a server is allowed to run.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ToolsServiceProtocol(Protocol):
    """Contract required by the tools capability."""

    @property
    def tool_names(self) -> list[str]: ...

    async def list_tools(self, request: Any | None) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...

    async def notify_list_changed(self) -> None: ...


@runtime_checkable
class ResourcesServiceProtocol(Protocol):
    """Contract required by the resources capability."""

    async def list_resources(self, request: Any) -> Any: ...

    async def list_templates(self, cursor: str | None) -> Any: ...

    async def read(self, uri: str) -> Any: ...

    async def subscribe_current(self, uri: str) -> None: ...

    async def unsubscribe_current(self, uri: str) -> None: ...

    async def notify_updated(self, uri: str) -> None: ...

    async def notify_list_changed(self) -> None: ...


@runtime_checkable
class PromptsServiceProtocol(Protocol):
    """Contract required by the prompts capability."""

    @property
    def names(self) -> list[str]: ...

    async def list_prompts(self, request: Any) -> Any: ...

    async def get_prompt(self, name: str, arguments: dict[str, str] | None) -> Any: ...

    async def notify_list_changed(self) -> None: ...


@runtime_checkable
class RootsServiceProtocol(Protocol):
    """Contract required by the roots capability."""

    def guard(self, session: Any) -> Any: ...

    async def on_session_open(self, session: Any) -> Any: ...

    async def on_list_changed(self, session: Any) -> None: ...


@runtime_checkable
class CompletionServiceProtocol(Protocol):
    """Contract required by the completion capability."""

    def register(self, target: Any) -> Any: ...

    async def execute(self, ref: Any, argument: Any, context: Any | None) -> Any: ...


@runtime_checkable
class SamplingServiceProtocol(Protocol):
    """Contract required by the sampling capability."""

    async def create_message(self, params: Any) -> Any: ...


@runtime_checkable
class ElicitationServiceProtocol(Protocol):
    """Contract required by the elicitation capability."""

    async def create(self, params: Any) -> Any: ...


@runtime_checkable
class LoggingServiceProtocol(Protocol):
    """Contract required by the logging capability."""

    async def set_level(self, level: Any) -> None: ...

    async def emit(self, level: Any, data: Any, logger: str | None = None) -> None: ...


@runtime_checkable
class PingServiceProtocol(Protocol):
    """Contract required by ping/heartbeat support."""

    def register(self, session: Any) -> None: ...

    def touch(self, session: Any) -> None: ...

    async def ping(self, session: Any, *, timeout: float | None = None) -> bool: ...

    async def ping_many(
        self,
        sessions: Any = ...,
        *,
        timeout: float | None = None,
        max_concurrency: int | None = None,
    ) -> Any: ...

    def start_heartbeat(
        self,
        task_group: Any,
        *,
        interval: float = 5.0,
        jitter: float = 0.2,
        timeout: float = 2.0,
        phi_threshold: float | None = None,
        max_concurrency: int | None = None,
    ) -> None: ...


__all__ = [
    "CompletionServiceProtocol",
    "ElicitationServiceProtocol",
    "LoggingServiceProtocol",
    "PingServiceProtocol",
    "PromptsServiceProtocol",
    "ResourcesServiceProtocol",
    "RootsServiceProtocol",
    "SamplingServiceProtocol",
    "ToolsServiceProtocol",
]
