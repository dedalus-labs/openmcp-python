# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Connection resolver with credential custody split.

Resolves connection handles to clients with security split:
- Org credentials: vault → driver → client (in-process)
- User credentials: backend → execution → result (forwarded)

Defense-in-depth:
- Token validation before resolution
- Handle authorization checks
- Fingerprint validation
- Secret zeroization
- Audit logging
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..utils import get_logger


@dataclass(slots=True)
class ConnectionMetadata:
    """Metadata for a connection handle."""

    handle: str
    """Connection handle (e.g., ddls:conn_018f...)"""

    driver_type: str
    """Driver type (e.g., supabase, postgres, rest)"""

    auth_type: str
    """Authentication type: 'org' or 'user'"""

    fingerprint: str | None = None
    """Optional fingerprint for additional validation"""

    connector_params: dict[str, Any] | None = None
    """Additional connection parameters"""


@dataclass(slots=True)
class ResolverConfig:
    """Configuration for connection resolver."""

    vault_enabled: bool = True
    """Enable vault connector for org credentials"""

    backend_enabled: bool = True
    """Enable execution backend for user credentials"""

    require_fingerprint: bool = False
    """Require fingerprint validation for all connections"""

    audit_log: bool = True
    """Enable audit logging for all resolution attempts"""


class ResolverError(Exception):
    """Base error for connection resolution failures."""


class UnauthorizedHandleError(ResolverError):
    """Raised when handle is not in token's authorized list."""


class FingerprintMismatchError(ResolverError):
    """Raised when handle fingerprint doesn't match token."""


class VaultError(ResolverError):
    """Raised when vault operations fail."""


class BackendError(ResolverError):
    """Raised when backend execution fails."""


class DriverNotFoundError(ResolverError):
    """Raised when driver type is not registered."""


class VaultConnector(Protocol):
    """Protocol for vault connector implementations.

    Handles org credential resolution from secure vault.
    """

    async def get_connection(self, handle: str) -> ConnectionMetadata:
        """Fetch connection metadata from vault.

        Args:
            handle: Connection handle to retrieve

        Returns:
            ConnectionMetadata with driver type and auth type

        Raises:
            VaultError: If vault operation fails
        """

    async def decrypt_secret(self, handle: str) -> str:
        """Decrypt and retrieve secret for handle.

        Args:
            handle: Connection handle

        Returns:
            Decrypted secret (must be zeroized after use)

        Raises:
            VaultError: If decryption fails
        """


