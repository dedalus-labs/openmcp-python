# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for connection definition framework."""

from __future__ import annotations

import pytest

from openmcp.server.connectors import (
    ConnectorDefinition,
    ConnectorHandle,
    EnvironmentCredentialLoader,
    EnvironmentCredentials,
    EnvironmentBindings,
    define,
)


class TestConnectorDefinition:
    """Test ConnectorDefinition class."""

    def test_valid_definition(self) -> None:
        """Test creating a valid connection definition."""
        defn = ConnectorDefinition(
            kind="postgres",
            params={"host": str, "port": int, "database": str},
            auth_methods=["password", "cert"],
            description="PostgreSQL connection",
        )

        assert defn.kind == "postgres"
        assert defn.params == {"host": str, "port": int, "database": str}
        assert defn.auth_methods == ["password", "cert"]
        assert defn.description == "PostgreSQL connection"

    def test_empty_kind_raises(self) -> None:
        """Test that empty kind raises ValueError."""
        with pytest.raises(ValueError, match="kind must be non-empty"):
            ConnectorDefinition(
                kind="",
                params={"url": str},
                auth_methods=["token"],
            )

    def test_empty_params_raises(self) -> None:
        """Test that empty params raises ValueError."""
        with pytest.raises(ValueError, match="params must contain at least one parameter"):
            ConnectorDefinition(
                kind="test",
                params={},
                auth_methods=["token"],
            )

    def test_empty_auth_methods_raises(self) -> None:
        """Test that empty auth_methods raises ValueError."""
        with pytest.raises(ValueError, match="auth_methods must contain at least one method"):
            ConnectorDefinition(
                kind="test",
                params={"url": str},
                auth_methods=[],
            )

    def test_invalid_param_type_raises(self) -> None:
        """Test that non-type param values raise TypeError."""
        with pytest.raises(TypeError, match="param 'url' must be a type"):
            ConnectorDefinition(
                kind="test",
                params={"url": "string"},  # type: ignore
                auth_methods=["token"],
            )

    def test_to_json_basic(self) -> None:
        """Test JSON serialization with basic types."""
        defn = ConnectorDefinition(
            kind="http-api",
            params={"base_url": str},
            auth_methods=["service_credential", "user_token"],
            description="Generic HTTP API connection",
        )

        result = defn.to_json()

        assert result == {
            "kind": "http-api",
            "params": {
                "base_url": {"type": "string"},
            },
            "auth_methods": ["service_credential", "user_token"],
            "description": "Generic HTTP API connection",
        }

    def test_to_json_multiple_types(self) -> None:
        """Test JSON serialization with multiple parameter types."""
        defn = ConnectorDefinition(
            kind="custom",
            params={
                "url": str,
                "port": int,
                "timeout": float,
                "ssl": bool,
            },
            auth_methods=["token"],
        )

        result = defn.to_json()

        assert result["params"] == {
            "url": {"type": "string"},
            "port": {"type": "integer"},
            "timeout": {"type": "number"},
            "ssl": {"type": "boolean"},
        }

    def test_frozen_dataclass(self) -> None:
        """Test that ConnectorDefinition is immutable."""
        defn = ConnectorDefinition(
            kind="test",
            params={"url": str},
            auth_methods=["token"],
        )

        with pytest.raises(AttributeError):
            defn.kind = "modified"  # type: ignore


class TestConnectorHandle:
    """Test ConnectorHandle class."""

    def test_valid_handle(self) -> None:
        """Test creating a valid connection handle."""
        handle = ConnectorHandle(
            id="ddls:conn_abc123",
            kind="postgres",
            config={"host": "localhost", "port": 5432, "database": "mydb"},
            auth_type="password",
        )

        assert handle.id == "ddls:conn_abc123"
        assert handle.kind == "postgres"
        assert handle.config == {"host": "localhost", "port": 5432, "database": "mydb"}
        assert handle.auth_type == "password"

    def test_invalid_id_prefix_raises(self) -> None:
        """Test that invalid ID prefix raises ValueError."""
        with pytest.raises(ValueError, match="id must start with 'ddls:conn_'"):
            ConnectorHandle(
                id="invalid_prefix",
                kind="test",
                config={"url": "test"},
                auth_type="token",
            )

    def test_empty_kind_raises(self) -> None:
        """Test that empty kind raises ValueError."""
        with pytest.raises(ValueError, match="kind must be non-empty"):
            ConnectorHandle(
                id="ddls:conn_123",
                kind="",
                config={"url": "test"},
                auth_type="token",
            )

    def test_empty_config_raises(self) -> None:
        """Test that empty config raises ValueError."""
        with pytest.raises(ValueError, match="config must be non-empty"):
            ConnectorHandle(
                id="ddls:conn_123",
                kind="test",
                config={},
                auth_type="token",
            )

    def test_empty_auth_type_raises(self) -> None:
        """Test that empty auth_type raises ValueError."""
        with pytest.raises(ValueError, match="auth_type must be non-empty"):
            ConnectorHandle(
                id="ddls:conn_123",
                kind="test",
                config={"url": "test"},
                auth_type="",
            )

    def test_frozen_dataclass(self) -> None:
        """Test that ConnectorHandle is immutable."""
        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="test",
            config={"url": "test"},
            auth_type="token",
        )

        with pytest.raises(AttributeError):
            handle.kind = "modified"  # type: ignore


