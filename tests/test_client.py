# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import anyio
import pytest

from openmcp import types
from openmcp.client import ClientCapabilitiesConfig, MCPClient


class FakeClientSession:
    def __init__(
        self,
        *_streams: Any,
        sampling_callback: Callable[..., Any] | None = None,
        elicitation_callback: Callable[..., Any] | None = None,
        list_roots_callback: Callable[..., Any] | None = None,
        logging_callback: Callable[..., Any] | None = None,
        client_info: types.Implementation | None = None,
        **_: Any,
    ) -> None:
        self.sampling_callback = sampling_callback
        self.elicitation_callback = elicitation_callback
        self.list_roots_callback = list_roots_callback
        self.logging_callback = logging_callback
        self.client_info = client_info
        self.send_request_calls: list[tuple[types.ClientRequest, type[Any], dict[str, Any]]] = []
        self.notifications: list[types.ClientNotification] = []
        self.roots_notifications = 0
        self.next_result: Any = types.EmptyResult()

    async def __aenter__(self) -> FakeClientSession:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def initialize(self) -> types.InitializeResult:
        return types.InitializeResult(
            protocolVersion=types.LATEST_PROTOCOL_VERSION,
            capabilities=types.ServerCapabilities(),
            serverInfo=types.Implementation(name="fake", version="0.0.0"),
        )

    async def send_request(
        self,
        request: types.ClientRequest,
        result_type: type[Any],
        *,
        progress_callback: Callable[[float, float | None, str | None], Any] | None = None,
    ) -> Any:
        self.send_request_calls.append((request, result_type, {"progress_callback": progress_callback}))
        return self.next_result

    async def send_notification(self, notification: types.ClientNotification) -> None:
        self.notifications.append(notification)

    async def send_roots_list_changed(self) -> None:
        self.roots_notifications += 1


class SessionFactory:
    def __init__(self) -> None:
        self.instances: list[FakeClientSession] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakeClientSession:
        session = FakeClientSession(*args, **kwargs)
        self.instances.append(session)
        return session


@pytest.mark.anyio
async def test_client_initializes_without_optional_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = SessionFactory()
    monkeypatch.setattr("openmcp.client.core.ClientSession", factory)

    recv, send = anyio.create_memory_object_stream(0)
    async with MCPClient(recv, send) as client:
        assert client.initialize_result is not None
    session = factory.instances[0]
    assert session.list_roots_callback is None
    assert session.sampling_callback is None
    assert session.elicitation_callback is None
    assert session.logging_callback is None


@pytest.mark.anyio
async def test_client_enables_roots_and_sends_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = SessionFactory()
    monkeypatch.setattr("openmcp.client.core.ClientSession", factory)

    recv, send = anyio.create_memory_object_stream(0)
    capabilities = ClientCapabilitiesConfig(enable_roots=True, initial_roots=[{"uri": "file:///tmp"}])
    async with MCPClient(recv, send, capabilities=capabilities) as client:
        session = factory.instances[0]
        assert session.list_roots_callback is not None
        await client.update_roots([types.Root(uri="file:///new")])
        assert session.roots_notifications == 1
        roots = await client.list_roots()
        assert [str(root.uri) for root in roots] == ["file:///new"]
        assert client.roots_version() == 1


@pytest.mark.anyio
async def test_client_cancel_request_sends_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = SessionFactory()
    monkeypatch.setattr("openmcp.client.core.ClientSession", factory)

    recv, send = anyio.create_memory_object_stream(0)
    async with MCPClient(recv, send) as client:
        session = factory.instances[0]
        await client.cancel_request(42, reason="timeout")
        assert session.notifications
        note = session.notifications[-1]
        assert note.root.method == "notifications/cancelled"
        assert note.root.params.reason == "timeout"
        assert note.root.params.requestId == 42


@pytest.mark.anyio
async def test_send_request_and_ping_delegate_to_session(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = SessionFactory()
    monkeypatch.setattr("openmcp.client.core.ClientSession", factory)

    recv, send = anyio.create_memory_object_stream(0)
    async with MCPClient(recv, send) as client:
        session = factory.instances[0]
        expected = types.EmptyResult()
        session.next_result = expected
        result = await client.ping()
        assert result is expected
        assert session.send_request_calls
        request, result_type, extras = session.send_request_calls[0]
        assert request.root.method == "ping"
        assert result_type is types.EmptyResult
        assert extras["progress_callback"] is None


@pytest.mark.anyio
async def test_sampling_and_elicitation_handlers_wrapped(monkeypatch: pytest.MonkeyPatch) -> None:
    factory = SessionFactory()
    monkeypatch.setattr("openmcp.client.core.ClientSession", factory)

    async def sampling_handler(ctx: Any, params: types.CreateMessageRequestParams) -> types.CreateMessageResult:
        content = types.TextContent(type="text", text="ok")
        return types.CreateMessageResult(role="assistant", content=content, model="stub")

    async def elicitation_handler(ctx: Any, params: types.ElicitRequestParams) -> types.ElicitResult:
        return types.ElicitResult(action="accept", content={})

    recv, send = anyio.create_memory_object_stream(0)
    config = ClientCapabilitiesConfig(sampling=sampling_handler, elicitation=elicitation_handler)
    async with MCPClient(recv, send, capabilities=config):
        session = factory.instances[0]
        assert session.sampling_callback is not None
        assert session.elicitation_callback is not None
        # Call wrappers directly to ensure they forward to user handlers
        ctx = object()
        params = types.CreateMessageRequestParams(model="m", messages=[], maxTokens=1)
        result = await session.sampling_callback(ctx, params)
        assert isinstance(result, types.CreateMessageResult)

        elicit_params = types.ElicitRequestParams(
            message="Provide", requestedSchema={"type": "object", "properties": {"value": {"type": "string"}}}
        )
        elicit_result = await session.elicitation_callback(ctx, elicit_params)
        assert isinstance(elicit_result, types.ElicitResult)
