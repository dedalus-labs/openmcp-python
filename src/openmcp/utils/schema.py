# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Ensure JSON Schema values satisfy MCP's object-shaped contract.

The Model Context Protocol requires structured tool payloads to be JSON
objects.  This module keeps schema generation aligned with that rule by
delegating to Pydantic for canonical definitions, pruning cosmetic metadata,
and marking scalar boxing with a vendor extension that clients can reverse.
"""

from __future__ import annotations

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
    "enforce_strict_schema",
    "generate_schema_from_annotation",
    "ensure_object_schema",
    "unwrap_structured_content",
    "resolve_input_schema",
    "resolve_output_schema",
]


JsonSchema = JsonSchemaValue


_MISSING = object()

DEDALUS_BOX_KEY = "x-dedalus-box"
"""Vendor extension that records scalar boxing metadata."""


DEFAULT_WRAP_FIELD = "result"
"""Name of the object property used when auto-wrapping scalar schemas."""


class SchemaError(RuntimeError):
    """Raised when a schema cannot be generated or normalized."""


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
    return _coerce_envelope(
        annotation,
        wrap_scalar=wrap_scalar,
        wrap_field=wrap_field,
        mode=mode,
        compress=compress,
        drop_titles=drop_titles,
        relax_additional_properties=relax_additional_properties,
    )


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


def resolve_input_schema(schema_like: Any) -> JsonSchema:
    """Normalize user-provided input schema declarations.

    Args:
        schema_like: JSON Schema mapping, :class:`SchemaEnvelope`, or Python type.

    Returns:
        JsonSchema: Object schema suitable for MCP ``inputSchema``.

    Raises:
        SchemaError: If the schema cannot be interpreted as an object schema.

    """
    envelope = _coerce_envelope(
        schema_like, wrap_scalar=False, wrap_field=DEFAULT_WRAP_FIELD, mode="validation", compress=True
    )
    return envelope.schema


def resolve_output_schema(schema_like: Any) -> SchemaEnvelope:
    """Normalize user-provided output schema declarations.

    Args:
        schema_like: JSON Schema mapping, :class:`SchemaEnvelope`, or Python type.

    Returns:
        SchemaEnvelope: Schema annotated with boxing metadata for MCP outputs.

    Raises:
        SchemaError: If the schema cannot be derived.

    """
    return _coerce_envelope(
        schema_like, wrap_scalar=True, wrap_field=DEFAULT_WRAP_FIELD, mode="serialization", compress=True
    )


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
        marker: Vendor extension key signaling boxing.

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
        schema: JSON Schema to normalize.
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


def enforce_strict_schema(schema: JsonSchema) -> JsonSchema:
    """Return a schema compliant with strict MCP/LLM expectations.

    The transformation ensures object schemas explicitly forbid unknown
    properties, populates ``required`` lists, cleans up oneOf/anyOf usage, and
    strips ``None`` defaults that add no semantic value.

    Args:
        schema: JSON Schema to normalize strictly.

    Returns:
        JsonSchema: Strict schema suitable for contexts such as sampling or
        external transports that require explicit constraints.

    """
    if schema == {}:
        return {"type": "object", "additionalProperties": False, "properties": {}, "required": []}

    clone = _clone_schema(schema)
    _enforce_strict_schema(clone, root=clone, path=())
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
    """Remove ``field_name`` wherever it appears in ``node``.

    Args:
        node: Schema fragment to mutate.
        field_name: Property key to delete recursively.

    """
    if isinstance(node, MutableMapping):
        node.pop(field_name, None)
        for value in node.values():
            _strip_field(value, field_name)
    elif isinstance(node, list):
        for value in node:
            _strip_field(value, field_name)


def _relax_additional_properties(node: Any) -> None:
    """Drop ``additionalProperties: false`` from mapping nodes.

    Args:
        node: Schema fragment to mutate.

    """
    if isinstance(node, MutableMapping):
        if node.get("additionalProperties") is False:
            node.pop("additionalProperties")
        for value in node.values():
            _relax_additional_properties(value)
    elif isinstance(node, list):
        for value in node:
            _relax_additional_properties(value)


def _drop_top_level_property(schema: MutableMapping[str, Any], name: str) -> None:
    """Remove ``name`` from top-level ``properties`` and ``required`` lists.

    Args:
        schema: JSON Schema mapping to mutate in place.
        name: Property name to remove.

    """
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
    """Delete empty ``required`` arrays produced by pruning.

    Args:
        node: Schema fragment to inspect recursively.

    """
    if isinstance(node, MutableMapping):
        required = node.get("required")
        if isinstance(required, list) and not required:
            node.pop("required")
        for value in node.values():
            _prune_empty_required(value)
    elif isinstance(node, list):
        for value in node:
            _prune_empty_required(value)


def _coerce_envelope(
    schema_like: Any,
    *,
    wrap_scalar: bool,
    wrap_field: str,
    mode: JsonSchemaMode,
    compress: bool,
    drop_titles: bool = True,
    relax_additional_properties: bool = True,
) -> SchemaEnvelope:
    """Convert ``schema_like`` into a :class:`SchemaEnvelope`.

    Args:
        schema_like: Mapping, :class:`SchemaEnvelope`, or Python annotation.
        wrap_scalar: Whether to box scalars.
        wrap_field: Synthetic property name used when boxing occurs.
        mode: JSON Schema mode supplied to :class:`pydantic.TypeAdapter`.
        compress: Whether to remove cosmetic metadata.
        drop_titles: Remove ``title`` fields during compression.
        relax_additional_properties: Drop ``additionalProperties: false``.

    Returns:
        SchemaEnvelope: Normalized schema envelope.

    Raises:
        SchemaError: If the schema cannot be derived.

    """
    if isinstance(schema_like, SchemaEnvelope):
        base_schema = (
            compress_schema(
                schema_like.schema, drop_titles=drop_titles, relax_additional_properties=relax_additional_properties
            )
            if compress
            else _clone_schema(schema_like.schema)
        )

        if schema_like.wrap_field is None and not _describes_object(base_schema):
            if not wrap_scalar:
                raise SchemaError(
                    "Schema describes a non-object value. Set wrap_scalar=True to comply with MCP output rules."
                )
            return ensure_object_schema(base_schema, wrap_scalar=True, wrap_field=wrap_field)

        return SchemaEnvelope(schema=base_schema, wrap_field=schema_like.wrap_field)

    if isinstance(schema_like, Mapping):
        base_schema = (
            compress_schema(
                schema_like, drop_titles=drop_titles, relax_additional_properties=relax_additional_properties
            )
            if compress
            else _clone_schema(schema_like)
        )
        return ensure_object_schema(base_schema, wrap_scalar=wrap_scalar, wrap_field=wrap_field)

    try:
        type_adapter = TypeAdapter(schema_like)
    except Exception as exc:  # pragma: no cover - surface original failure
        raise SchemaError(f"Unable to create TypeAdapter for {schema_like!r}") from exc

    try:
        base_schema = type_adapter.json_schema(mode=mode)
    except Exception as exc:  # pragma: no cover - surface original failure
        raise SchemaError(f"Unable to derive JSON schema for {schema_like!r}") from exc

    if compress:
        base_schema = compress_schema(
            base_schema, drop_titles=drop_titles, relax_additional_properties=relax_additional_properties
        )

    return ensure_object_schema(base_schema, wrap_scalar=wrap_scalar, wrap_field=wrap_field)


def _enforce_strict_schema(node: JsonSchema, *, root: JsonSchema, path: tuple[str, ...]) -> JsonSchema:
    """Recursively enforce strict JSON Schema semantics via depth-first search.

    Args:
        node: Schema fragment being inspected.
        root: Top-level schema for resolving references.
        path: Tuple representing the traversal path for diagnostics.

    Returns:
        JsonSchema: Strict schema node.

    Raises:
        SchemaError: If the schema fragment violates strict requirements.

    """
    if not isinstance(node, MutableMapping):
        raise SchemaError(f"Expected mapping for schema node; path={'/'.join(path)}")

    defs = node.get("$defs")
    if isinstance(defs, MutableMapping):
        for name, sub in defs.items():
            _enforce_strict_schema(sub, root=root, path=(*path, "$defs", name))

    definitions = node.get("definitions")
    if isinstance(definitions, MutableMapping):
        for name, sub in definitions.items():
            _enforce_strict_schema(sub, root=root, path=(*path, "definitions", name))

    type_hint = node.get("type")
    if type_hint == "object":
        if node.get("additionalProperties") is None:
            node["additionalProperties"] = False
        elif node.get("additionalProperties") not in (False,):
            raise SchemaError(f"Strict schema forbids additionalProperties other than False; path={'/'.join(path)}")

    properties = node.get("properties")
    if isinstance(properties, MutableMapping):
        node["required"] = list(properties.keys())
        for key, sub in properties.items():
            _enforce_strict_schema(sub, root=root, path=(*path, "properties", key))

    items = node.get("items")
    if isinstance(items, MutableMapping):
        node["items"] = _enforce_strict_schema(items, root=root, path=(*path, "items"))

    any_of = node.get("anyOf")
    if isinstance(any_of, list):
        node["anyOf"] = [
            _enforce_strict_schema(entry, root=root, path=(*path, "anyOf", str(i))) for i, entry in enumerate(any_of)
        ]

    one_of = node.get("oneOf")
    if isinstance(one_of, list):
        existing_any_of = node.get("anyOf")
        if not isinstance(existing_any_of, list):
            existing_any_of = []
        node["anyOf"] = existing_any_of + [
            _enforce_strict_schema(entry, root=root, path=(*path, "oneOf", str(i))) for i, entry in enumerate(one_of)
        ]
        node.pop("oneOf")

    all_of = node.get("allOf")
    if isinstance(all_of, list):
        if len(all_of) == 1:
            merged = _enforce_strict_schema(all_of[0], root=root, path=(*path, "allOf", "0"))
            node.pop("allOf")
            node.update({k: v for k, v in merged.items() if k != "$defs"})
        else:
            node["allOf"] = [
                _enforce_strict_schema(entry, root=root, path=(*path, "allOf", str(i)))
                for i, entry in enumerate(all_of)
            ]

    default = node.get("default", _MISSING)
    if default is None:
        node.pop("default", None)

    ref = node.get("$ref")
    if isinstance(ref, str) and len(node) > 1:
        resolved = _resolve_ref(root=root, ref=ref)
        if not isinstance(resolved, MutableMapping):
            raise SchemaError(f"Ref {ref!r} did not resolve to an object; path={'/'.join(path)}")
        node.update({k: v for k, v in resolved.items() if k != "$ref"})
        node.pop("$ref", None)
        return _enforce_strict_schema(node, root=root, path=path)

    return node


def _resolve_ref(*, root: Mapping[str, Any], ref: str) -> JsonSchema:
    """Resolve a ``$ref`` pointer against ``root``.

    Args:
        root: Schema root containing definitions.
        ref: JSON Pointer-style reference (``#/...``).

    Returns:
        JsonSchema: Referenced schema fragment.

    Raises:
        SchemaError: If the reference cannot be resolved to a mapping.

    """
    if not ref.startswith("#/"):
        raise SchemaError(f"Unexpected $ref format {ref!r}")

    target: JsonSchema | Mapping[str, Any] = root
    for part in ref[2:].split("/"):
        if not isinstance(target, Mapping) or part not in target:
            raise SchemaError(f"Unable to resolve $ref {ref!r} at {part!r}")
        target = target[part]  # type: ignore[index]
    if not isinstance(target, Mapping):
        raise SchemaError(f"Resolved $ref {ref!r} to non-mapping node {target!r}")
    return target
