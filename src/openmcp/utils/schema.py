"""Ensure JSON Schema values satisfy MCP's object-shaped contract.

The Model Context Protocol requires structured tool payloads to be JSON
objects.  This module keeps schema generation aligned with that rule by
delegating to Pydantic for canonical definitions, pruning cosmetic metadata,
and marking scalar boxing with a vendor extension that clients can reverse.
"""

from collections.abc import Iterable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any

from pydantic import TypeAdapter
from pydantic.json_schema import JsonSchemaMode, JsonSchemaValue


__all__ = [
    "JsonSchema",
    "SchemaError",
    "SchemaEnvelope",
    "DEDALUS_BOX_KEY",
    "DEFAULT_WRAP_FIELD",
    "compress_schema",
    "generate_schema_from_annotation",
    "ensure_object_schema",
    "unwrap_structured_content",
]


JsonSchema = JsonSchemaValue


DEDALUS_BOX_KEY = "x-dedalus-box"
"""Vendor extension that records scalar boxing metadata."""


DEFAULT_WRAP_FIELD = "result"
"""Name of the object property used when auto-wrapping scalar schemas."""


class SchemaError(RuntimeError):
    """Raised when a schema cannot be generated or normalised."""


@dataclass(frozen=True, slots=True)
class SchemaEnvelope:
    """Describe how a JSON Schema aligns with MCP structured content.

    Attributes:
        schema: JSON Schema value, treated as immutable data.
        wrap_field: Name of the boxed scalar field, or ``None`` when the schema
            already describes an object.

    """

    schema: JsonSchema
    wrap_field: str | None = None

    @property
    def is_wrapped(self) -> bool:
        """Return whether the envelope records a boxed scalar.

        Returns:
            bool: ``True`` when :attr:`wrap_field` is not ``None``.

        """
        return self.wrap_field is not None

    def unwrap(self, structured_content: Mapping[str, Any]) -> Any:
        """Recover the original value from structured content.

        Args:
            structured_content: Mapping returned in
                :attr:`CallToolResult.structuredContent`.

        Returns:
            Any: Original scalar or mapping provided by the tool.

        Raises:
            SchemaError: If the structured content conflicts with the recorded
                boxing metadata.

        """
        if not self.is_wrapped:
            return structured_content

        if not isinstance(structured_content, Mapping):  # pragma: no cover - defensive
            raise SchemaError("Structured content must be a mapping when using an auto-wrapped schema.")

        try:
            return structured_content[self.wrap_field]  # type: ignore[index]
        except KeyError as exc:  # pragma: no cover - defensive
            raise SchemaError(f"Expected wrapped result to contain '{self.wrap_field}'") from exc

    def wrap(self, value: Any) -> Mapping[str, Any]:
        """Box ``value`` into the MCP structured-content envelope.

        Args:
            value: Original scalar or mapping.

        Returns:
            Mapping[str, Any]: Transport-ready payload.

        Raises:
            SchemaError: If the envelope records no boxing yet ``value`` is not
                a mapping.

        """
        if not self.is_wrapped:
            if isinstance(value, Mapping):
                return value
            raise SchemaError("Wrapped value must be a mapping when no synthetic wrapper is present.")
        return {self.wrap_field: value}


def generate_schema_from_annotation(
    annotation: Any,
    *,
    mode: JsonSchemaMode = "serialization",
    wrap_scalar: bool = True,
    wrap_field: str = DEFAULT_WRAP_FIELD,
    compress: bool = True,
    drop_titles: bool = True,
    relax_additional_properties: bool = True,
) -> SchemaEnvelope:
    """Build a schema envelope from a Python annotation.

    Args:
        annotation: Object understood by :class:`pydantic.TypeAdapter`.
        mode: JSON Schema generation mode.
        wrap_scalar: Whether non-object schemas should be boxed automatically.
        wrap_field: Synthetic property name used when boxing occurs.
        compress: Whether to remove cosmetic metadata.
        drop_titles: Remove ``title`` fields when compression is enabled.
        relax_additional_properties: Replace ``additionalProperties: false``
            with a permissive default when compression is enabled.

    Returns:
        SchemaEnvelope: Schema information aligned with MCP transport rules.

    Raises:
        SchemaError: If :class:`pydantic.TypeAdapter` cannot derive a schema.

    """
    try:
        schema = TypeAdapter(annotation).json_schema(mode=mode)
    except Exception as exc:  # pragma: no cover - surface the original failure
        raise SchemaError(f"Unable to derive JSON schema for {annotation!r}") from exc

    if compress:
        schema = compress_schema(
            schema, drop_titles=drop_titles, relax_additional_properties=relax_additional_properties
        )

    return ensure_object_schema(schema, wrap_scalar=wrap_scalar, wrap_field=wrap_field)


def ensure_object_schema(
    schema: JsonSchema, *, wrap_scalar: bool = True, wrap_field: str = DEFAULT_WRAP_FIELD, marker: str = DEDALUS_BOX_KEY
) -> SchemaEnvelope:
    """Guarantee that ``schema`` can travel over MCP as an object.

    Args:
        schema: JSON Schema to inspect.
        wrap_scalar: Whether to box non-object schemas.
        wrap_field: Property name used when boxing.
        marker: Vendor extension recording boxing metadata.

    Returns:
        SchemaEnvelope: Schema aligned with MCP output rules.

    Raises:
        SchemaError: If boxing is disabled and ``schema`` is non-object.

    """
    if _describes_object(schema):
        return SchemaEnvelope(schema=_clone_schema(schema))

    if not wrap_scalar:
        raise SchemaError("Schema describes a non-object value. Set wrap_scalar=True to comply with MCP output rules.")

    wrapped: JsonSchema = {
        "type": "object",
        "properties": {wrap_field: _clone_schema(schema)},
        "required": [wrap_field],
        "additionalProperties": False,
        marker: {"field": wrap_field},
    }
    return SchemaEnvelope(schema=wrapped, wrap_field=wrap_field)


