# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Connection definition framework for OpenMCP.

This module provides a declarative schema for defining connection types that
tools can accept. Connection definitions specify the parameters and authentication
methods required to establish connections to external services.

Key components:

* :class:`ConnectorDefinition` – Declarative schema for connection types
* :func:`define` – Factory for creating connection type handles
* :class:`ConnectorHandle` – Runtime representation of an active connection
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypeVar

from pydantic import BaseModel, create_model

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .drivers import Driver

_UNSET = object()


@dataclass(frozen=True, slots=True)
class ConnectorDefinition:
    """Declarative schema defining a connection type.

    A connection definition specifies the structure and requirements for
    establishing connections to external services.

    Attributes:
        kind: Unique identifier for the connection type (e.g., "supabase", "postgres")
        params: Parameter names and their expected types
        auth_methods: Supported authentication method names
        description: Human-readable description of the connection
    """

    kind: str
    params: dict[str, type]
    auth_methods: list[str]
    description: str = ""

    def __post_init__(self) -> None:
        """Validate connection definition invariants."""
        if not self.kind:
            raise ValueError("kind must be non-empty")
        if not self.params:
            raise ValueError("params must contain at least one parameter")
        if not self.auth_methods:
            raise ValueError("auth_methods must contain at least one method")

        # Validate param types
        for param_name, param_type in self.params.items():
            if not isinstance(param_type, type):
                raise TypeError(f"param '{param_name}' must be a type, got {type(param_type).__name__}")

    def to_json(self) -> dict[str, Any]:
        """Serialize to JSON for .well-known endpoint.

        Returns:
            JSON-serializable dictionary representation
        """
        return {
            "kind": self.kind,
            "params": {name: _type_to_json_schema(typ) for name, typ in self.params.items()},
            "auth_methods": self.auth_methods,
            "description": self.description,
        }


@dataclass(frozen=True, slots=True)
class ConnectorHandle:
    """Runtime handle representing an active connection.

    This is the runtime representation passed to tools at execution time,
    containing the actual configuration and credentials.

    Attributes:
        id: Unique connection identifier (format: "ddls:conn_...")
        kind: Connection type (must match a ConnectorDefinition.kind)
        config: Connection configuration parameters
        auth_type: Authentication method being used
    """

    id: str
    kind: str
    config: dict[str, Any]
    auth_type: str

    def __post_init__(self) -> None:
        """Validate connection handle invariants."""
        if not self.id.startswith("ddls:conn_"):
            raise ValueError(f"id must start with 'ddls:conn_', got {self.id}")
        if not self.kind:
            raise ValueError("kind must be non-empty")
        if not self.config:
            raise ValueError("config must be non-empty")
        if not self.auth_type:
            raise ValueError("auth_type must be non-empty")


# Type variable for connection handles
ConnT = TypeVar("ConnT", bound=ConnectorHandle)


def _model_name(kind: str, suffix: str) -> str:
    parts = [part for part in kind.replace("_", "-").split("-") if part]
    base = "".join(part.capitalize() for part in parts) or "Connector"
    return f"{base}{suffix}"


class _ConnectorType:
    """Type marker for connection definitions.

    This class represents a connection type that can be used in tool signatures.
    It wraps a ConnectorDefinition and can be used for type hints and validation.
    """

    def __init__(self, definition: ConnectorDefinition) -> None:
        self._definition = definition
        fields = {name: (param_type, ...) for name, param_type in definition.params.items()}
        self._config_model = create_model(
            _model_name(definition.kind, "Config"),
            __base__=BaseModel,
            **fields,
        )

    @property
    def definition(self) -> ConnectorDefinition:
        """Access the underlying connection definition."""
        return self._definition

    @property
    def config_model(self) -> type[BaseModel]:
        """Return the Pydantic model for this connector's configuration."""

        return self._config_model

    def parse_config(self, data: dict[str, Any]) -> BaseModel:
        """Parse configuration payload into the typed model."""

        return self._config_model(**data)

    def validate(self, handle: ConnectorHandle) -> None:
        """Validate a connection handle against this definition.

        Args:
            handle: Connection handle to validate

        Raises:
            ValueError: If handle doesn't match definition requirements
        """
        if handle.kind != self._definition.kind:
            raise ValueError(f"expected kind '{self._definition.kind}', got '{handle.kind}'")

        # Validate all required params are present
        missing = set(self._definition.params.keys()) - set(handle.config.keys())
        if missing:
            raise ValueError(f"missing required params: {', '.join(sorted(missing))}")

        # Validate auth method is supported
        if handle.auth_type not in self._definition.auth_methods:
            raise ValueError(
                f"auth_type '{handle.auth_type}' not in supported methods: {', '.join(self._definition.auth_methods)}"
            )

        # Validate param types
        for param_name, expected_type in self._definition.params.items():
            value = handle.config[param_name]
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"param '{param_name}' expected {expected_type.__name__}, got {type(value).__name__}"
                )

    def __repr__(self) -> str:
        return f"ConnectionType(kind={self._definition.kind!r})"


