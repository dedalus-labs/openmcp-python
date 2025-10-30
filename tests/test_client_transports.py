# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations


"""Targeted transport regression tests.

These tests deliberately patch the reference SDK transport to surface the
persistent GET/SSE stream behavior that breaks on AWS Lambda.  ``lambda_http_client``
must avoid triggering that code path, while the vanilla
``streamablehttp_client`` should continue to expose it so we can catch any
accidental regression.
"""

from contextlib import asynccontextmanager
from typing import Any

import anyio
import anyio.abc
import pytest

from openmcp._sdk_loader import ensure_sdk_importable
from openmcp.client.transports import lambda_http_client


ensure_sdk_importable()

from mcp.client.streamable_http import streamablehttp_client


class SentinelError(RuntimeError):
    """Raised when the upstream transport attempts to start the GET stream."""


class FakeTransport:
    """Test double mirroring the SDK transport interface without real I/O."""

    def __init__(
        self, url: str, headers: dict[str, str] | None, timeout: float, sse_read_timeout: float, auth: Any
    ) -> None:
        self.url = url
        self.request_headers = headers or {}
        self.timeout = timeout
        self.sse_read_timeout = sse_read_timeout
        self.auth = auth
        self.session_id = "fake-session"
        self.start_get_stream = None
        self.terminated = False
        self.post_calls = 0

    def get_session_id(self) -> str:
        return self.session_id

    async def terminate_session(self, _client: Any) -> None:
        self.terminated = True

    async def post_writer(
        self,
        _client: Any,
        _write_reader: Any,
        _read_writer: Any,
        _write_stream: Any,
        start_get_stream: Any,
        _tg: anyio.abc.TaskGroup,
    ) -> None:
        self.post_calls += 1
        self.start_get_stream = start_get_stream
        try:
            await anyio.sleep_forever()
        except BaseException:  # pragma: no cover - cancellation path
            pass


@pytest.mark.anyio
async def test_lambda_http_client_injects_noop_get_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Our wrapper must *not* invoke the GET/SSE starter the SDK normally uses."""
    transport_instances: list[FakeTransport] = []

    def transport_factory(
        url: str, headers: dict[str, str] | None, timeout: float, sse_timeout: float, auth: Any
    ) -> FakeTransport:
        inst = FakeTransport(url, headers, timeout, sse_timeout, auth)
        transport_instances.append(inst)
        return inst

    @asynccontextmanager
    async def fake_client_factory(**_: Any):
        yield object()

    monkeypatch.setattr("openmcp.client.transports.StreamableHTTPTransport", transport_factory)
    monkeypatch.setattr("openmcp.client.transports.create_mcp_http_client", fake_client_factory)

    async with lambda_http_client("https://lambda.example.test/mcp") as (read, write, get_session_id):
        assert transport_instances, "transport should be created"
        transport = transport_instances[0]

        await anyio.sleep(0)  # allow post_writer to start
        assert transport.post_calls == 1
        assert transport.start_get_stream is not None
        assert transport.start_get_stream.__name__ == "_noop_start_get_stream"
        assert get_session_id() == "fake-session"

        await write.aclose()
        await read.aclose()

    assert transport_instances[0].terminated is True


@pytest.mark.anyio
async def test_streamablehttp_client_raises_when_get_stream_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: stock streamable client still tries to attach SSE."""

    class RaisingTransport(FakeTransport):
        """Record the SDK behavior: register GET stream and let it raise."""

        async def handle_get_stream(self, *_: Any) -> None:
            raise SentinelError("GET stream started")

        async def post_writer(
            self,
            client: Any,
            write_reader: Any,
            read_writer: Any,
            write_stream: Any,
            start_get_stream: Any,
            tg: anyio.abc.TaskGroup,
        ) -> None:
            if start_get_stream is not None:
                start_get_stream()
            try:
                await anyio.sleep_forever()
            except BaseException:  # pragma: no cover - cancelled by sentinel
                pass

    def transport_factory(
        url: str, headers: dict[str, str] | None, timeout: float, sse_timeout: float, auth: Any
    ) -> RaisingTransport:
        return RaisingTransport(url, headers, timeout, sse_timeout, auth)

    @asynccontextmanager
    async def fake_client_factory(**_: Any):
        yield object()

    monkeypatch.setattr("mcp.client.streamable_http.StreamableHTTPTransport", transport_factory)
    monkeypatch.setattr("mcp.client.streamable_http.create_mcp_http_client", fake_client_factory)

    with pytest.raises(BaseExceptionGroup) as excinfo:
        async with streamablehttp_client(url="https://lambda.example.test/mcp"):
            pass

    def _flatten(exc: BaseException | BaseExceptionGroup):
        if isinstance(exc, BaseExceptionGroup):
            for inner in exc.exceptions:
                yield from _flatten(inner)
        else:
            yield exc

    assert all(isinstance(err, SentinelError) for err in _flatten(excinfo.value))
