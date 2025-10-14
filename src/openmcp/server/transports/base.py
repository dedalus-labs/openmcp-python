"""Shared transport primitives for :mod:`openmcp.server`.

Provides a minimal base class that custom transports can subclass and a factory
signature that `MCPServer` uses to instantiate transports lazily.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from ..app import MCPServer


class BaseTransport(ABC):
    """Common base for server transports.

    Subclasses receive the active :class:`MCPServer` instance so they can obtain
    initialization options or interact with server helpers.  Implementations
    must define :meth:`run`, which accepts keyword arguments specific to the
    transport (e.g. host/port for HTTP or ``raise_exceptions`` for stdio).
    """

    def __init__(self, server: "MCPServer") -> None:
        self._server = server

    @property
    def server(self) -> "MCPServer":
        """Return the owning :class:`MCPServer`."""

        return self._server

    @abstractmethod
    async def run(self, **kwargs) -> None:
        """Start the transport.

        Parameters are free-form and depend on the concrete transport.  The base
        class only requires async execution so transports can be awaited
        directly from ``asyncio`` contexts.
        """


@runtime_checkable
class TransportFactory(Protocol):
    """Callable that produces a configured transport for an ``MCPServer``."""

    def __call__(self, server: "MCPServer") -> BaseTransport:  # pragma: no cover - protocol
        ...


__all__ = ["BaseTransport", "TransportFactory"]
