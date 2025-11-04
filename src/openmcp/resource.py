# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Resource registration utilities for OpenMCP.

Implements the resources capability as specified in the Model Context Protocol:

- https://modelcontextprotocol.io/specification/2025-06-18/server/resources
  (resources capability, list and read operations)

Usage mirrors the :mod:`openmcp.tool` ambient registration pattern. Decorated
functions return text (str) or binary (bytes) content for resource URIs.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass

from . import types


if types:
    types.Resource  # noqa: B018

from typing import TYPE_CHECKING


if TYPE_CHECKING:  # pragma: no cover
    from .server import MCPServer

ResourceFn = Callable[[], str | bytes]


@dataclass(slots=True)
class ResourceSpec:
    uri: str
    fn: ResourceFn
    name: str | None = None
    description: str | None = None
    mime_type: str | None = None


_RESOURCE_ATTR = "__openmcp_resource__"
_ACTIVE_SERVER: ContextVar[MCPServer | None] = ContextVar("_openmcp_resource_server", default=None)


def get_active_server() -> MCPServer | None:
    return _ACTIVE_SERVER.get()


def set_active_server(server: MCPServer) -> object:
    return _ACTIVE_SERVER.set(server)


def reset_active_server(token: object) -> None:
    _ACTIVE_SERVER.reset(token)


def resource(
    uri: str, *, name: str | None = None, description: str | None = None, mime_type: str | None = None
) -> Callable[[ResourceFn], ResourceFn]:
    """Register a resource-producing callable.

    The decorated function must return ``str`` (text) or ``bytes`` (binary)
    content.  Registration happens immediately if inside
    :meth:`openmcp.server.MCPServer.binding`.
    """

    def decorator(fn: ResourceFn) -> ResourceFn:
        spec = ResourceSpec(uri=uri, fn=fn, name=name, description=description, mime_type=mime_type)
        setattr(fn, _RESOURCE_ATTR, spec)

        server = get_active_server()
        if server is not None:
            server.register_resource(spec)
        return fn

    return decorator


def extract_resource_spec(fn: ResourceFn) -> ResourceSpec | None:
    spec = getattr(fn, _RESOURCE_ATTR, None)
    if isinstance(spec, ResourceSpec):
        return spec
    return None


__all__ = ["resource", "ResourceSpec", "extract_resource_spec", "set_active_server", "reset_active_server"]
