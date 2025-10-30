# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Ping service tests (docs/mcp/spec/schema-reference/ping.md)."""

from __future__ import annotations

import anyio
from mcp.client.session import ClientSession
import pytest

from openmcp import MCPServer, types
from openmcp.server.services.ping import PingService


@pytest.mark.anyio
async def test_ping_service_failure_detector() -> None:
    service = PingService()

    class DummySession:
        async def send_ping(self) -> None:  # pragma: no cover - tests override
            pass

    session = DummySession()
    service.register(session)

    # Baseline: no suspicion, unknown RTT
    assert service.round_trip_time(session) is None
    assert service.suspicion(session) == 0.0
    assert service.is_alive(session)

    history = []

    async def ping_ok(delay: float) -> None:
        original = session.send_ping

        async def _impl():
            await anyio.sleep(delay)

        session.send_ping = _impl
        try:
            assert await service.ping(session, timeout=None)
        finally:
            session.send_ping = original

    await ping_ok(0.01)
    await ping_ok(0.02)
    history.append(service.round_trip_time(session))

    # Inject failures
    async def failing() -> None:
        raise RuntimeError("boom")

    session.send_ping = failing
    assert await service.ping(session, timeout=None) is False
    assert service._state(session).consecutive_failures == 1

    assert await service.ping(session, timeout=None) is False
    assert service._state(session).consecutive_failures == 2
    session.send_ping = failing
    assert await service.ping(session, timeout=None) is False
    assert service._state(session).consecutive_failures == 3

    assert service.is_alive(session, phi_threshold=0.0) is False


@pytest.mark.anyio
async def test_ping_service_ping_many_concurrency() -> None:
    service = PingService()

    active = 0
    peak = 0

    class DummySession:
        def __init__(self, name: str, *, ok: bool) -> None:
            self.name = name
            self.ok = ok
            self.calls = 0

        async def send_ping(self) -> None:
            nonlocal active, peak
            self.calls += 1
            active += 1
            peak = max(peak, active)
            try:
                await anyio.sleep(0.01)
                if not self.ok:
                    raise RuntimeError("fail")
            finally:
                active -= 1

    sessions = [DummySession(str(i), ok=(i % 2 == 0)) for i in range(6)]
    for sess in sessions:
        service.register(sess)

    limit = 2
    results = await service.ping_many(max_concurrency=limit)

    for sess in sessions:
        assert sess.calls == 1
        assert results[sess] is sess.ok
    assert peak == limit


@pytest.mark.anyio
async def test_ping_service_callbacks() -> None:
    suspects: list[tuple[object, float]] = []
    downs: list[object] = []
    suspect_event = anyio.Event()
    down_event = anyio.Event()

    def on_suspect(session, phi):
        suspects.append((session, phi))
        suspect_event.set()

    def on_down(session):
        downs.append(session)
        down_event.set()

    service = PingService(ewma_alpha=1.0, failure_budget=0, on_suspect=on_suspect, on_down=on_down)

    class DummySession:
        def __init__(self) -> None:
            self.ok = True

        async def send_ping(self) -> None:
            if not self.ok:
                raise RuntimeError("fail")

    session = DummySession()
    service.register(session)

    # establish baseline success to populate history
    await service.ping(session)

    session.ok = False

    async with anyio.create_task_group() as tg:
        service.start_heartbeat(tg, interval=0.01, jitter=0.0, timeout=0.01, phi_threshold=0.0, max_concurrency=1)

        with anyio.fail_after(0.5):
            await down_event.wait()
        tg.cancel_scope.cancel()

    assert suspect_event.is_set()
    assert suspects and suspects[-1][0] is session
    assert downs and downs[-1] is session
    assert session not in service.active()


@pytest.mark.anyio
async def test_ping_roundtrip_and_server_initiated_ping() -> None:
    """Clients can ping the server and vice versa using the new helpers."""
    server = MCPServer("ping")
    init_options = server.create_initialization_options()

    client_to_server_send, client_to_server_recv = anyio.create_memory_object_stream(0)
    server_to_client_send, server_to_client_recv = anyio.create_memory_object_stream(0)

    async with anyio.create_task_group() as tg:
        tg.start_soon(server.run, client_to_server_recv, server_to_client_send, init_options, True, False)

        session = ClientSession(
            server_to_client_recv,
            client_to_server_send,
            client_info=types.Implementation(name="ping-client", version="0.0.1"),
        )

        async with session as client_session:
            await client_session.initialize()

            server.start_ping_heartbeat(
                tg, interval=0.05, jitter=0.0, timeout=0.05, phi_threshold=2.0, max_concurrency=1
            )

            for _ in range(10):
                if server.active_sessions():
                    break
                await anyio.sleep(0.01)

            assert server.active_sessions(), "server did not record the session after initialize"

            client_result = await client_session.send_request(
                types.ClientRequest(types.PingRequest()), types.EmptyResult
            )
            assert isinstance(client_result, types.EmptyResult)

            server_session = server.active_sessions()[0]

            await server.ping_client(server_session)
            ping_results = await server.ping_clients(max_concurrency=1)
            assert len(ping_results) == 1
            assert all(ping_results.values())
            assert server.ping.is_alive(server_session)
            assert server.ping.round_trip_time(server_session) is not None

            original_send_ping = server_session.send_ping

            async def failing_ping() -> None:  # pragma: no cover - deterministic in tests
                raise RuntimeError("boom")

            server_session.send_ping = failing_ping
            failure_result = await server.ping_client(server_session)
            assert failure_result is False

            for _ in range(4):
                await anyio.sleep(0.01)
                assert await server.ping_client(server_session) is False

            suspicion = server.ping.suspicion(server_session)
            assert suspicion >= 0.0

            with anyio.fail_after(0.2):
                while server.active_sessions():
                    await anyio.sleep(0.01)

            server_session.send_ping = original_send_ping
            server.ping.register(server_session)
            await server.ping_client(server_session)
            assert server.ping.is_alive(server_session)

        await client_to_server_send.aclose()
        await server_to_client_recv.aclose()
        tg.cancel_scope.cancel()

    await client_to_server_recv.aclose()
    await server_to_client_send.aclose()
