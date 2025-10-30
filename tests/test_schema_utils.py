# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

from __future__ import annotations

import copy
from dataclasses import dataclass

from pydantic import BaseModel
import pytest

from openmcp.tool import extract_tool_spec, tool
from openmcp.utils.schema import (
    DEDALUS_BOX_KEY,
    DEFAULT_WRAP_FIELD,
    SchemaEnvelope,
    SchemaError,
    compress_schema,
    enforce_strict_schema,
    ensure_object_schema,
    generate_schema_from_annotation,
    resolve_input_schema,
    resolve_output_schema,
    unwrap_structured_content,
)


class TestSchemaEnvelope:
    def test_wrap_and_unwrap_boxed_scalar(self) -> None:
        envelope = SchemaEnvelope(
            schema={
                "type": "object",
                "properties": {DEFAULT_WRAP_FIELD: {"type": "number"}},
                "required": [DEFAULT_WRAP_FIELD],
            },
            wrap_field=DEFAULT_WRAP_FIELD,
        )

        boxed = envelope.wrap(3.14)
        assert boxed == {DEFAULT_WRAP_FIELD: 3.14}
        assert envelope.unwrap(boxed) == 3.14

    def test_wrap_and_unwrap_passthrough_mapping(self) -> None:
        payload = {"name": "openmcp"}
        envelope = SchemaEnvelope(schema={"type": "object"})

        assert envelope.wrap(payload) is payload
        assert envelope.unwrap(payload) is payload

    def test_unwrap_missing_box_field_raises(self) -> None:
        envelope = SchemaEnvelope(
            schema={"type": "object", "properties": {"value": {"type": "integer"}}, "required": ["value"]},
            wrap_field="value",
        )

        with pytest.raises(SchemaError):
            envelope.unwrap({})


class TestSchemaGeneration:
    def test_generate_schema_wraps_scalar_annotation(self) -> None:
        envelope = generate_schema_from_annotation(int)

        assert envelope.is_wrapped
        assert envelope.wrap_field == DEFAULT_WRAP_FIELD

        schema = envelope.schema
        assert schema["type"] == "object"
        assert schema["properties"][DEFAULT_WRAP_FIELD]["type"] == "integer"
        assert schema[DEDALUS_BOX_KEY]["field"] == DEFAULT_WRAP_FIELD

    def test_generate_schema_preserves_object_annotation(self) -> None:
        envelope = generate_schema_from_annotation(dict[str, int])

        assert not envelope.is_wrapped
        assert envelope.schema["type"] == "object"

    def test_generate_schema_for_dataclass_round_trip(self) -> None:
        @dataclass
        class Settings:
            flag: bool
            retries: int = 1

        envelope = generate_schema_from_annotation(Settings)

        assert not envelope.is_wrapped
        schema = envelope.schema
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"flag", "retries"}
        assert schema["required"] == ["flag"]

    def test_ensure_object_schema_refuses_unwrapped_scalars(self) -> None:
        with pytest.raises(SchemaError):
            ensure_object_schema({"type": "number"}, wrap_scalar=False)


class TestStructuredContent:
    def test_unwrap_structured_content_with_marker(self) -> None:
        schema = {
            "type": "object",
            "properties": {DEFAULT_WRAP_FIELD: {"type": "integer"}},
            "required": [DEFAULT_WRAP_FIELD],
            DEDALUS_BOX_KEY: {"field": DEFAULT_WRAP_FIELD},
        }

        value = unwrap_structured_content({DEFAULT_WRAP_FIELD: 7}, schema)
        assert value == 7

    def test_unwrap_structured_content_none_passthrough(self) -> None:
        assert unwrap_structured_content(None, {}) is None

    def test_unwrap_with_schema_envelope_instance(self) -> None:
        envelope = SchemaEnvelope(
            schema={
                "type": "object",
                "properties": {DEFAULT_WRAP_FIELD: {"type": "string"}},
                "required": [DEFAULT_WRAP_FIELD],
                DEDALUS_BOX_KEY: {"field": DEFAULT_WRAP_FIELD},
            },
            wrap_field=DEFAULT_WRAP_FIELD,
        )

        assert unwrap_structured_content({DEFAULT_WRAP_FIELD: "done"}, envelope) == "done"


