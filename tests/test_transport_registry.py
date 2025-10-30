# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

from typing import Any

from mcp.server.transport_security import TransportSecuritySettings
import pytest

from openmcp.server import MCPServer
from openmcp.server.transports import BaseTransport, StreamableHTTPTransport
from openmcp.server.transports._starlette import SessionManagerHandler


class DummyTransport(BaseTransport):
    def __init__(self, server: MCPServer, calls: dict[str, object]) -> None:
        super().__init__(server)
        self.calls = calls

    async def run(self, **kwargs: Any) -> None:
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
    settings = server._http_security_settings  # internal detail, intentional  # noqa: SLF001

    assert settings.enable_dns_rebinding_protection is True
    assert "127.0.0.1:*" in settings.allowed_hosts
    assert "https://as.dedaluslabs.ai" in settings.allowed_origins


def test_http_security_override() -> None:
    override = TransportSecuritySettings(
        enable_dns_rebinding_protection=True, allowed_hosts=["example.com:443"], allowed_origins=["https://example.com"]
    )

    server = MCPServer("security-override", http_security=override)

    assert server._http_security_settings is override  # noqa: SLF001

    transport = server._transport_for_name("streamable-http")  # noqa: SLF001
    assert isinstance(transport, StreamableHTTPTransport)
    assert transport._security_settings is override  # noqa: SLF001

    server.configure_streamable_http_security(None)
    assert server._http_security_settings != override  # noqa: SLF001


@pytest.mark.anyio
async def test_streamable_http_application_rejects_non_http_scope() -> None:
    class DummyManager:
        async def handle_request(self, *_args: object, **_kwargs: object) -> None:  # pragma: no cover - defensive
            message = "handle_request should not be invoked for non-http scopes"
            raise AssertionError(message)

    app = SessionManagerHandler(
        session_manager=DummyManager(), transport_label="Streamable HTTP transport", allowed_scopes=("http",)
    )

    async def receive() -> dict[str, object]:  # pragma: no cover - never called
        return {"type": "http.disconnect"}

    async def send(_message: dict[str, object]) -> None:  # pragma: no cover - never called
        message = "send should not be invoked for non-http scopes"
        raise AssertionError(message)

    with pytest.raises(TypeError) as excinfo:
        await app({"type": "lifespan"}, receive, send)

    assert "Streamable HTTP" in str(excinfo.value)
