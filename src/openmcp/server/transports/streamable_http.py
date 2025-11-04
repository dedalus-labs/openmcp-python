# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Streamable HTTP transport adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from ._asgi import ASGITransportBase, ASGITransportConfig, SessionManagerHandler
from ..._sdk_loader import ensure_sdk_importable


ensure_sdk_importable()

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..core import MCPServer


class StreamableHTTPTransport(ASGITransportBase):
    """Serve an :class:`openmcp.server.MCPServer` over Streamable HTTP."""

    TRANSPORT = ("streamable-http", "Streamable HTTP", "shttp", "sHTTP")

    def __init__(
        self, server: MCPServer, *, security_settings: TransportSecuritySettings | None = None, stateless: bool = False
    ) -> None:
        config = ASGITransportConfig(security_settings=security_settings, stateless=stateless)
        super().__init__(server, config=config)

    def _build_session_manager(self) -> StreamableHTTPSessionManager:
        security = self.security_settings

        if security is not None and not isinstance(security, TransportSecuritySettings):
            security = TransportSecuritySettings.model_validate(security)

        return StreamableHTTPSessionManager(self.server, security_settings=security, stateless=self.stateless)

    def _build_routes(self, *, path: str, handler: SessionManagerHandler) -> Iterable[Route]:
        return [Route(path, handler)]


__all__ = ["StreamableHTTPTransport"]
