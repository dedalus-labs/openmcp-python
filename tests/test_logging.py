# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Logging capability tests for logging/setLevel."""

from __future__ import annotations

import logging

import anyio
from mcp.shared.exceptions import McpError
import pytest

from openmcp import MCPServer, types
from tests.helpers import DummySession, run_with_context


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("debug", logging.DEBUG),
        ("info", logging.INFO),
        ("notice", logging.INFO),
        ("warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.CRITICAL),
        ("alert", logging.CRITICAL),
        ("emergency", logging.CRITICAL),
    ],
)
async def test_logging_set_level_handler(level: str, expected: int) -> None:
    server = MCPServer("logging-handler")
    handler = server.request_handlers[types.SetLevelRequest]
    request = types.SetLevelRequest(params=types.SetLevelRequestParams(level=level))

    root_logger = logging.getLogger()
    original_root = root_logger.level
    original_server = server._logger.level

    try:
        result = await handler(request)
        assert isinstance(result, types.ServerResult)
        assert root_logger.level == expected
        assert server._logger.level == expected
    finally:
        root_logger.setLevel(original_root)
        server._logger.setLevel(original_server)


@pytest.mark.anyio
async def test_logging_set_level_invalid_value() -> None:
    server = MCPServer("logging-invalid")
    handler = server.request_handlers[types.SetLevelRequest]
    params = types.SetLevelRequestParams.model_construct(level="verbose")
    request = types.SetLevelRequest.model_construct(method="logging/setLevel", params=params)

    with pytest.raises(McpError):
        await handler(request)


@pytest.mark.anyio
async def test_logging_notifications_respect_level() -> None:
    server = MCPServer("logging-notify")
    handler = server.request_handlers[types.SetLevelRequest]
    session = DummySession("logger")

    request = types.SetLevelRequest(params=types.SetLevelRequestParams(level="error"))
    await run_with_context(session, handler, request)
    assert server.logging_service._session_levels  # type: ignore[attr-defined]
    threshold = list(server.logging_service._session_levels.values())[0]  # type: ignore[attr-defined]
    assert threshold == logging.ERROR

    server._logger.info("info should be filtered")
    assert session.notifications == []

    original = server.logging_service.handle_log_record
    calls: list[logging.LogRecord] = []

    async def wrapper(record: logging.LogRecord) -> None:
        calls.append(record)
        await original(record)

    server.logging_service.handle_log_record = wrapper  # type: ignore[assignment]
    server._logger.error("boom!")
    await anyio.sleep(0.05)
    server.logging_service.handle_log_record = original  # type: ignore[assignment]

    assert calls
    assert server.logging_service._session_levels  # type: ignore[attr-defined]
    assert len(session.notifications) == 1
    note = session.notifications[-1].root
    assert note.method == "notifications/message"
    assert note.params.level == "error"
    assert note.params.data["message"] == "boom!"


@pytest.mark.anyio
async def test_logging_manual_emit_overrides() -> None:
    server = MCPServer("logging-manual")
    handler = server.request_handlers[types.SetLevelRequest]
    session = DummySession("manual")

    request = types.SetLevelRequest(params=types.SetLevelRequestParams(level="debug"))
    await run_with_context(session, handler, request)

    await server.log_message("warning", {"message": "explicit"}, logger="demo")
    await anyio.sleep(0.05)

    assert len(session.notifications) == 1
    note = session.notifications[-1].root
    assert note.params.level == "warning"
    assert note.params.logger == "demo"
    assert note.params.data == {"message": "explicit"}
