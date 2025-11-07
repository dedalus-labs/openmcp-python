# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for connection resolver with credential custody split."""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from openmcp.server.authorization import AuthorizationContext
from openmcp.server.resolver import (
    BackendError,
    ConnectionMetadata,
    ConnectionResolver,
    DriverNotFoundError,
    FingerprintMismatchError,
    ResolverConfig,
    ResolverError,
    UnauthorizedHandleError,
    VaultError,
)


# =============================================================================
# Test Fixtures
# =============================================================================


class MockVaultConnector:
    """Mock vault connector for testing."""

    def __init__(self) -> None:
        self.connections: dict[str, ConnectionMetadata] = {}
        self.secrets: dict[str, str] = {}

    async def get_connection(self, handle: str) -> ConnectionMetadata:
        """Fetch connection metadata."""
        if handle not in self.connections:
            raise VaultError(f"connection not found: {handle}")
        return self.connections[handle]

    async def decrypt_secret(self, handle: str) -> str:
        """Decrypt secret."""
        if handle not in self.secrets:
            raise VaultError(f"secret not found: {handle}")
        return self.secrets[handle]

    def add_connection(
        self,
        handle: str,
        driver_type: str,
        auth_type: str,
        secret: str,
        fingerprint: str | None = None,
    ) -> None:
        """Helper to add test connection."""
        self.connections[handle] = ConnectionMetadata(
            handle=handle,
            driver_type=driver_type,
            auth_type=auth_type,
            fingerprint=fingerprint,
            connector_params={"test": "param"},
        )
        self.secrets[handle] = secret


class MockExecutionBackend:
    """Mock execution backend for testing."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute_with_credential(
        self,
        encrypted_cred: dict[str, Any],
        upstream_call: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute with credential."""
        self.calls.append({"cred": encrypted_cred, "call": upstream_call})
        return {"result": "success", "data": "test_data"}


