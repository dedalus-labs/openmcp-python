from __future__ import annotations

import pytest

from mcp.server.transport_security import TransportSecuritySettings

from openmcp.server import MCPServer
from openmcp.server.transports import BaseTransport, StreamableHTTPTransport


class DummyTransport(BaseTransport):
    def __init__(self, server: MCPServer, calls: dict[str, object]) -> None:
        super().__init__(server)
        self.calls = calls

    async def run(self, **kwargs) -> None:  # pragma: no cover - exercised in tests
        self.calls["called"] = True
        self.calls["kwargs"] = kwargs


@pytest.mark.anyio
async def test_register_custom_transport_invoked() -> None:
    server = MCPServer("custom-transport")
    calls: dict[str, object] = {}

    server.register_transport("dummy", lambda srv: DummyTransport(srv, calls))

    await server.serve(transport="dummy", foo=42)

    assert calls.get("called") is True
    assert calls.get("kwargs") == {"foo": 42}


def test_default_http_security_settings() -> None:
    server = MCPServer("security-defaults")
    settings = server._http_security_settings  # internal detail, intentional

    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "https://as.dedaluslabs.ai" in settings.allowed_origins


def test_http_security_override() -> None:
    override = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["example.com:443"],
        allowed_origins=["https://example.com"],
    )

    server = MCPServer("security-override", http_security=override)

    assert server._http_security_settings is override

    transport = server._transport_for_name("streamable-http")
    assert isinstance(transport, StreamableHTTPTransport)
    assert transport._security_settings is override

    server.configure_streamable_http_security(None)
    assert server._http_security_settings != override
