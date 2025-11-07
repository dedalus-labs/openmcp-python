# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

from typing import Any

import pytest

from openmcp.server import MCPServer
from openmcp.server.core import ServerValidationError
from openmcp.server.transports import ASGIRunConfig
from openmcp.server.transports.base import BaseTransport


class _StubTransport(BaseTransport):
    def __init__(self, server: MCPServer) -> None:
        super().__init__(server)
        self.kwargs: dict[str, Any] | None = None

    async def run(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def stop(self) -> None:
        """Test stub implementation."""


def test_validate_passes_with_default_services() -> None:
    server = MCPServer("validation-happy-path")
    # Should not raise
    server.validate()


def test_validate_fails_when_prompts_missing() -> None:
    server = MCPServer("validation-missing-prompts")
    server.prompts = None  # type: ignore[assignment]

    with pytest.raises(ServerValidationError) as excinfo:
        server.validate()

    assert "Prompts capability" in str(excinfo.value)


@pytest.mark.anyio
async def test_serve_streamable_http_runs_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    server = MCPServer("validation-http")
    transport = _StubTransport(server)
    monkeypatch.setattr(server, "_transport_for_name", lambda _name: transport)

    called = False

    def fake_validate() -> None:
        nonlocal called
        called = True

    server.validate = fake_validate  # type: ignore[assignment]

    await server.serve_streamable_http(host="0.0.0.0", port=9999)

    assert called is True
    assert transport.kwargs is not None
    assert isinstance(transport.kwargs.get("config"), ASGIRunConfig)


@pytest.mark.anyio
async def test_serve_streamable_http_can_skip_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    server = MCPServer("validation-http-skip")
    transport = _StubTransport(server)
    monkeypatch.setattr(server, "_transport_for_name", lambda _name: transport)

    called = False

    def fake_validate() -> None:
        nonlocal called
        called = True

    server.validate = fake_validate  # type: ignore[assignment]

    await server.serve_streamable_http(validate=False)

    assert called is False
    assert transport.kwargs is not None
    assert isinstance(transport.kwargs.get("config"), ASGIRunConfig)