class MockDriver:
    """Mock driver for testing."""

    def __init__(self) -> None:
        self.created_clients: list[tuple[str, dict[str, Any] | None]] = []

    async def create_client(
        self,
        secret: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Create client."""
        self.created_clients.append((secret, params))
        return Mock(spec=["query", "close"])


@pytest.fixture
def mock_vault() -> MockVaultConnector:
    """Create mock vault connector."""
    return MockVaultConnector()


@pytest.fixture
def mock_backend() -> MockExecutionBackend:
    """Create mock execution backend."""
    return MockExecutionBackend()


@pytest.fixture
def mock_driver() -> MockDriver:
    """Create mock driver."""
    return MockDriver()


@pytest.fixture
def resolver_config() -> ResolverConfig:
    """Create resolver config."""
    return ResolverConfig(
        vault_enabled=True,
        backend_enabled=True,
        require_fingerprint=False,
        audit_log=True,
    )


@pytest.fixture
def auth_context() -> AuthorizationContext:
    """Create auth context with authorized handles."""
    return AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_org", "ddls:conn_user"],
            "ddls:fingerprints": {
                "ddls:conn_org": "fp_org_123",
                "ddls:conn_user": "fp_user_456",
            },
            "ddls:credential": {"encrypted": "user_cred_data"},
        },
    )


# =============================================================================
# Org Credential Resolution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_resolve_org_credential_success(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
) -> None:
    """Test successful org credential resolution path."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_org",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute
    client = await resolver.resolve_client("ddls:conn_org", request_context)

    # Verify
    assert client is not None
    assert len(mock_driver.created_clients) == 1
    secret, params = mock_driver.created_clients[0]
    assert secret == "postgres://user:pass@host/db"
    assert params == {"test": "param"}


@pytest.mark.asyncio
async def test_resolve_org_credential_with_fingerprint_validation(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
) -> None:
    """Test org credential resolution with fingerprint validation."""
    # Setup with fingerprint requirement
    resolver_config.require_fingerprint = True
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_org",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
        fingerprint="fp_org_123",
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute
    client = await resolver.resolve_client("ddls:conn_org", request_context)

    # Verify
    assert client is not None


@pytest.mark.asyncio
async def test_resolve_org_credential_fingerprint_mismatch(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
) -> None:
    """Test fingerprint mismatch rejection."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_org",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
        fingerprint="fp_wrong_999",  # Wrong fingerprint
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(FingerprintMismatchError, match="fingerprint mismatch"):
        await resolver.resolve_client("ddls:conn_org", request_context)


@pytest.mark.asyncio
async def test_resolve_org_credential_driver_not_found(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    auth_context: AuthorizationContext,
) -> None:
    """Test error when driver not registered."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    # Don't register any driver

    mock_vault.add_connection(
        handle="ddls:conn_org",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(DriverNotFoundError, match="driver not found"):
        await resolver.resolve_client("ddls:conn_org", request_context)


# =============================================================================
# User Credential Resolution Tests
# =============================================================================


@pytest.mark.asyncio
async def test_resolve_user_credential_success(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_backend: MockExecutionBackend,
    auth_context: AuthorizationContext,
) -> None:
    """Test successful user credential forwarding path."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault, backend=mock_backend)

    mock_vault.add_connection(
        handle="ddls:conn_user",
        driver_type="supabase",
        auth_type="user",
        secret="",  # Not used for user creds
    )

    request_context = {
        "openmcp.auth": auth_context,
        "operation": {"type": "query", "sql": "SELECT * FROM users"},
    }

    # Execute
    result = await resolver.resolve_client("ddls:conn_user", request_context)

    # Verify
    assert result == {"result": "success", "data": "test_data"}
    assert len(mock_backend.calls) == 1
    call = mock_backend.calls[0]
    assert call["cred"] == {"encrypted": "user_cred_data"}
    assert call["call"]["handle"] == "ddls:conn_user"
    assert call["call"]["driver_type"] == "supabase"


@pytest.mark.asyncio
async def test_resolve_user_credential_backend_disabled(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    auth_context: AuthorizationContext,
) -> None:
    """Test error when backend disabled."""
    # Setup with backend disabled
    resolver_config.backend_enabled = False
    resolver = ConnectionResolver(resolver_config, vault=mock_vault, backend=None)

    mock_vault.add_connection(
        handle="ddls:conn_user",
        driver_type="supabase",
        auth_type="user",
        secret="",
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(BackendError, match="backend not configured"):
        await resolver.resolve_client("ddls:conn_user", request_context)


@pytest.mark.asyncio
async def test_resolve_user_credential_missing_encrypted_cred(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_backend: MockExecutionBackend,
) -> None:
    """Test error when encrypted credential missing from token."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault, backend=mock_backend)

    mock_vault.add_connection(
        handle="ddls:conn_user",
        driver_type="supabase",
        auth_type="user",
        secret="",
    )

    # Auth context without encrypted credential
    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_user"],
            # Missing ddls:credential
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(BackendError, match="missing encrypted credential"):
        await resolver.resolve_client("ddls:conn_user", request_context)


# =============================================================================
# Authorization Tests
# =============================================================================


@pytest.mark.asyncio
async def test_unauthorized_handle_rejected(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
) -> None:
    """Test unauthorized handle rejection."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_unauthorized",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
    )

    # Auth context WITHOUT unauthorized handle
    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_org"],  # Different handle
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(UnauthorizedHandleError, match="handle not authorized"):
        await resolver.resolve_client("ddls:conn_unauthorized", request_context)


@pytest.mark.asyncio
async def test_missing_auth_context(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
) -> None:
    """Test error when auth context missing."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)

    request_context = {}  # No auth context

    # Execute & Verify
    with pytest.raises(ResolverError, match="missing authentication context"):
        await resolver.resolve_client("ddls:conn_org", request_context)


# =============================================================================
# Token Claims Validation Tests
# =============================================================================


@pytest.mark.asyncio
async def test_validate_handle_in_connections_claim(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
) -> None:
    """Test handle must be in ddls:connectors claim."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_test",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
    )

    # Auth context with handle in connections
    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_test", "ddls:conn_other"],
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute - should succeed
    client = await resolver.resolve_client("ddls:conn_test", request_context)
    assert client is not None


@pytest.mark.asyncio
async def test_validate_fingerprint_from_token_claim(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
) -> None:
    """Test fingerprint validation uses ddls:fingerprints claim."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_fp",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
        fingerprint="fp_correct_123",
    )

    # Auth context with matching fingerprint
    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_fp"],
            "ddls:fingerprints": {
                "ddls:conn_fp": "fp_correct_123",
            },
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute - should succeed
    client = await resolver.resolve_client("ddls:conn_fp", request_context)
    assert client is not None


@pytest.mark.asyncio
async def test_per_handle_scopes_validation(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
) -> None:
    """Test per-handle scope enforcement (future feature)."""
    # This test documents the intended per-handle scope validation
    # Currently, scope validation happens at the token level (in jwt_validator)
    # but could be extended to per-handle scopes in ddls:connection_scopes claim

    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_scoped",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host/db",
    )

    # Future: ddls:connection_scopes claim
    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_scoped"],
            # Future: "ddls:connection_scopes": {
            #     "ddls:conn_scoped": ["read", "write"]
            # }
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute - currently succeeds (no per-handle scope enforcement yet)
    client = await resolver.resolve_client("ddls:conn_scoped", request_context)
    assert client is not None


