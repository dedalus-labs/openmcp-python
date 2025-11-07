# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Tests for JSON serialization utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, Field

from openmcp.types import (
    CallToolResult,
    ErrorData,
    TextContent,
    ImageContent,
    EmbeddedResource,
)
from openmcp.utils.serializer import to_json


class Color(Enum):
    """Test enum."""

    RED = "red"
    BLUE = "blue"


class NestedModel(BaseModel):
    """Deeply nested Pydantic model."""

    timestamp: datetime
    identifier: UUID
    color: Color
    metadata: dict[str, Any]


class ComplexModel(BaseModel):
    """Complex model with aliases and nested structures."""

    display_name: str = Field(alias="displayName")
    items: list[NestedModel]
    optional_field: str | None = None


def test_dump_primitives():
    """Test serialization of primitive types."""
    assert to_json(42) == 42
    assert to_json("hello") == "hello"
    assert to_json(True) is True
    assert to_json(None) is None
    assert to_json(3.14) == 3.14


def test_dump_collections():
    """Test serialization of lists, dicts, tuples."""
    assert to_json([1, 2, 3]) == [1, 2, 3]
    assert to_json({"key": "value"}) == {"key": "value"}
    assert to_json((1, 2, 3)) == [1, 2, 3]  # mode='json' converts tuples to lists
    assert to_json({"nested": {"dict": [1, 2]}}) == {"nested": {"dict": [1, 2]}}


def test_dump_datetime():
    """Test datetime serialization."""
    dt = datetime(2025, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
    result = to_json(dt)
    assert isinstance(result, str)
    assert "2025-01-15" in result
    assert "10:30:45" in result


def test_dump_uuid():
    """Test UUID serialization."""
    uid = UUID("12345678-1234-5678-1234-567812345678")
    result = to_json(uid)
    assert result == "12345678-1234-5678-1234-567812345678"


def test_dump_enum():
    """Test enum serialization."""
    assert to_json(Color.RED) == "red"
    assert to_json(Color.BLUE) == "blue"


def test_dump_simple_pydantic_model():
    """Test basic Pydantic model serialization."""

    class SimpleModel(BaseModel):
        name: str
        count: int

    obj = SimpleModel(name="test", count=42)
    result = to_json(obj)

    assert result == {"name": "test", "count": 42}


def test_dump_pydantic_with_alias():
    """Test Pydantic model with field aliases."""

    class AliasedModel(BaseModel):
        internal_name: str = Field(alias="externalName")

    # Pydantic v2 requires using populate_by_name or passing via alias
    obj = AliasedModel.model_validate({"externalName": "value"})
    result = to_json(obj)

    # by_alias=True is default, so should use alias
    assert result == {"externalName": "value"}
    assert "internal_name" not in result


def test_dump_nested_pydantic_models():
    """Test deeply nested Pydantic models with complex types."""
    nested = NestedModel(
        timestamp=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
        identifier=UUID("12345678-1234-5678-1234-567812345678"),
        color=Color.RED,
        metadata={"key": "value", "count": 42},
    )

    obj = ComplexModel.model_validate({"displayName": "Test Object", "items": [nested, nested], "optional_field": None})

    result = to_json(obj)

    assert result["displayName"] == "Test Object"  # Alias used
    assert "display_name" not in result
    assert len(result["items"]) == 2
    assert result["items"][0]["color"] == "red"
    assert result["items"][0]["identifier"] == "12345678-1234-5678-1234-567812345678"
    assert isinstance(result["items"][0]["timestamp"], str)
    assert result["items"][0]["metadata"] == {"key": "value", "count": 42}
    assert result["optional_field"] is None


def test_dump_mcp_protocol_types():
    """Test serialization of actual MCP protocol types."""
    result = CallToolResult(
        content=[
            TextContent(type="text", text="Hello world"),
            ImageContent(type="image", data="base64data", mimeType="image/png"),
        ],
        isError=False,
    )

    dumped = to_json(result)

    assert dumped["isError"] is False
    assert len(dumped["content"]) == 2
    assert dumped["content"][0]["type"] == "text"
    assert dumped["content"][0]["text"] == "Hello world"
    assert dumped["content"][1]["type"] == "image"
    assert dumped["content"][1]["mimeType"] == "image/png"


def test_dump_error_data():
    """Test ErrorData serialization."""
    error = ErrorData(code=-32603, message="Internal error", data={"details": "failed"})

    result = to_json(error)

    assert result["code"] == -32603
    assert result["message"] == "Internal error"
    assert result["data"] == {"details": "failed"}


def test_dump_mixed_nested_structures():
    """Test complex nested structures mixing models, lists, dicts."""

    class Inner(BaseModel):
        value: int

    obj = {
        "models": [Inner(value=1), Inner(value=2)],
        "nested": {"items": [{"inner": Inner(value=3)}]},
        "primitive": 42,
    }

    result = to_json(obj)

    assert result["models"] == [{"value": 1}, {"value": 2}]
    assert result["nested"]["items"][0]["inner"] == {"value": 3}
    assert result["primitive"] == 42


def test_dump_embedded_resource():
    """Test EmbeddedResource serialization (complex MCP type)."""
    # EmbeddedResource expects TextResourceContents or BlobResourceContents, not TextContent
    from openmcp.types import TextResourceContents

    resource = EmbeddedResource(
        type="resource",
        resource=TextResourceContents(uri="file://test.txt", mimeType="text/plain", text="embedded content"),
    )

    result = to_json(resource)

    assert result["type"] == "resource"
    assert result["resource"]["uri"] == "file://test.txt/"  # Pydantic normalizes URIs
    assert result["resource"]["text"] == "embedded content"


def test_dump_none_values_preserved():
    """Test that None values are preserved in output."""

    class ModelWithNone(BaseModel):
        required: str
        optional: str | None = None

    obj = ModelWithNone(required="value", optional=None)
    result = to_json(obj)

    assert "optional" in result
    assert result["optional"] is None


def test_dump_empty_collections():
    """Test serialization of empty collections."""
    assert to_json([]) == []
    assert to_json({}) == {}
    # Note: sets are not directly JSON serializable and TypeAdapter doesn't handle them specially


def test_dump_by_alias_false():
    """Test serialization without aliases."""

    class AliasedModel(BaseModel):
        internal_name: str = Field(alias="externalName")

    obj = AliasedModel.model_validate({"externalName": "value"})
    result = to_json(obj, by_alias=False)

    assert result == {"internal_name": "value"}
    assert "externalName" not in result
