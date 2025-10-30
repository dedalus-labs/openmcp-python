# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""End-to-end transport tests for subscription flows.

Exercises ``serve_stdio`` and ``serve_streamable_http`` using in-memory transports
so we can verify resource notifications traverse the wire exactly as the spec
requires (``docs/mcp/spec/schema-reference/resources-subscribe.md`` and
``docs/mcp/capabilities/resources``).
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

import anyio
import anyio.abc
from mcp.client.session import ClientSession
from mcp.shared.session import RequestResponder
import pytest

from openmcp import MCPServer, NotificationFlags, resource, types


async def _exercise_transport(
    monkeypatch: pytest.MonkeyPatch,
    apply_transport_patch: Callable[
        [pytest.MonkeyPatch, anyio.abc.ObjectReceiveStream[Any], anyio.abc.ObjectSendStream[Any]], None
    ],
    start_server: Callable[[MCPServer], anyio.abc.TaskStatus[Any] | anyio.abc.AsyncResource],
) -> tuple[types.InitializeResult, list[types.ServerNotification], tuple[int, int]]:
    """Spin up a server under the given transport and collect notifications."""
    server = MCPServer("integration", notification_flags=NotificationFlags(resources_changed=True))

    uri = "resource://demo/file"

    with server.binding():

        @resource(uri, description="Integration resource")
        def demo_resource() -> str:
            return "integration payload"

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(0)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(0)

    apply_transport_patch(monkeypatch, client_to_server_recv, server_to_client_send)

    notifications: list[types.ServerNotification] = []

    async def message_handler(
        message: RequestResponder[types.ServerRequest, types.ClientResult] | types.ServerNotification | Exception,
    ) -> None:
        if isinstance(message, RequestResponder):
            await message.error(
                types.ErrorData(code=types.INVALID_REQUEST, message="Test client does not handle server requests")
            )
            return
        if isinstance(message, Exception):  # pragma: no cover - defensive
            raise message
        notifications.append(message)

    async with anyio.create_task_group() as tg:
        tg.start_soon(start_server, server)

        session = ClientSession(
            server_to_client_recv,
            client_to_server_send,
            message_handler=message_handler,
            client_info=types.Implementation(name="integration-client", version="0.0.1"),
        )

        async with session as client_session:
            init_result = await client_session.initialize()

            list_result = await client_session.send_request(
                types.ClientRequest(types.ListResourcesRequest()), types.ListResourcesResult
            )
            assert list_result.resources
            assert str(list_result.resources[0].uri) == uri

            await client_session.send_request(
                types.ClientRequest(types.SubscribeRequest(params=types.SubscribeRequestParams(uri=uri))),
                types.EmptyResult,
            )

            await server.notify_resource_updated(uri)
            await anyio.sleep(0.05)

            initial_updates = sum(1 for note in notifications if note.root.method == "notifications/resources/updated")

            await client_session.send_request(
                types.ClientRequest(types.UnsubscribeRequest(params=types.UnsubscribeRequestParams(uri=uri))),
                types.EmptyResult,
            )

            await server.notify_resource_updated(uri)
            await anyio.sleep(0.05)

            post_unsubscribe_updates = sum(
                1 for note in notifications if note.root.method == "notifications/resources/updated"
            )

            await server.notify_resources_list_changed()
            await anyio.sleep(0.05)

        await client_to_server_send.aclose()
        await server_to_client_recv.aclose()
        tg.cancel_scope.cancel()

    await client_to_server_recv.aclose()
    await server_to_client_send.aclose()

    return init_result, notifications, (initial_updates, post_unsubscribe_updates)


@pytest.mark.anyio
async def test_stdio_subscription_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    async def start(server: MCPServer) -> None:
        await server.serve_stdio(raise_exceptions=True)

    def patch_stdio(monkeypatch: pytest.MonkeyPatch, recv, send) -> None:
        @asynccontextmanager
        async def fake_stdio(*_: object, **__: object):
            yield recv, send

        monkeypatch.setattr("openmcp.server.transports.stdio.get_stdio_server", lambda: fake_stdio, raising=False)

    init_result, notifications, (before_updates, after_updates) = await _exercise_transport(
        monkeypatch, patch_stdio, start
    )

    assert before_updates == after_updates

    resources_cap = init_result.capabilities.resources
    assert resources_cap and resources_cap.subscribe is True
    assert resources_cap.listChanged is True

    methods = [note.root.method for note in notifications]
    assert methods.count("notifications/resources/updated") == 1
    assert "notifications/resources/list_changed" in methods


@pytest.mark.anyio
async def test_streamable_http_subscription_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    async def start(server: MCPServer) -> None:
        await server.serve_streamable_http(host="127.0.0.1", port=3001, path="/mcp")

    def patch_streamable_http(monkeypatch: pytest.MonkeyPatch, recv, send) -> None:
        async def fake_run(
            self, *, host: str, port: int, path: str, log_level: str, uvicorn_options: dict[str, object]
        ) -> None:
            init_options = self._server.create_initialization_options()
            await self._server.run(
                recv,
                send,
                init_options,
                raise_exceptions=uvicorn_options.get("raise_exceptions", False),
                stateless=False,
            )

        monkeypatch.setattr("openmcp.server.transports.streamable_http.StreamableHTTPTransport._run_server", fake_run)

    init_result, notifications, (before_updates, after_updates) = await _exercise_transport(
        monkeypatch, patch_streamable_http, start
    )

    assert before_updates == after_updates

    resources_cap = init_result.capabilities.resources
    assert resources_cap and resources_cap.subscribe is True
    assert resources_cap.listChanged is True

    methods = [note.root.method for note in notifications]
    assert methods.count("notifications/resources/updated") == 1
    assert "notifications/resources/list_changed" in methods
