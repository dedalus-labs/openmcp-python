# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Base driver implementation with common validation logic."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel


class BaseDriver:
    """Base class providing common driver functionality.

    Subclasses should override `create_client` to implement service-specific
    client creation logic.
    """

    @staticmethod
    def _normalize_input(data: Any) -> dict[str, Any]:
        """Coerce BaseModel/mapping inputs into plain dictionaries."""

        if isinstance(data, BaseModel):
            return data.model_dump()
        if hasattr(data, "model_dump"):
            return data.model_dump()
        if isinstance(data, Mapping):
            return dict(data)
        raise TypeError("Expected mapping or Pydantic model input")

    @staticmethod
    def _validate_required_config(config: dict[str, Any], keys: list[str]) -> None:
        """Validate that required config keys are present.

        Args:
            config: Configuration dictionary
            keys: List of required keys

        Raises:
            ValueError: If any required key is missing
        """
        missing = [k for k in keys if k not in config]
        if missing:
            raise ValueError(f"Missing required config parameter(s): {', '.join(missing)}")

    @staticmethod
    def _validate_auth_type(auth: dict[str, Any], supported_types: list[str]) -> None:
        """Validate that auth type is supported.

        Args:
            auth: Authentication dictionary
            supported_types: List of supported auth types

        Raises:
            ValueError: If auth type is missing or unsupported
        """
        auth_type = auth.get("type")
        if not auth_type:
            raise ValueError("Missing 'type' field in auth parameters")
        if auth_type not in supported_types:
            raise ValueError(
                f"Unsupported auth type '{auth_type}'. "
                f"Supported types: {', '.join(supported_types)}"
            )

    @staticmethod
    def _get_required_auth_field(auth: dict[str, Any], field: str) -> Any:
        """Extract required field from auth dict.

        Args:
            auth: Authentication dictionary
            field: Field name to extract

        Returns:
            Field value

        Raises:
            ValueError: If field is missing
        """
        value = auth.get(field)
        if not value:
            raise ValueError(f"Missing required auth field: {field}")
        return value


__all__ = ["BaseDriver"]