def define(
    kind: str,
    params: dict[str, type],
    auth: list[str],
    description: str = "",
) -> _ConnectorType:
    """Define a connection type for use in tool signatures.

    This factory function creates a reusable connection type that can be used
    in tool parameter type hints to declare connection dependencies.

    Args:
        kind: Unique connection type identifier
        params: Dictionary mapping parameter names to their types
        auth: List of supported authentication method names
        description: Optional human-readable description

    Returns:
        Connection type handle for use in type signatures

    Example:
        >>> HttpConn = define(
        ...     kind="http-api",
        ...     params={"base_url": str},
        ...     auth=["service_credential", "user_token"],
        ...     description="Generic HTTP API connection"
        ... )
        >>> # Use in tool signature:
        >>> def my_tool(conn: HttpConn) -> str:
        ...     return "connected"
    """
    definition = ConnectorDefinition(
        kind=kind,
        params=params,
        auth_methods=auth,
        description=description,
    )
    return _ConnectorType(definition)


def _type_to_json_schema(typ: type) -> dict[str, str]:
    """Convert Python type to JSON Schema type representation.

    Args:
        typ: Python type to convert

    Returns:
        JSON Schema type dictionary
    """
    type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
    }

    json_type = type_map.get(typ, "string")
    return {"type": json_type}


__all__ = [
    "ConnectorDefinition",
    "ConnectorHandle",
    "EnvironmentBinding",
    "EnvironmentBindings",
    "EnvironmentCredentials",
    "EnvironmentCredentialLoader",
    "ResolvedConnector",
    "define",
]


@dataclass(frozen=True, slots=True)
class ResolvedConnector:
    """Typed connector resolution result.

    Attributes:
        handle: Persistable connector handle (config stored as plain dict).
        config: Typed configuration model parsed via :class:`ConnectorDefinition`.
        auth: Typed secret/authentication model including the ``type`` discriminator.
    """

    handle: ConnectorHandle
    config: BaseModel
    auth: BaseModel

    async def build_client(self, driver: "Driver") -> Any:
        """Instantiate a client using the provided driver."""

        return await driver.create_client(self.config, self.auth)

@dataclass(frozen=True, slots=True)
class EnvironmentBinding:
    """Descriptor for a single environment-provided value."""

    name: str
    cast: type = str
    default: Any = _UNSET
    optional: bool = False


@dataclass(frozen=True, slots=True)
class EnvironmentBindings:
    """Mapping from field names to environment bindings."""

    entries: dict[str, EnvironmentBinding]

    def __init__(self, **kwargs: Any) -> None:  # type: ignore[override]
        entries = {
            key: value if isinstance(value, EnvironmentBinding) else EnvironmentBinding(str(value))
            for key, value in kwargs.items()
        }
        object.__setattr__(self, "entries", entries)


@dataclass(frozen=True, slots=True)
class EnvironmentCredentials:
    """Environment-backed configuration for a connector auth method."""

    config: EnvironmentBindings = field(default_factory=EnvironmentBindings)
    secrets: EnvironmentBindings = field(default_factory=EnvironmentBindings)


class EnvironmentCredentialLoader:
    """Load connector credentials from environment variables.

    This helper lets resource servers bootstrap connection handles without
    embedding vendor-specific logic. Each authentication method maps the
    connector's required parameters and secret fields to environment
    variables. Missing variables raise ``RuntimeError`` so misconfiguration is
    caught during startup.
    """

    def __init__(
        self,
        connector: _ConnectorType,
        variants: dict[str, EnvironmentCredentials],
        *,
        handle_prefix: str = "ddls:conn_env",
    ) -> None:
        if not variants:
            raise ValueError("variants must contain at least one auth mapping")

        allowed_auth = set(connector.definition.auth_methods)
        unknown = sorted(set(variants.keys()) - allowed_auth)
        if unknown:
            raise ValueError(
                "environment credentials configured for unsupported auth methods: "
                + ", ".join(unknown)
            )

        self._connector = connector
        self._variants = variants
        self._handle_prefix = handle_prefix.rstrip("_")

    def supported_auth_types(self) -> list[str]:
        """Return auth types configured for this source."""
        return sorted(self._variants.keys())

    def load(self, auth_type: str) -> ResolvedConnector:
        """Load credentials for ``auth_type``.

        Returns the connector handle plus a secret payload that callers can
        hand to a driver.
        """
        if auth_type not in self._variants:
            raise ValueError(f"auth_type '{auth_type}' not configured for this source")

        mapping = self._variants[auth_type]
        config_values = {name: self._read_env(value) for name, value in mapping.config.entries.items()}
        config_model = self._connector.config_model(**config_values)

        secret_fields = {
            name: (value.cast, ...)
            for name, value in mapping.secrets.entries.items()
        }
        AuthModel = create_model(  # type: ignore[call-arg]
            _model_name(f"{self._connector.definition.kind}_{auth_type}", "Auth"),
            __base__=BaseModel,
            type=(Literal[auth_type], auth_type),
            **secret_fields,
        )
        secret_values = {name: self._read_env(value) for name, value in mapping.secrets.entries.items()}
        auth_model = AuthModel(**secret_values)

        handle = ConnectorHandle(
            id=f"{self._handle_prefix}_{self._connector.definition.kind}_{auth_type}",
            kind=self._connector.definition.kind,
            config=config_model.model_dump(),
            auth_type=auth_type,
        )
        self._connector.validate(handle)

        return ResolvedConnector(handle=handle, config=config_model, auth=auth_model)

    @staticmethod
    def _read_env(binding: EnvironmentBinding) -> Any:
        raw = os.getenv(binding.name)
        if raw is None or raw == "":
            if binding.default is not _UNSET:
                return binding.default
            if binding.optional:
                return None
            raise RuntimeError(f"Environment variable {binding.name} is not set")
        if binding.cast is str:
            return raw
        return binding.cast(raw)