class TestCompressSchema:
    def test_compress_schema_prunes_metadata_and_defaults(self) -> None:
        original = {
            "type": "object",
            "title": "Example",
            "properties": {"ctx": {"type": "string"}, "name": {"type": "string", "title": "Name"}},
            "required": ["ctx", "name"],
            "additionalProperties": False,
        }

        before = copy.deepcopy(original)
        compressed = compress_schema(original, prune_parameters=["ctx"])

        # Original is untouched.
        assert original == before

        assert "title" not in compressed
        assert compressed["properties"] == {"name": {"type": "string"}}
        assert compressed["required"] == ["name"]
        assert "additionalProperties" not in compressed


class TestSchemaResolution:
    def test_resolve_input_schema_from_dataclass(self) -> None:
        @dataclass
        class Args:
            path: str
            count: int

        resolved = resolve_input_schema(Args)
        assert resolved["type"] == "object"
        assert set(resolved["properties"]) == {"path", "count"}

    def test_resolve_output_schema_from_model(self) -> None:
        class Payload(BaseModel):
            ok: bool

        envelope = resolve_output_schema(Payload)
        assert not envelope.is_wrapped
        assert envelope.schema["type"] == "object"
        assert set(envelope.schema["properties"]) == {"ok"}

    def test_resolve_output_schema_preserves_boxing(self) -> None:
        original = generate_schema_from_annotation(str)
        assert original.is_wrapped

        resolved = resolve_output_schema(original)

        assert resolved.is_wrapped
        assert resolved.wrap_field == original.wrap_field
        assert resolved.schema["properties"] == original.schema["properties"]
        assert resolved.schema["required"] == original.schema["required"]
        assert resolved.schema.get(DEDALUS_BOX_KEY) == original.schema.get(DEDALUS_BOX_KEY)
        assert resolved.schema["type"] == "object"

    def test_resolve_input_schema_rejects_scalar(self) -> None:
        with pytest.raises(SchemaError):
            resolve_input_schema(int)


class TestEnforceStrictSchema:
    def test_enforce_strict_sets_required_and_ap(self) -> None:
        schema = {"type": "object", "properties": {"a": {"type": "string"}, "b": {"type": "integer", "default": None}}}

        strict = enforce_strict_schema(schema)
        assert strict["additionalProperties"] is False
        assert strict["required"] == ["a", "b"]
        assert "default" not in strict["properties"]["b"]

    def test_enforce_strict_rejects_permissive_additional_properties(self) -> None:
        schema = {"type": "object", "additionalProperties": True}
        with pytest.raises(SchemaError):
            enforce_strict_schema(schema)

    def test_enforce_strict_inlines_single_ref(self) -> None:
        schema = {
            "$ref": "#/$defs/X",
            "description": "example",
            "$defs": {"X": {"type": "object", "properties": {"field": {"type": "string"}}}},
            "definitions": {"Y": {"type": "object", "properties": {"other": {"type": "integer"}}}},
        }

        strict = enforce_strict_schema(schema)
        assert strict["type"] == "object"
        assert strict["additionalProperties"] is False
        assert "field" in strict["properties"]
        assert "$ref" not in strict


class TestToolDecoratorIntegration:
    def test_tool_accepts_class_schemas(self) -> None:
        @dataclass
        class InputArgs:
            query: str

        class OutputModel(BaseModel):
            status: str

        @tool(input_schema=InputArgs, output_schema=OutputModel)
        def sample_tool(query: InputArgs) -> OutputModel:  # type: ignore[override]
            return OutputModel(status=query.query)

        spec = extract_tool_spec(sample_tool)
        assert spec is not None
        assert spec.input_schema and spec.input_schema["type"] == "object"
        assert spec.output_schema and spec.output_schema["type"] == "object"

    def test_tool_rejects_scalar_input_schema(self) -> None:
        with pytest.raises(SchemaError):

            @tool(input_schema=int)
            def invalid_tool(value: int) -> None:  # type: ignore[empty-body]
                pass
