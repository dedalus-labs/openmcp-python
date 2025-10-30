"""High-level client entrypoint.

`open_connection` wraps transport selection and :class:`~openmcp.client.MCPClient`
so applications can talk to an MCP server with a single ``async with`` block.

The helper deliberately keeps the surface tiny: callers choose a transport via
``transport=`` (defaulting to streamable HTTP) and receive an
:class:`~openmcp.client.MCPClient` instance that already negotiated
capabilities.  Power users can still reach the underlying transport by using
the lower-level helpers directly.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import timedelta
from typing import AsyncGenerator, Callable, Mapping

import httpx

from .._sdk_loader import ensure_sdk_importable

ensure_sdk_importable()

from mcp.client.streamable_http import (  # type: ignore  # noqa: E402
    MCP_PROTOCOL_VERSION,
    streamablehttp_client,
)
from mcp.shared._httpx_utils import (  # type: ignore  # noqa: E402
    McpHttpClientFactory,
    create_mcp_http_client,
)
from mcp.types import Implementation, LATEST_PROTOCOL_VERSION  # type: ignore  # noqa: E402

from .app import ClientCapabilitiesConfig, MCPClient
from .transports import lambda_http_client

StreamableHTTPNames = {"streamable-http", "streamable_http", "shttp", "http"}
LambdaHTTPNames = {"lambda-http", "lambda_http"}


@asynccontextmanager
async def open_connection(  # noqa: D401 - docstring inherited by module docs
    target: str,
    *,
    transport: str = "streamable-http",
    headers: Mapping[str, str] | None = None,
    timeout: float | timedelta = 30,
    sse_read_timeout: float | timedelta = 300,
    terminate_on_close: bool = True,
    httpx_client_factory: McpHttpClientFactory | Callable[..., httpx.AsyncClient] = create_mcp_http_client,
    auth: httpx.Auth | None = None,
    capabilities: ClientCapabilitiesConfig | None = None,
    client_info: Implementation | None = None,
    **transport_kwargs,
) -> AsyncGenerator[MCPClient, None]:
    """Open an MCP client connection.

    Parameters
    ----------
    target:
        URL or transport-specific target to connect to.
    transport:
        Name of the transport to use (``"streamable-http"`` by default).  Alias
        spellings like ``"shttp"`` are supported.  ``"lambda-http"`` selects the
        POST-only helper for stateless environments.  All other transports
        raise :class:`ValueError`.
    headers, timeout, sse_read_timeout, terminate_on_close, httpx_client_factory, auth:
        Passed through to the underlying transport factory.
    capabilities, client_info:
        Optional settings forwarded to :class:`~openmcp.client.MCPClient` for
        capability negotiation.
    transport_kwargs:
        Extra keyword arguments forwarded to the underlying transport helper.
    """

    selected = transport.lower()

    if selected in StreamableHTTPNames:
        # The Streamable HTTP handshake requires ``MCP-Protocol-Version`` on
        # every request.  Ensure callers always send the latest version we
        # support while still allowing custom headers to override it.
        base_headers: dict[str, str] = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
        if headers:
            base_headers.update(headers)

        async with streamablehttp_client(
            target,
            headers=base_headers,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
            terminate_on_close=terminate_on_close,
            httpx_client_factory=httpx_client_factory,
            auth=auth,
            **transport_kwargs,
        ) as (read_stream, write_stream, _):
            async with MCPClient(
                read_stream,
                write_stream,
                capabilities=capabilities,
                client_info=client_info,
            ) as client:
                yield client
        return

    if selected in LambdaHTTPNames:
        base_headers = {MCP_PROTOCOL_VERSION: LATEST_PROTOCOL_VERSION}
        if headers:
            base_headers.update(headers)

        async with lambda_http_client(
            target,
            headers=base_headers,
            timeout=timeout,
            sse_read_timeout=sse_read_timeout,
            terminate_on_close=terminate_on_close,
            httpx_client_factory=httpx_client_factory,
            auth=auth,
            **transport_kwargs,
        ) as (read_stream, write_stream, _):
            async with MCPClient(
                read_stream,
                write_stream,
                capabilities=capabilities,
                client_info=client_info,
            ) as client:
                yield client
        return

    raise ValueError(f"Unsupported transport '{transport}'")


__all__ = ["open_connection"]