class TestDefineFunction:
    """Test define() factory function."""

    def test_basic_definition(self) -> None:
        """Test creating a basic connection type."""
        conn_type = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        assert conn_type is not None
        assert conn_type.definition.kind == "http-api"
        assert conn_type.definition.params == {"base_url": str}
        assert conn_type.definition.auth_methods == ["service_credential"]

    def test_with_description(self) -> None:
        """Test creating connection type with description."""
        conn_type = define(
            kind="postgres",
            params={"host": str, "port": int},
            auth=["password"],
            description="PostgreSQL database connection",
        )

        assert conn_type.definition.description == "PostgreSQL database connection"

    def test_multiple_params_and_auth(self) -> None:
        """Test connection type with multiple params and auth methods."""
        conn_type = define(
            kind="rest_api",
            params={
                "base_url": str,
                "timeout": int,
                "verify_ssl": bool,
            },
            auth=["api_key", "oauth2", "basic"],
        )

        assert len(conn_type.definition.params) == 3
        assert len(conn_type.definition.auth_methods) == 3

    def test_validates_on_creation(self) -> None:
        """Test that define() validates the definition."""
        with pytest.raises(ValueError, match="kind must be non-empty"):
            define(
                kind="",
                params={"url": str},
                auth=["token"],
            )


