"""Resource capability tests following the MCP spec receipts.

See ``docs/mcp/spec/schema-reference/resources-read.md`` for the binary encoding
rules and ``resources-subscribe.md`` for subscription capability toggles.
"""

from __future__ import annotations

import base64
import gc
import weakref

import anyio
import pytest

from openmcp import MCPServer, NotificationFlags, resource, types
from mcp.shared.exceptions import McpError

from tests.helpers import DummySession, FailingSession, run_with_context


@pytest.mark.asyncio
async def test_resource_registration_and_read():
    server = MCPServer("resources-demo")

    with server.collecting():
        @resource("resource://demo/greeting", name="greeting", description="Simple greeting")
        def greeting() -> str:
            return "hello world"

    listed = await server.invoke_resource("resource://demo/greeting")
    assert listed.contents
    content = listed.contents[0]
    assert content.text == "hello world"
    assert content.mimeType == "text/plain"

    resources = server.register_resource(greeting)  # should be idempotent
    assert resources.uri == "resource://demo/greeting"

    listed_resources = await server.invoke_resource("resource://demo/greeting")
    assert listed_resources.contents[0].text == "hello world"


@pytest.mark.anyio
async def test_resource_subscription_emits_updates():
    server = MCPServer("resources-subscribe")
    session = DummySession()
    await run_with_context(session, server.resources.subscribe_current, "resource://demo/file")

    await server.notify_resource_updated("resource://demo/file")

    assert len(session.notifications) == 1
    notification = session.notifications[0]
    assert notification.root.method == "notifications/resources/updated"
    assert str(notification.root.params.uri) == "resource://demo/file"


@pytest.mark.anyio
async def test_resource_unknown_uri_returns_empty_contents():
    server = MCPServer("resources-missing")

    result = await server.invoke_resource("resource://demo/missing")
    assert result.contents == []


@pytest.mark.anyio
async def test_resource_unsubscribe_stops_notifications():
    server = MCPServer("resources-unsubscribe")
    session = DummySession()
    await run_with_context(session, server.resources.subscribe_current, "resource://demo/file")
    await run_with_context(session, server.resources.unsubscribe_current, "resource://demo/file")

    await server.notify_resource_updated("resource://demo/file")
    assert session.notifications == []


@pytest.mark.anyio
async def test_resource_subscribe_capability_advertised():
    server = MCPServer("resources-capability-flag")
    options = server.create_initialization_options()
    assert options.capabilities.resources
    assert options.capabilities.resources.subscribe is True


@pytest.mark.asyncio
async def test_resource_binary_content_encoding():
    """Binary resources must surface as base64 blobs per the spec.

    Read more: https://modelcontextprotocol.io/specification/2025-06-18/schema#blobresourcecontents

    """
    payload = b"\x00\x01\x02demo"
    server = MCPServer("resources-binary")

    with server.collecting():
        @resource("resource://demo/binary", mime_type="application/octet-stream")
        def binary() -> bytes:
            return payload

    result = await server.invoke_resource("resource://demo/binary")
    assert result.contents
    blob = result.contents[0]
    assert isinstance(blob, types.BlobResourceContents)
    assert blob.mimeType == "application/octet-stream"
    assert base64.b64decode(blob.blob) == payload


def test_resource_subscribe_capability_flag():
    """`resources.subscribe` is advertised by default and remains enabled after overrides."""

    server = MCPServer("resources-capability")
    init_opts = server.create_initialization_options()
    assert init_opts.capabilities.resources
    assert init_opts.capabilities.resources.subscribe is True

    @server.subscribe_resource()
    async def _sub(uri: str) -> None:  # pragma: no cover
        return None

    @server.unsubscribe_resource()
    async def _unsub(uri: str) -> None:  # pragma: no cover
        return None

    updated_opts = server.create_initialization_options()
    assert updated_opts.capabilities.resources
    assert updated_opts.capabilities.resources.subscribe is True


def test_resources_list_changed_capability_flag():
    server = MCPServer(
        "resources-list-flag",
        notification_flags=NotificationFlags(resources_changed=True),
    )

    init_opts = server.create_initialization_options()
    assert init_opts.capabilities.resources
    assert init_opts.capabilities.resources.listChanged is True


@pytest.mark.anyio
async def test_resource_subscription_duplicate_registration():
    server = MCPServer("resources-duplicate")
    session = DummySession("dup")
    uri = "resource://demo/dup"

    await run_with_context(session, server.resources.subscribe_current, uri)
    await run_with_context(session, server.resources.subscribe_current, uri)

    await server.notify_resource_updated(uri)
    assert len(session.notifications) == 1

    subscribers = await server.resources.subscriptions.subscribers(uri)
    assert len(subscribers) == 1


@pytest.mark.anyio
async def test_resource_subscription_garbage_collection_cleanup():
    server = MCPServer("resources-gc")
    uri = "resource://demo/gc"
    session = DummySession("gc")
    await run_with_context(session, server.resources.subscribe_current, uri)

    session_ref = weakref.ref(session)
    session = None  # drop strong reference
    gc.collect()
    await anyio.sleep(0)

    await server.notify_resource_updated(uri)

    by_uri, _ = await server.resources.subscriptions.snapshot()
    assert session_ref() is None
    assert len(by_uri.get(uri, [])) == 0