# =============================================================================
# Vault Error Tests
# =============================================================================


@pytest.mark.asyncio
async def test_vault_disabled(
    mock_driver: MockDriver,
) -> None:
    """Test error when vault disabled."""
    # Setup with vault disabled
    config = ResolverConfig(vault_enabled=False)
    resolver = ConnectionResolver(config, vault=None)

    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={"ddls:connectors": ["ddls:conn_test"]},
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(VaultError, match="vault connector not configured"):
        await resolver.resolve_client("ddls:conn_test", request_context)


@pytest.mark.asyncio
async def test_vault_connection_not_found(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    auth_context: AuthorizationContext,
) -> None:
    """Test error when connection not in vault."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    # Don't add connection to vault

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(VaultError, match="failed to retrieve connection metadata"):
        await resolver.resolve_client("ddls:conn_org", request_context)


@pytest.mark.asyncio
async def test_vault_secret_decryption_failure(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
) -> None:
    """Test error when secret decryption fails."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    # Add connection but not secret (will fail on decrypt)
    mock_vault.connections["ddls:conn_org"] = ConnectionMetadata(
        handle="ddls:conn_org",
        driver_type="postgres",
        auth_type="org",
    )
    # Don't add secret to mock_vault.secrets

    request_context = {"openmcp.auth": auth_context}

    # Execute & Verify
    with pytest.raises(VaultError, match="failed to decrypt secret"):
        await resolver.resolve_client("ddls:conn_org", request_context)


# =============================================================================
# Driver Registry Tests
# =============================================================================


@pytest.mark.asyncio
async def test_register_multiple_drivers(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
) -> None:
    """Test registering multiple drivers."""
    # Setup
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)

    postgres_driver = MockDriver()
    supabase_driver = MockDriver()
    rest_driver = MockDriver()

    # Register drivers
    resolver.register_driver("postgres", postgres_driver)
    resolver.register_driver("supabase", supabase_driver)
    resolver.register_driver("rest", rest_driver)

    # Verify registration through resolution
    mock_vault.add_connection(
        handle="ddls:conn_postgres",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://...",
    )

    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={"ddls:connectors": ["ddls:conn_postgres"]},
    )

    request_context = {"openmcp.auth": auth_context}

    client = await resolver.resolve_client("ddls:conn_postgres", request_context)
    assert client is not None
    assert len(postgres_driver.created_clients) == 1


