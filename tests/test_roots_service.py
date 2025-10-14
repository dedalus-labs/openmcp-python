from __future__ import annotations

import gc
import weakref
from pathlib import Path
from typing import Any, Mapping

import anyio
import pytest

from openmcp import types
from openmcp.server import MCPServer
from openmcp.server.services.roots import RootGuard, RootsService
from mcp.shared.exceptions import McpError
from tests.helpers import run_with_context


class SessionStub:
    """Weak-reference friendly session stand-in."""

    pass


class FakeRootsRPC:
    def __init__(self, pages: list[Mapping[str, Any]]) -> None:
        self._pages = pages
        self.calls: list[Mapping[str, Any] | None] = []

    async def __call__(self, _session: SessionStub, params: Mapping[str, Any] | None) -> Mapping[str, Any]:
        self.calls.append(params or {})
        if not self._pages:
            return {"roots": []}
        page = self._pages.pop(0)
        # Return a shallow copy so tests can mutate `_pages` safely.
        return {key: value for key, value in page.items()}


@pytest.mark.anyio
async def test_refresh_and_guard_allows_within(tmp_path: Path) -> None:
    root_uri = tmp_path.as_uri()
    rpc = FakeRootsRPC([
        {"roots": [types.Root(uri=root_uri).model_dump(by_alias=True)]},
    ])
    service = RootsService(rpc, debounce_delay=0.0)
    session = SessionStub()

    await service.on_session_open(session)
    snapshot = service.snapshot(session)
    assert len(snapshot) == 1
    assert str(snapshot[0].uri) == root_uri

    guard = service.guard(session)
    assert isinstance(guard, RootGuard)
    assert guard.within(tmp_path / "inside.txt")
    assert guard.within(f"file://{tmp_path}/inside.txt")
    assert not guard.within(tmp_path.parent / "outside.txt")

    rpc._pages = [
        {"roots": [types.Root(uri=root_uri).model_dump(by_alias=True)]},
    ]
    await service.on_list_changed(session)
    await anyio.sleep(0)
    snapshot = service.snapshot(session)
    assert len(snapshot) == 1
    assert str(snapshot[0].uri) == root_uri


@pytest.mark.anyio
async def test_remove_clears_cache(tmp_path: Path) -> None:
    rpc = FakeRootsRPC([
        {"roots": [types.Root(uri=tmp_path.as_uri()).model_dump(by_alias=True)]},
    ])
    service = RootsService(rpc, debounce_delay=0.0)
    session = SessionStub()

    await service.on_session_open(session)
    assert service.snapshot(session)
    service.remove(session)
    assert service.snapshot(session) == ()
    assert not service.guard(session).within(tmp_path)


@pytest.mark.anyio
async def test_pagination_and_versioning(tmp_path: Path) -> None:
    page_one = {"roots": [types.Root(uri=(tmp_path / "a").as_uri()).model_dump(by_alias=True)], "nextCursor": "abc"}
    page_two = {"roots": [types.Root(uri=(tmp_path / "b").as_uri()).model_dump(by_alias=True)]}
    rpc = FakeRootsRPC([page_one, page_two])
    service = RootsService(rpc, debounce_delay=0.0)
    session = SessionStub()

    await service.on_session_open(session)
    snapshot = service.snapshot(session)
    assert {str(root.uri) for root in snapshot} == {
        (tmp_path / "a").as_uri(),
        (tmp_path / "b").as_uri(),
    }
    assert service.version(session) == 1

    cursor = service.encode_cursor(session, offset=1)
    version, offset = service.decode_cursor(session, cursor)
    assert version == 1
    assert offset == 1

    # Trigger a change so the version increments.
    rpc._pages = [
        {"roots": [types.Root(uri=(tmp_path / "c").as_uri()).model_dump(by_alias=True)]},
    ]
    await service.refresh(session)
    assert service.version(session) == 2
    with pytest.raises(McpError):
        service.decode_cursor(session, cursor)