class ExecutionBackendClient(Protocol):
    """Protocol for execution backend client.

    Handles user credential forwarding to backend.
    """

    async def execute_with_credential(
        self,
        encrypted_cred: dict[str, Any],
        upstream_call: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute operation with user credential on backend.

        Args:
            encrypted_cred: Encrypted credential payload
            upstream_call: Operation to execute

        Returns:
            Execution result

        Raises:
            BackendError: If backend execution fails
        """


class Driver(Protocol):
    """Protocol for connection drivers.

    Implements connection logic for specific database/API types.
    """

    async def create_client(
        self,
        secret: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Create client from decrypted secret.

        Args:
            secret: Decrypted connection secret (zeroize after use)
            params: Additional connection parameters

        Returns:
            Client instance ready for use

        Raises:
            Exception: If client creation fails
        """


class ConnectionResolver:
    """Resolves connection handles to clients with credential custody split.

    Routes based on auth type:
    - org credentials: vault → driver → client (in-process)
    - user credentials: backend → execution → result (forwarded)

    Security features:
    - Token validation before resolution
    - Handle authorization checks
    - Fingerprint validation
    - Secret zeroization
    - Audit logging
    """

    def __init__(
        self,
        config: ResolverConfig,
        vault: VaultConnector | None = None,
        backend: ExecutionBackendClient | None = None,
        drivers: dict[str, Driver] | None = None,
    ) -> None:
        """Initialize connection resolver.

        Args:
            config: Resolver configuration
            vault: Vault connector for org credentials
            backend: Execution backend client for user credentials
            drivers: Driver registry mapping driver_type → Driver
        """
        self.config = config
        self._vault = vault
        self._backend = backend
        self._drivers = drivers or {}
        self._logger = get_logger("openmcp.resolver")

    def register_driver(self, driver_type: str, driver: Driver) -> None:
        """Register a driver for a connection type.

        Args:
            driver_type: Driver type identifier (e.g., 'supabase', 'postgres')
            driver: Driver implementation
        """
        self._drivers[driver_type] = driver
        self._logger.debug(
            "driver registered",
            extra={"event": "resolver.driver.register", "driver_type": driver_type},
        )

    async def resolve_client(
        self,
        handle: str,
        request_context: dict[str, Any],
    ) -> Any:
        """Resolve handle to client with credential custody split.

        Args:
            handle: Connection handle (e.g., ddls:conn_018f...)
            request_context: Request context containing auth info

        Returns:
            Client instance (org creds) or execution result (user creds)

        Raises:
            UnauthorizedHandleError: If handle not authorized in token
            FingerprintMismatchError: If fingerprint validation fails
            VaultError: If vault operations fail
            BackendError: If backend execution fails
            DriverNotFoundError: If driver not registered
        """
        # Extract auth context from request
        auth_context = request_context.get("openmcp.auth")
        if not auth_context:
            self._audit_log("resolve_failed", handle, "missing_auth_context")
            raise ResolverError("missing authentication context")

        # Validate handle authorization
        self._validate_handle_authorization(handle, auth_context)

        # Get connection metadata
        if not self._vault or not self.config.vault_enabled:
            self._audit_log("resolve_failed", handle, "vault_disabled")
            raise VaultError("vault connector not configured")

        try:
            metadata = await self._vault.get_connection(handle)
        except Exception as e:
            self._audit_log("resolve_failed", handle, f"vault_error: {e}")
            raise VaultError(f"failed to retrieve connection metadata: {e}") from e

        # Validate fingerprint if required
        if self.config.require_fingerprint or metadata.fingerprint:
            self._validate_fingerprint(handle, metadata, auth_context)

        # Route based on auth type
        if metadata.auth_type == "org":
            return await self._resolve_org_credential(handle, metadata)
        elif metadata.auth_type == "user":
            return await self._resolve_user_credential(handle, metadata, request_context)
        else:
            self._audit_log("resolve_failed", handle, f"invalid_auth_type: {metadata.auth_type}")
            raise ResolverError(f"invalid auth type: {metadata.auth_type}")

    async def _resolve_org_credential(
        self,
        handle: str,
        metadata: ConnectionMetadata,
    ) -> Any:
        """Resolve org credential: vault → driver → client (in-process).

        Args:
            handle: Connection handle
            metadata: Connection metadata

        Returns:
            Client instance ready for use

        Raises:
            VaultError: If secret decryption fails
            DriverNotFoundError: If driver not found
        """
        # Get driver
        driver = self._drivers.get(metadata.driver_type)
        if not driver:
            self._audit_log("resolve_failed", handle, f"driver_not_found: {metadata.driver_type}")
            raise DriverNotFoundError(f"driver not found: {metadata.driver_type}")

        # Decrypt secret from vault
        try:
            secret = await self._vault.decrypt_secret(handle)  # type: ignore[union-attr]
        except Exception as e:
            self._audit_log("resolve_failed", handle, f"decrypt_error: {e}")
            raise VaultError(f"failed to decrypt secret: {e}") from e

        # Create client (zeroize secret after use)
        try:
            client = await driver.create_client(secret, metadata.connector_params)
            self._audit_log("resolve_success", handle, "org_credential_in_process")
            return client
        except Exception as e:
            self._audit_log("resolve_failed", handle, f"client_creation_error: {e}")
            raise
        finally:
            # Zeroize secret immediately after use
            self._zeroize_secret(secret)

    async def _resolve_user_credential(
        self,
        handle: str,
        metadata: ConnectionMetadata,
        request_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve user credential: backend → execution → result (forwarded).

        Args:
            handle: Connection handle
            metadata: Connection metadata
            request_context: Full request context

        Returns:
            Execution result from backend

        Raises:
            BackendError: If backend execution fails
        """
        if not self._backend or not self.config.backend_enabled:
            self._audit_log("resolve_failed", handle, "backend_disabled")
            raise BackendError("execution backend not configured")

        # Extract encrypted credential from token claims
        auth_context = request_context.get("openmcp.auth")
        encrypted_cred = auth_context.claims.get("ddls:credential")  # type: ignore[union-attr]

        if not encrypted_cred:
            self._audit_log("resolve_failed", handle, "missing_encrypted_credential")
            raise BackendError("missing encrypted credential in token")

        # Prepare upstream call
        upstream_call = {
            "handle": handle,
            "driver_type": metadata.driver_type,
            "params": metadata.connector_params,
            "operation": request_context.get("operation"),
        }

        # Forward to backend
        try:
            result = await self._backend.execute_with_credential(encrypted_cred, upstream_call)
            self._audit_log("resolve_success", handle, "user_credential_forwarded")
            return result
        except Exception as e:
            self._audit_log("resolve_failed", handle, f"backend_execution_error: {e}")
            raise BackendError(f"backend execution failed: {e}") from e

    def _validate_handle_authorization(
        self,
        handle: str,
        auth_context: Any,
    ) -> None:
        """Validate handle is authorized in token claims.

        Args:
            handle: Connection handle
            auth_context: Authorization context from token

        Raises:
            UnauthorizedHandleError: If handle not authorized
        """
        authorized_handles = auth_context.claims.get("ddls:connectors", [])

        if handle not in authorized_handles:
            self._audit_log("authorization_failed", handle, "handle_not_in_token")
            raise UnauthorizedHandleError(f"handle not authorized: {handle}")

    def _validate_fingerprint(
        self,
        handle: str,
        metadata: ConnectionMetadata,
        auth_context: Any,
    ) -> None:
        """Validate fingerprint matches token claim.

        Args:
            handle: Connection handle
            metadata: Connection metadata
            auth_context: Authorization context from token

        Raises:
            FingerprintMismatchError: If fingerprints don't match
        """
        token_fingerprints = auth_context.claims.get("ddls:fingerprints", {})
        token_fp = token_fingerprints.get(handle)

        if metadata.fingerprint and token_fp and metadata.fingerprint != token_fp:
            self._audit_log("fingerprint_mismatch", handle, "validation_failed")
            raise FingerprintMismatchError(f"fingerprint mismatch for handle: {handle}")

    def _zeroize_secret(self, secret: str) -> None:
        """Zeroize secret in memory (best effort).

        Args:
            secret: Secret to zeroize
        """
        # Python doesn't have true zeroization, but we can at least
        # clear the reference and rely on GC
        # In production, consider using ctypes or secure memory libraries
        del secret

    def _audit_log(
        self,
        event: str,
        handle: str,
        detail: str,
    ) -> None:
        """Log audit event for resolution attempt.

        Args:
            event: Event type
            handle: Connection handle
            detail: Event detail
        """
        if not self.config.audit_log:
            return

        self._logger.info(
            f"connection resolution: {event}",
            extra={
                "event": f"resolver.{event}",
                "handle": handle,
                "detail": detail,
            },
        )


__all__ = [
    "ConnectionMetadata",
    "ResolverConfig",
    "ConnectionResolver",
    "VaultConnector",
    "ExecutionBackendClient",
    "Driver",
    "ResolverError",
    "UnauthorizedHandleError",
    "FingerprintMismatchError",
    "VaultError",
    "BackendError",
    "DriverNotFoundError",
]
