# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Driver protocols for third-party service integrations.

Drivers provide standardized interfaces for creating and managing clients
to external services (databases, APIs, etc.) with proper authentication
and configuration validation.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .http_api import HTTPAPIDriver, HTTPAPIClient


@runtime_checkable
class Driver(Protocol):
    """Protocol for service client drivers.

    A driver encapsulates the logic for creating authenticated clients to
    external services. It validates configuration and credentials, then
    returns a ready-to-use client instance.
    """

    async def create_client(
        self,
        config: dict[str, Any],
        auth: dict[str, Any],
    ) -> Any:
        """Create an authenticated client for the service.

        Args:
            config: Service configuration (e.g., URLs, project IDs)
            auth: Authentication credentials (type + secrets)

        Returns:
            Configured client instance ready for use

        Raises:
            ValueError: Missing or invalid config/auth parameters
            RuntimeError: Client creation or authentication failed
        """
        ...


__all__ = [
    "Driver",
    "HTTPAPIDriver",
    "HTTPAPIClient",
]
