# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""HTTP transport helpers for :mod:`openmcp.client`.

This module provides variants of the streamable HTTP transport described in the
Model Context Protocol specification (see
``docs/mcp/core/transports/streamable-http.md``).  ``lambda_http_client`` mirrors
the reference SDK implementation but deliberately avoids registering a
server-push GET stream so that it works with stateless environments such as AWS
Lambda.  The behavior aligns with the "POST-only" pattern noted in the spec's
server guidance and our notes in ``docs/openmcp/transports.md``.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import timedelta

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
import httpx

from .._sdk_loader import ensure_sdk_importable


ensure_sdk_importable()

from mcp.client.streamable_http import (  # type: ignore  # noqa: E402
    GetSessionIdCallback,
    StreamableHTTPTransport,
)
from mcp.shared._httpx_utils import (  # type: ignore  # noqa: E402
    McpHttpClientFactory,
    create_mcp_http_client,
)
from mcp.shared.message import SessionMessage  # type: ignore  # noqa: E402


@asynccontextmanager
async def lambda_http_client(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 300,
    terminate_on_close: bool = True,
    httpx_client_factory: McpHttpClientFactory | Callable[..., httpx.AsyncClient] = create_mcp_http_client,
    auth: httpx.Auth | None = None,
) -> AsyncGenerator[
    tuple[
        MemoryObjectReceiveStream[SessionMessage | Exception],
        MemoryObjectSendStream[SessionMessage],
        GetSessionIdCallback,
    ],
    None,
]:
    """Create a streamable HTTP transport without the persistent GET stream.

    The Model Context Protocol allows streamable HTTP transports to keep a
    server-push channel open (``docs/mcp/core/transports/streamable-http.md``),
    but serverless hosts like AWS Lambda cannot maintain such long-lived
    connections.  ``lambda_http_client`` mirrors the reference SDK's
    ``streamablehttp_client`` implementation while replacing the
    ``start_get_stream`` callback with a no-op.  This keeps each JSON-RPC request
    self-contained (``initialize`` → operation → optional ``session/close``) and
    matches the stateless guidance in ``docs/openmcp/transports.md``.

    Yields:
        Tuple of ``(read_stream, write_stream, get_session_id)`` compatible with
        :class:`mcp.client.session.ClientSession`.
    """
    transport = StreamableHTTPTransport(url, headers, timeout, sse_read_timeout, auth)

    read_writer, read_stream = anyio.create_memory_object_stream[SessionMessage | Exception](0)
    write_stream, write_reader = anyio.create_memory_object_stream[SessionMessage](0)

    async with anyio.create_task_group() as tg:
        try:
            async with httpx_client_factory(
                headers=transport.request_headers,
                timeout=httpx.Timeout(transport.timeout, read=transport.sse_read_timeout),
                auth=transport.auth,
            ) as client:

                def _noop_start_get_stream() -> None:
                    """Lambda-safe placeholder that intentionally avoids SSE."""

                tg.start_soon(
                    transport.post_writer, client, write_reader, read_writer, write_stream, _noop_start_get_stream, tg
                )

                try:
                    yield read_stream, write_stream, transport.get_session_id
                finally:
                    if transport.session_id and terminate_on_close:
                        await transport.terminate_session(client)
                    tg.cancel_scope.cancel()
        finally:
            await read_writer.aclose()
            await write_stream.aclose()
