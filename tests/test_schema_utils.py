import copy

import pytest

from dataclasses import dataclass

from openmcp.utils.schema import (
    DEDALUS_BOX_KEY,
    DEFAULT_WRAP_FIELD,
    SchemaEnvelope,
    SchemaError,
    compress_schema,
    ensure_object_schema,
    generate_schema_from_annotation,
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
            schema={
                "type": "object",
                "properties": {"value": {"type": "integer"}},
                "required": ["value"],
            },
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
            "properties": {
                "ctx": {"type": "string"},
                "name": {"type": "string", "title": "Name"},
            },
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
