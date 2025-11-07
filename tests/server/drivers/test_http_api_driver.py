# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for provider-agnostic HTTP API driver."""

from __future__ import annotations

import pytest

from pydantic import BaseModel

from openmcp.server.connectors import (
    EnvironmentCredentialLoader,
    EnvironmentCredentials,
    EnvironmentBindings,
    define,
)
from openmcp.server.drivers.http_api import HTTPAPIClient, HTTPAPIDriver


class HTTPAPIConfig(BaseModel):
    base_url: str


class HTTPAPIAuth(BaseModel):
    type: str
    secret: str


@pytest.fixture
def driver() -> HTTPAPIDriver:
    """Instantiate the driver with default options."""

    return HTTPAPIDriver()


class TestHTTPAPIDriver:
    """Behavioral tests for HTTPAPIDriver."""

    @pytest.mark.asyncio
    async def test_create_client_with_service_credential(self, driver: HTTPAPIDriver) -> None:
        config = HTTPAPIConfig(base_url="https://api.example.com")
        auth = HTTPAPIAuth(type="service_credential", secret="service-key")

        client = await driver.create_client(config, auth)

        assert isinstance(client, HTTPAPIClient)
        assert client.base_url == "https://api.example.com"
        assert client.auth_type == "service_credential"
        assert client.build_headers() == {"Authorization": "Bearer service-key"}

    @pytest.mark.asyncio
    async def test_create_client_with_user_token(self, driver: HTTPAPIDriver) -> None:
        config = HTTPAPIConfig(base_url="https://api.example.com")
        auth = HTTPAPIAuth(type="user_token", secret="user-token")

        client = await driver.create_client(config, auth)

        assert client.auth_type == "user_token"
        assert client.build_headers() == {"Authorization": "Bearer user-token"}

    @pytest.mark.asyncio
    async def test_custom_prefixes(self) -> None:
        driver = HTTPAPIDriver(prefixes={"service_credential": "Token "})

        client = await driver.create_client(
            HTTPAPIConfig(base_url="https://api"),
            HTTPAPIAuth(type="service_credential", secret="abc"),
        )

        assert client.build_headers() == {"Authorization": "Token abc"}

    @pytest.mark.asyncio
    async def test_missing_base_url_raises(self, driver: HTTPAPIDriver) -> None:
        with pytest.raises(ValueError, match="Missing required config parameter"):
            await driver.create_client({}, {"type": "service_credential", "secret": "abc"})

    @pytest.mark.asyncio
    async def test_unsupported_auth_type_raises(self, driver: HTTPAPIDriver) -> None:
        with pytest.raises(ValueError, match="Unsupported auth type"):
            await driver.create_client(
                {"base_url": "https://api"},
                {"type": "invalid", "secret": "abc"},
            )

    @pytest.mark.asyncio
    async def test_missing_secret_raises(self, driver: HTTPAPIDriver) -> None:
        with pytest.raises(ValueError, match="Missing required auth field: secret"):
            await driver.create_client(
                {"base_url": "https://api"},
                {"type": "service_credential"},
            )

    @pytest.mark.asyncio
    async def test_build_client_from_resolved_connector(self, driver: HTTPAPIDriver, monkeypatch: pytest.MonkeyPatch) -> None:
        connector = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        loader = EnvironmentCredentialLoader(
            connector,
            variants={
                "service_credential": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_API_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_SERVICE_KEY"),
                )
            },
        )

        monkeypatch.setenv("GENERIC_API_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("GENERIC_SERVICE_KEY", "svc-456")

        resolved = loader.load("service_credential")
        client = await resolved.build_client(driver)

        assert client.base_url == "https://api.example.com"
        assert client.auth_type == "service_credential"
        assert client.build_headers()["Authorization"].endswith("svc-456")