@pytest.mark.anyio
async def test_resource_subscription_high_volume_notifications():
    server = MCPServer("resources-volume")
    uri = "resource://demo/high"
    sessions = [DummySession(f"vol-{i}") for i in range(50)]

    async with anyio.create_task_group() as tg:
        for session in sessions:
            tg.start_soon(run_with_context, session, server.resources.subscribe_current, uri)

    await server.notify_resource_updated(uri)
    for session in sessions:
        assert len(session.notifications) == 1

    await server.notify_resource_updated(uri)
    for session in sessions:
        assert len(session.notifications) == 2


@pytest.mark.anyio
async def test_resource_subscription_concurrent_activity():
    server = MCPServer("resources-concurrent")
    uri = "resource://demo/concurrent"
    sessions = [DummySession(f"conc-{i}") for i in range(10)]

    async def worker(session: DummySession) -> None:
        for _ in range(5):
            await run_with_context(session, server.resources.subscribe_current, uri)
            await server.notify_resource_updated(uri)
            await run_with_context(session, server.resources.unsubscribe_current, uri)

    async with anyio.create_task_group() as tg:
        for session in sessions:
            tg.start_soon(worker, session)

    max_expected = len(sessions) * 5
    for session in sessions:
        assert 0 < len(session.notifications) <= max_expected

    by_uri, _ = await server.resources.subscriptions.snapshot()
    assert not by_uri.get(uri)


@pytest.mark.anyio
async def test_resource_subscription_failed_session_cleanup():
    server = MCPServer("resources-failing")
    uri = "resource://demo/failing"
    session = FailingSession()

    await run_with_context(session, server.resources.subscribe_current, uri)
    await server.notify_resource_updated(uri)
    by_uri, _ = await server.resources.subscriptions.snapshot()
    assert session.failures == 1
    assert len(by_uri.get(uri, [])) == 0


@pytest.mark.anyio
async def test_resources_list_pagination():
    server = MCPServer("resources-pagination")
    for idx in range(120):
        uri = f"resource://demo/{idx:03d}"

        def make_resource(value: str):
            @resource(uri, description=value)
            def _res() -> str:
                return value

            return _res

        server.register_resource(make_resource(f"res-{idx}"))

    handler = server.request_handlers[types.ListResourcesRequest]

    first = await run_with_context(DummySession("res-pages-1"), handler, types.ListResourcesRequest())
    first_result = first.root
    assert len(first_result.resources) == 50
    assert first_result.nextCursor == "50"

    second_request = types.ListResourcesRequest(params=types.PaginatedRequestParams(cursor="50"))
    second = await run_with_context(DummySession("res-pages-2"), handler, second_request)
    second_result = second.root
    assert len(second_result.resources) == 50
    assert second_result.nextCursor == "100"

    third_request = types.ListResourcesRequest(params=types.PaginatedRequestParams(cursor="100"))
    third = await run_with_context(DummySession("res-pages-3"), handler, third_request)
    third_result = third.root
    assert len(third_result.resources) == 20
    assert third_result.nextCursor is None


@pytest.mark.anyio
async def test_resources_list_invalid_cursor():
    server = MCPServer("resources-invalid-cursor")

    @resource("resource://demo/a")
    def _res() -> str:
        return "a"

    server.register_resource(_res)
    handler = server.request_handlers[types.ListResourcesRequest]
    request = types.ListResourcesRequest(params=types.PaginatedRequestParams(cursor="bad"))

    with pytest.raises(McpError) as excinfo:
        await run_with_context(DummySession("res-invalid"), handler, request)

    assert excinfo.value.error.code == types.INVALID_PARAMS


@pytest.mark.anyio
async def test_resources_list_negative_cursor_clamps_to_start():
    server = MCPServer("resources-negative-cursor")

    for idx in range(3):

        @resource(f"resource://demo/{idx}")
        def _res(value=idx):  # pragma: no cover - invoked via list
            return str(value)

        server.register_resource(_res)

    handler = server.request_handlers[types.ListResourcesRequest]
    request = types.ListResourcesRequest(params=types.PaginatedRequestParams(cursor="-10"))
    response = await run_with_context(DummySession("res-negative"), handler, request)

    assert [resource.uri for resource in response.root.resources]  # non-empty
    assert response.root.nextCursor is None


@pytest.mark.anyio
async def test_resources_list_cursor_past_end():
    server = MCPServer("resources-past-end")

    for idx in range(2):
        def make_resource(i: int):
            @resource(f"resource://demo/{i}")
            def _res() -> str:
                return str(i)

            return _res

        server.register_resource(make_resource(idx))

    handler = server.request_handlers[types.ListResourcesRequest]
    request = types.ListResourcesRequest(params=types.PaginatedRequestParams(cursor="500"))
    response = await run_with_context(DummySession("res-past"), handler, request)

    assert response.root.resources == []
    assert response.root.nextCursor is None


@pytest.mark.anyio
async def test_resources_list_changed_notification_enabled():
    server = MCPServer("resources-list-changed", notification_flags=NotificationFlags(resources_changed=True))
    session = DummySession("observer")
    handler = server.request_handlers[types.ListResourcesRequest]

    await run_with_context(session, handler, types.ListResourcesRequest())
    await server.notify_resources_list_changed()

    assert session.notifications
    assert session.notifications[-1].root.method == "notifications/resources/list_changed"


@pytest.mark.anyio
async def test_resources_list_changed_notification_disabled():
    server = MCPServer("resources-list-changed-off")
    session = DummySession("observer-off")
    handler = server.request_handlers[types.ListResourcesRequest]

    await run_with_context(session, handler, types.ListResourcesRequest())
    await server.notify_resources_list_changed()

    assert all(note.root.method != "notifications/resources/list_changed" for note in session.notifications)
