# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Generic HTTP API driver helpers.

This driver is intentionally provider-agnostic. It turns a connector handle and
secret payload (e.g., service credential or user token) into a light-weight
client that knows how to attach authorization headers for outbound requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .base import BaseDriver


@dataclass(slots=True)
class HTTPAPIClient:
    """Minimal HTTP client wrapper that decorates requests with auth headers."""

    base_url: str
    auth_type: str
    header_name: str
    token_prefix: str
    _secret: str

    def build_headers(self) -> dict[str, str]:
        """Return headers representing the configured authorization secret."""
        value = f"{self.token_prefix}{self._secret}" if self.token_prefix else self._secret
        return {self.header_name: value}

    def as_dict(self) -> dict[str, Any]:
        """Return a sanitized representation without leaking the secret."""
        return {
            "base_url": self.base_url,
            "auth_type": self.auth_type,
            "header_name": self.header_name,
            "token_prefix": self.token_prefix,
        }


class HTTPAPIDriver(BaseDriver):
    """Driver that produces :class:`HTTPAPIClient` instances."""

    SUPPORTED_AUTH_TYPES = ["service_credential", "user_token"]

    def __init__(
        self,
        *,
        header_name: str = "Authorization",
        prefixes: dict[str, str] | None = None,
    ) -> None:
        self._header_name = header_name
        self._prefixes = prefixes or {
            "service_credential": "Bearer ",
            "user_token": "Bearer ",
        }

    async def create_client(
        self,
        config: Any,
        auth: Any,
    ) -> HTTPAPIClient:
        """Create a driver-specific client for HTTP APIs."""

        config_data = self._normalize_input(config)
        auth_data = self._normalize_input(auth)

        self._validate_required_config(config_data, ["base_url"])
        self._validate_auth_type(auth_data, self.SUPPORTED_AUTH_TYPES)
        secret = self._get_required_auth_field(auth_data, "secret")

        prefix = self._prefixes.get(auth_data["type"], "")

        return HTTPAPIClient(
            base_url=config_data["base_url"],
            auth_type=auth_data["type"],
            header_name=self._header_name,
            token_prefix=prefix,
            _secret=secret,
        )


__all__ = ["HTTPAPIClient", "HTTPAPIDriver"]