@pytest.mark.asyncio
async def test_driver_initialization_with_registry(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
) -> None:
    """Test initializing resolver with driver registry."""
    # Setup with pre-populated driver registry
    postgres_driver = MockDriver()
    supabase_driver = MockDriver()

    drivers = {
        "postgres": postgres_driver,
        "supabase": supabase_driver,
    }

    resolver = ConnectionResolver(resolver_config, vault=mock_vault, drivers=drivers)

    mock_vault.add_connection(
        handle="ddls:conn_supabase",
        driver_type="supabase",
        auth_type="org",
        secret="supabase://...",
    )

    auth_context = AuthorizationContext(
        subject="user_123",
        scopes=["mcp:tools:call"],
        claims={"ddls:connectors": ["ddls:conn_supabase"]},
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute
    client = await resolver.resolve_client("ddls:conn_supabase", request_context)
    assert client is not None
    assert len(supabase_driver.created_clients) == 1


# =============================================================================
# Audit Logging Tests
# =============================================================================


@pytest.mark.asyncio
async def test_audit_logging_enabled(
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test audit logging when enabled."""
    # Setup with audit logging
    config = ResolverConfig(audit_log=True)
    resolver = ConnectionResolver(config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_audit",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://...",
    )

    # Update auth context with correct handle
    auth_context.claims["ddls:connectors"] = ["ddls:conn_audit"]

    request_context = {"openmcp.auth": auth_context}

    # Execute
    await resolver.resolve_client("ddls:conn_audit", request_context)

    # Verify audit log (check for success event)
    assert any("resolve_success" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_audit_logging_disabled(
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
    auth_context: AuthorizationContext,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test audit logging when disabled."""
    # Setup with audit logging disabled
    config = ResolverConfig(audit_log=False)
    resolver = ConnectionResolver(config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    mock_vault.add_connection(
        handle="ddls:conn_no_audit",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://...",
    )

    auth_context.claims["ddls:connectors"] = ["ddls:conn_no_audit"]
    request_context = {"openmcp.auth": auth_context}

    # Execute
    await resolver.resolve_client("ddls:conn_no_audit", request_context)

    # Verify no audit logs (resolver.* events should not appear)
    assert not any("resolver." in record.message for record in caplog.records)


# =============================================================================
# Integration Tests
# =============================================================================


@pytest.mark.asyncio
async def test_end_to_end_org_credential_flow(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_driver: MockDriver,
) -> None:
    """Test complete org credential flow end-to-end."""
    # Setup complete system
    resolver = ConnectionResolver(resolver_config, vault=mock_vault)
    resolver.register_driver("postgres", mock_driver)

    # Add connection with fingerprint
    mock_vault.add_connection(
        handle="ddls:conn_e2e_org",
        driver_type="postgres",
        auth_type="org",
        secret="postgres://user:pass@host:5432/db",
        fingerprint="fp_e2e_123",
    )

    # Auth context with all claims
    auth_context = AuthorizationContext(
        subject="org_user_123",
        scopes=["mcp:tools:call", "mcp:connections:read"],
        claims={
            "ddls:connectors": ["ddls:conn_e2e_org"],
            "ddls:fingerprints": {"ddls:conn_e2e_org": "fp_e2e_123"},
            "org_id": "org_456",
        },
    )

    request_context = {"openmcp.auth": auth_context}

    # Execute
    client = await resolver.resolve_client("ddls:conn_e2e_org", request_context)

    # Verify complete flow
    assert client is not None
    assert len(mock_driver.created_clients) == 1
    secret, params = mock_driver.created_clients[0]
    assert secret == "postgres://user:pass@host:5432/db"
    assert params == {"test": "param"}


@pytest.mark.asyncio
async def test_end_to_end_user_credential_flow(
    resolver_config: ResolverConfig,
    mock_vault: MockVaultConnector,
    mock_backend: MockExecutionBackend,
) -> None:
    """Test complete user credential flow end-to-end."""
    # Setup complete system
    resolver = ConnectionResolver(resolver_config, vault=mock_vault, backend=mock_backend)

    # Add user connection
    mock_vault.add_connection(
        handle="ddls:conn_e2e_user",
        driver_type="supabase",
        auth_type="user",
        secret="",  # Not used
        fingerprint="fp_user_e2e",
    )

    # Auth context with encrypted credential
    auth_context = AuthorizationContext(
        subject="end_user_789",
        scopes=["mcp:tools:call"],
        claims={
            "ddls:connectors": ["ddls:conn_e2e_user"],
            "ddls:fingerprints": {"ddls:conn_e2e_user": "fp_user_e2e"},
            "ddls:credential": {
                "encrypted": "encrypted_user_cred_xyz",
                "algorithm": "aes-256-gcm",
            },
        },
    )

    request_context = {
        "openmcp.auth": auth_context,
        "operation": {
            "type": "rpc",
            "function": "get_user_profile",
            "args": {"user_id": "789"},
        },
    }

    # Execute
    result = await resolver.resolve_client("ddls:conn_e2e_user", request_context)

    # Verify complete flow
    assert result == {"result": "success", "data": "test_data"}
    assert len(mock_backend.calls) == 1

    call = mock_backend.calls[0]
    assert call["cred"]["encrypted"] == "encrypted_user_cred_xyz"
    assert call["call"]["handle"] == "ddls:conn_e2e_user"
    assert call["call"]["driver_type"] == "supabase"
    assert call["call"]["operation"]["type"] == "rpc"