@pytest.mark.anyio
async def test_symlink_outside_denied(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside.txt"
    outside.write_text("secret")
    link_dir = tmp_path / "link"
    link_dir.mkdir()
    try:
        (link_dir / "escape").symlink_to(outside)
    except OSError as exc:  # pragma: no cover - platform without symlink support
        pytest.skip(f"symlinks unsupported: {exc}")

    rpc = FakeRootsRPC([
        {"roots": [types.Root(uri=tmp_path.as_uri()).model_dump(by_alias=True)]},
    ])
    service = RootsService(rpc, debounce_delay=0.0)
    session = SessionStub()
    await service.on_session_open(session)

    guard = service.guard(session)
    assert not guard.within(link_dir / "escape")


@pytest.mark.anyio
async def test_debounce_coalesces_requests(tmp_path: Path) -> None:
    rpc = FakeRootsRPC([
        {"roots": [types.Root(uri=tmp_path.as_uri()).model_dump(by_alias=True)]},
    ])
    service = RootsService(rpc, debounce_delay=0.05)
    session = SessionStub()

    await service.on_session_open(session)
    initial_calls = len(rpc.calls)

    await service.on_list_changed(session)
    await service.on_list_changed(session)
    await anyio.sleep(0.1)

    assert len(rpc.calls) == initial_calls + 1


@pytest.mark.anyio
async def test_weakref_cleanup_allows_gc(tmp_path: Path) -> None:
    rpc = FakeRootsRPC([
        {"roots": [types.Root(uri=tmp_path.as_uri()).model_dump(by_alias=True)]},
    ])
    service = RootsService(rpc, debounce_delay=0.0)
    session = SessionStub()

    await service.on_session_open(session)
    assert len(service._entries) == 1  # type: ignore[attr-defined]

    weak = weakref.ref(session)
    del session
    gc.collect()

    assert weak() is None
    assert len(service._entries) == 0  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_server_integration_uses_roots_service(tmp_path: Path) -> None:
    class FakeSession:
        def __init__(self, roots: list[types.Root]) -> None:
            self._roots = roots

        async def send_request(self, request, result_type):
            assert isinstance(request.root, types.ListRootsRequest)
            return types.ListRootsResult(roots=self._roots)

    server = MCPServer("roots-int-test")
    fake_session = FakeSession([types.Root(uri=tmp_path.as_uri())])

    await server.roots.on_session_open(fake_session)
    guard = server.roots.guard(fake_session)
    assert guard.within(tmp_path / "allowed.txt")
    await server.roots.on_list_changed(fake_session)
    await anyio.sleep(0.01)

    server.roots.remove(fake_session)
    assert server.roots.snapshot(fake_session) == ()


@pytest.mark.anyio
async def test_require_within_roots_decorator_enforces_guard(tmp_path: Path) -> None:
    class FakeSession:
        def __init__(self, roots: list[types.Root]) -> None:
            self._roots = roots

        async def send_request(self, request, result_type):
            assert isinstance(request.root, types.ListRootsRequest)
            return types.ListRootsResult(roots=self._roots)

    server = MCPServer("guard-decorator")
    fake_session = FakeSession([types.Root(uri=tmp_path.as_uri())])
    await server.roots.on_session_open(fake_session)

    @server.require_within_roots(argument="path")
    async def protected(*, path: str) -> str:
        return "ok"

    async def _call_allowed() -> str:
        return await protected(path=str(tmp_path / "allowed.txt"))

    allowed = await run_with_context(fake_session, _call_allowed)
    assert allowed == "ok"

    with pytest.raises(McpError):
        await run_with_context(fake_session, lambda: protected(path=str(tmp_path.parent / "outside.txt")))


@pytest.mark.anyio
async def test_initialized_notification_triggers_refresh(tmp_path: Path) -> None:
    class FakeSession:
        def __init__(self, roots: list[types.Root]) -> None:
            self._roots = roots

        async def send_request(self, request, result_type):
            assert isinstance(request.root, types.ListRootsRequest)
            return types.ListRootsResult(roots=self._roots)

    server = MCPServer("initialized")
    fake_session = FakeSession([types.Root(uri=tmp_path.as_uri())])

    async def invoke_handler() -> None:
        await server._handle_initialized(types.InitializedNotification(params=None))

    await run_with_context(fake_session, invoke_handler)
    snapshot = server.roots.snapshot(fake_session)
    assert snapshot