def unwrap_structured_content(
    structured_content: Mapping[str, Any] | None,
    schema: Mapping[str, Any] | SchemaEnvelope,
    *,
    marker: str = DEDALUS_BOX_KEY,
) -> Any:
    """Reverse the boxing step recorded in a schema envelope.

    Args:
        structured_content: Payload returned by the remote tool.
        schema: Raw JSON Schema or :class:`SchemaEnvelope` describing boxing.
        marker: Vendor extension key signalling boxing.

    Returns:
        Any: Unboxed value.

    """
    if structured_content is None:
        return None

    envelope = schema if isinstance(schema, SchemaEnvelope) else _envelope_from_schema(schema, marker)
    return envelope.unwrap(structured_content)


def compress_schema(
    schema: JsonSchema,
    *,
    drop_titles: bool = True,
    relax_additional_properties: bool = True,
    prune_parameters: Iterable[str] | None = None,
) -> JsonSchema:
    """Return a structurally equivalent schema with cosmetic noise removed.

    Args:
        schema: JSON Schema to normalise.
        drop_titles: Remove ``title`` keys recursively.
        relax_additional_properties: Drop ``additionalProperties: false``.
        prune_parameters: Parameter names to delete from the top level.

    Returns:
        JsonSchema: Cleaned schema.

    """
    clone = _clone_schema(schema)

    if drop_titles:
        _strip_field(clone, "title")

    if relax_additional_properties:
        _relax_additional_properties(clone)

    if prune_parameters:
        for param in prune_parameters:
            _drop_top_level_property(clone, param)

    _prune_empty_required(clone)
    return clone


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _clone_schema(schema: JsonSchema) -> JsonSchema:
    """Return a deep copy of ``schema``.

    Returns:
        JsonSchema: Deep copy of the input schema.

    """
    if isinstance(schema, dict):
        return {k: _clone_schema(v) for k, v in schema.items()}
    if isinstance(schema, list):
        return [_clone_schema(item) for item in schema]
    return schema


def _describes_object(schema: Mapping[str, Any]) -> bool:
    """Return whether ``schema`` already encodes an object shape.

    Returns:
        bool: ``True`` when the schema includes object keywords.

    """

    if schema.get("type") == "object":
        return True
    return any(
        key in schema
        for key in ("properties", "patternProperties", "additionalProperties", "propertyNames", "dependentRequired")
    )


def _envelope_from_schema(schema: Mapping[str, Any], marker: str) -> SchemaEnvelope:
    """Construct an envelope from vendor metadata stored in ``schema``.

    Returns:
        SchemaEnvelope: Envelope reconstructed from raw schema.

    """

    wrap_field: str | None = None
    metadata = schema.get(marker)
    if isinstance(metadata, Mapping):
        wrap_field = str(metadata.get("field", DEFAULT_WRAP_FIELD))
    elif metadata:
        wrap_field = DEFAULT_WRAP_FIELD
    if wrap_field is not None:
        properties = schema.get("properties")
        if isinstance(properties, Mapping) and wrap_field not in properties:
            wrap_field = next(iter(properties.keys()), wrap_field)
    return SchemaEnvelope(schema=_clone_schema(schema), wrap_field=wrap_field)


def _strip_field(node: Any, field_name: str) -> None:
    """Remove ``field_name`` wherever it appears in ``node``."""

    if isinstance(node, MutableMapping):
        node.pop(field_name, None)
        for value in node.values():
            _strip_field(value, field_name)
    elif isinstance(node, list):
        for value in node:
            _strip_field(value, field_name)


def _relax_additional_properties(node: Any) -> None:
    """Drop ``additionalProperties: false`` from mapping nodes."""

    if isinstance(node, MutableMapping):
        if node.get("additionalProperties") is False:
            node.pop("additionalProperties")
        for value in node.values():
            _relax_additional_properties(value)
    elif isinstance(node, list):
        for value in node:
            _relax_additional_properties(value)


def _drop_top_level_property(schema: MutableMapping[str, Any], name: str) -> None:
    """Remove ``name`` from top-level ``properties`` and ``required`` lists."""

    properties = schema.get("properties")
    if isinstance(properties, MutableMapping):
        properties.pop(name, None)
        if not properties:
            schema.pop("properties")

    required = schema.get("required")
    if isinstance(required, list) and name in required:
        required = [item for item in required if item != name]
        if required:
            schema["required"] = required
        else:
            schema.pop("required")


def _prune_empty_required(node: Any) -> None:
    """Delete empty ``required`` arrays produced by pruning."""
    if isinstance(node, MutableMapping):
        required = node.get("required")
        if isinstance(required, list) and not required:
            node.pop("required")
        for value in node.values():
            _prune_empty_required(value)
    elif isinstance(node, list):
        for value in node:
            _prune_empty_required(value)