class TestConnectionTypeValidation:
    """Test _ConnectorType validation methods."""

    def test_validate_matching_handle(self) -> None:
        """Test validating a matching connection handle."""
        conn_type = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="http-api",
            config={"base_url": "https://example.http-api.co"},
            auth_type="service_credential",
        )

        # Should not raise
        conn_type.validate(handle)

    def test_validate_wrong_kind(self) -> None:
        """Test validation fails for wrong kind."""
        conn_type = define(
            kind="postgres",
            params={"host": str},
            auth=["password"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="mysql",  # Wrong kind
            config={"host": "localhost"},
            auth_type="password",
        )

        with pytest.raises(ValueError, match="expected kind 'postgres', got 'mysql'"):
            conn_type.validate(handle)

    def test_validate_missing_params(self) -> None:
        """Test validation fails for missing params."""
        conn_type = define(
            kind="postgres",
            params={"host": str, "port": int, "database": str},
            auth=["password"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="postgres",
            config={"host": "localhost"},  # Missing port and database
            auth_type="password",
        )

        with pytest.raises(ValueError, match="missing required params"):
            conn_type.validate(handle)

    def test_validate_unsupported_auth(self) -> None:
        """Test validation fails for unsupported auth method."""
        conn_type = define(
            kind="postgres",
            params={"host": str},
            auth=["password", "cert"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="postgres",
            config={"host": "localhost"},
            auth_type="kerberos",  # Not supported
        )

        with pytest.raises(ValueError, match="auth_type 'kerberos' not in supported methods"):
            conn_type.validate(handle)

    def test_validate_wrong_param_type(self) -> None:
        """Test validation fails for wrong parameter type."""
        conn_type = define(
            kind="postgres",
            params={"host": str, "port": int},
            auth=["password"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_123",
            kind="postgres",
            config={"host": "localhost", "port": "5432"},  # Port should be int
            auth_type="password",
        )

        with pytest.raises(TypeError, match="param 'port' expected int, got str"):
            conn_type.validate(handle)

    def test_validate_complex_scenario(self) -> None:
        """Test validation with complex connection setup."""
        conn_type = define(
            kind="rest_api",
            params={
                "base_url": str,
                "timeout": int,
                "verify_ssl": bool,
            },
            auth=["api_key", "oauth2"],
        )

        handle = ConnectorHandle(
            id="ddls:conn_xyz789",
            kind="rest_api",
            config={
                "base_url": "https://api.example.com",
                "timeout": 30,
                "verify_ssl": True,
            },
            auth_type="oauth2",
        )

        # Should not raise
        conn_type.validate(handle)


class TestConnectionTypeRepr:
    """Test _ConnectorType string representation."""

    def test_repr(self) -> None:
        """Test __repr__ output."""
        conn_type = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        assert repr(conn_type) == "ConnectionType(kind='http-api')"


class TestIntegration:
    """Integration tests for the connection framework."""

    def test_full_workflow(self) -> None:
        """Test complete workflow: define, create handle, validate, serialize."""
        # Define connection type
        http_api_conn = define(
            kind="http-api",
            params={"base_url": str, "label": str},
            auth=["service_credential", "user_token"],
            description="HTTP API connection",
        )

        # Create connection handle
        handle = ConnectorHandle(
            id="ddls:conn_prod_123",
            kind="http-api",
            config={
                "base_url": "https://api.example.com",
                "label": "prod",
            },
            auth_type="service_credential",
        )

        # Validate handle
        http_api_conn.validate(handle)

        # Serialize definition to JSON
        json_output = http_api_conn.definition.to_json()

        assert json_output["kind"] == "http-api"
        assert "base_url" in json_output["params"]
        assert "service_credential" in json_output["auth_methods"]

    def test_multiple_connection_types(self) -> None:
        """Test defining and using multiple connection types."""
        PostgresConn = define(
            kind="postgres",
            params={"host": str, "port": int, "database": str},
            auth=["password"],
        )

        RedisConn = define(
            kind="redis",
            params={"host": str, "port": int},
            auth=["password", "none"],
        )

        # Create handles
        pg_handle = ConnectorHandle(
            id="ddls:conn_pg_1",
            kind="postgres",
            config={"host": "localhost", "port": 5432, "database": "mydb"},
            auth_type="password",
        )

        redis_handle = ConnectorHandle(
            id="ddls:conn_redis_1",
            kind="redis",
            config={"host": "localhost", "port": 6379},
            auth_type="none",
        )

        # Validate each
        PostgresConn.validate(pg_handle)
        RedisConn.validate(redis_handle)

        # Cross-validation should fail
        with pytest.raises(ValueError, match="expected kind"):
            PostgresConn.validate(redis_handle)


class TestEnvironmentCredentialLoader:
    """Tests for EnvironmentCredentialLoader helper."""

    def test_supported_auth_types(self) -> None:
        connector = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential", "user_token"],
        )

        loader = EnvironmentCredentialLoader(
            connector,
            variants={
                "service_credential": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_SERVICE_KEY"),
                ),
                "user_token": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_USER_TOKEN"),
                ),
            },
        )

        assert loader.supported_auth_types() == ["service_credential", "user_token"]

    def test_load_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connector = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential", "user_token"],
        )

        loader = EnvironmentCredentialLoader(
            connector,
            variants={
                "service_credential": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_SERVICE_KEY"),
                ),
                "user_token": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_USER_TOKEN"),
                ),
            },
        )

        monkeypatch.setenv("GENERIC_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("GENERIC_SERVICE_KEY", "svc-123")
        monkeypatch.setenv("GENERIC_USER_TOKEN", "user-xyz")

        resolved = loader.load("service_credential")
        assert resolved.handle.config == {"base_url": "https://api.example.com"}
        assert resolved.handle.auth_type == "service_credential"
        assert resolved.config.base_url == "https://api.example.com"
        assert resolved.auth.secret == "svc-123"
        assert resolved.auth.type == "service_credential"

        resolved_user = loader.load("user_token")
        assert resolved_user.handle.auth_type == "user_token"
        assert resolved_user.auth.secret == "user-xyz"
        assert resolved_user.auth.type == "user_token"

    def test_missing_environment_variable_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connector = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        loader = EnvironmentCredentialLoader(
            connector,
            variants={
                "service_credential": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_SERVICE_KEY"),
                )
            },
        )

        monkeypatch.setenv("GENERIC_BASE_URL", "https://api.example.com")

        with pytest.raises(RuntimeError, match="GENERIC_SERVICE_KEY"):
            loader.load("service_credential")

    def test_unknown_auth_type(self, monkeypatch: pytest.MonkeyPatch) -> None:
        connector = define(
            kind="http-api",
            params={"base_url": str},
            auth=["service_credential"],
        )

        loader = EnvironmentCredentialLoader(
            connector,
            variants={
                "service_credential": EnvironmentCredentials(
                    config=EnvironmentBindings(base_url="GENERIC_BASE_URL"),
                    secrets=EnvironmentBindings(secret="GENERIC_SERVICE_KEY"),
                )
            },
        )

        monkeypatch.setenv("GENERIC_BASE_URL", "https://api.example.com")
        monkeypatch.setenv("GENERIC_SERVICE_KEY", "svc-123")

        with pytest.raises(ValueError, match="auth_type 'user_token' not configured"):
            loader.load("user_token")
