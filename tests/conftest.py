import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest


@pytest.fixture
def event_loop():  # type: ignore[misc]
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def httpx_async_client(anyio_backend_name):
    async def factory(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client

    return factory
