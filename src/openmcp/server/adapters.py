# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""Normalization helpers for server-facing handler results.

The adapters keep the capability services thin while ensuring all outbound
responses conform to the structures defined in the MCP specification.

Spec receipts referenced here:

* ``docs/mcp/spec/schema-reference/tools-call.md``
* ``docs/mcp/spec/schema-reference/resources-read.md``
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from dataclasses import asdict, is_dataclass
import json
from typing import Any

from .. import types


try:  # pragma: no cover - optional import when pydantic is present
    from pydantic import BaseModel
except Exception:  # pragma: no cover - fall back if the import path changes
    BaseModel = None

__all__ = ["normalize_tool_result", "normalize_resource_payload"]


_CONTENT_CLASSES = (
    types.TextContent,
    types.ImageContent,
    types.AudioContent,
    types.ResourceLink,
    types.EmbeddedResource,
)

_JSONIFY_SENTINEL = object()


def normalize_tool_result(value: Any) -> types.CallToolResult:
    """Coerce arbitrary tool handler output into ``CallToolResult``."""
    if isinstance(value, types.CallToolResult):
        return value

    if isinstance(value, dict) and any(
        key in value for key in ("content", "structuredContent", "isError", "_meta", "meta")
    ):
        try:
            return types.CallToolResult(**value)
        except Exception:  # pragma: no cover - defensive; fallback to generic path
            pass

    if is_dataclass(value):
        value = asdict(value)
    elif BaseModel and isinstance(value, BaseModel) and not isinstance(value, _CONTENT_CLASSES):
        value = value.model_dump(mode="json")

    structured: Any | None = None
    payload = value

    if isinstance(value, tuple) and len(value) == 2:
        payload, structured = value
    elif isinstance(value, dict):
        structured = value

    json_ready = _jsonify(payload)
    if structured is None and json_ready is not _JSONIFY_SENTINEL:
        structured = json_ready if isinstance(json_ready, dict) else {"result": json_ready}

    content_blocks = _coerce_content_blocks(payload)

    result_payload: dict[str, Any] = {"content": content_blocks}
    if structured is not None:
        result_payload["structuredContent"] = structured
    return types.CallToolResult(**result_payload)


def _coerce_content_blocks(source: Any) -> list[types.ContentBlock]:
    if source is None:
        return []

    if is_dataclass(source):
        source = asdict(source)
    elif BaseModel and isinstance(source, BaseModel) and not isinstance(source, _CONTENT_CLASSES):
        source = source.model_dump(mode="json")

    if isinstance(source, types.ContentBlock):
        return [source]

    if isinstance(source, dict):
        block = _content_from_mapping(source)
        return [block] if block is not None else [_as_text_content(source)]

    if isinstance(source, (bytes, bytearray)):
        encoded = base64.b64encode(bytes(source)).decode("ascii")
        return [types.TextContent(type="text", text=encoded)]

    if isinstance(source, str):
        return [types.TextContent(type="text", text=source)]

    if isinstance(source, Iterable):
        blocks: list[types.ContentBlock] = []
        for item in source:
            blocks.extend(_coerce_content_blocks(item))
        return blocks

    return [_as_text_content(source)]


def _content_from_mapping(data: dict[str, Any]) -> types.ContentBlock | None:
    marker = data.get("type")
    if marker is None:
        return None
    try:
        return types.ContentBlock.model_validate(data)
    except Exception:
        return None


def _as_text_content(value: Any) -> types.TextContent:
    if isinstance(value, types.TextContent):
        return value
    if isinstance(value, str):
        return types.TextContent(type="text", text=value)
    json_ready = _jsonify(value)
    if json_ready is _JSONIFY_SENTINEL:
        text = str(value)
    else:
        text = json.dumps(json_ready, ensure_ascii=False)
    return types.TextContent(type="text", text=text)


def normalize_resource_payload(uri: str, declared_mime: str | None, payload: Any) -> types.ReadResourceResult:
    """Coerce resource handler output into ``ReadResourceResult``."""
    if isinstance(payload, types.ReadResourceResult):
        return payload

    if isinstance(payload, (types.TextResourceContents, types.BlobResourceContents)):
        return types.ReadResourceResult(contents=[payload])

    if isinstance(payload, list) and all(
        isinstance(item, (types.TextResourceContents, types.BlobResourceContents)) for item in payload
    ):
        return types.ReadResourceResult(contents=payload)

    if is_dataclass(payload):
        payload = asdict(payload)
    elif BaseModel and isinstance(payload, BaseModel) and not isinstance(payload, _CONTENT_CLASSES):
        payload = payload.model_dump(mode="json")

    if isinstance(payload, dict):
        try:
            content = types.TextResourceContents.model_validate({"uri": uri, **payload})
            return types.ReadResourceResult(contents=[content])
        except Exception:
            try:
                content = types.BlobResourceContents.model_validate({"uri": uri, **payload})
                return types.ReadResourceResult(contents=[content])
            except Exception:
                pass

    if isinstance(payload, (bytes, bytearray)):
        mime = declared_mime or "application/octet-stream"
        encoded = base64.b64encode(bytes(payload)).decode("ascii")
        blob = types.BlobResourceContents(uri=uri, mimeType=mime, blob=encoded)
        return types.ReadResourceResult(contents=[blob])

    mime = declared_mime or "text/plain"
    if isinstance(payload, str):
        text = payload
    else:
        json_ready = _jsonify(payload)
        if json_ready is _JSONIFY_SENTINEL:
            text = str(payload)
        else:
            text = json.dumps(json_ready, ensure_ascii=False)
    return types.ReadResourceResult(contents=[types.TextResourceContents(uri=uri, mimeType=mime, text=text)])


def _jsonify(value: Any, _depth: int = 0) -> Any:
    """Recursively convert value to JSON-compatible types.

    Args:
        value: The value to convert
        _depth: Internal recursion depth counter (max 100)

    Returns:
        JSON-compatible value or _JSONIFY_SENTINEL if not convertible
    """
    if _depth > 100:
        return _JSONIFY_SENTINEL

    if is_dataclass(value):
        value = asdict(value)
    elif BaseModel and isinstance(value, BaseModel) and not isinstance(value, _CONTENT_CLASSES):
        value = value.model_dump(mode="json")

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, sub in value.items():
            json_sub = _jsonify(sub, _depth + 1)
            if json_sub is _JSONIFY_SENTINEL:
                return _JSONIFY_SENTINEL
            result[str(key)] = json_sub
        return result

    if isinstance(value, (list, tuple, set)):
        result_list: list[Any] = []
        for item in value:
            json_item = _jsonify(item, _depth + 1)
            if json_item is _JSONIFY_SENTINEL:
                return _JSONIFY_SENTINEL
            result_list.append(json_item)
        return result_list

    return _JSONIFY_SENTINEL
