"""Normalization helpers for server-facing handler results.

The adapters keep the capability services thin while ensuring all outbound
responses conform to the structures defined in the MCP specification.

Spec receipts referenced here:

* ``docs/mcp/spec/schema-reference/tools-call.md``
* ``docs/mcp/spec/schema-reference/resources-read.md``
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterable
from typing import Any

from .. import types

__all__ = ["normalize_tool_result", "normalize_resource_payload"]


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

    structured: Any | None = None
    payload = value

    if isinstance(value, tuple) and len(value) == 2:
        payload, structured = value
    elif isinstance(value, dict):
        structured = value

    content_blocks = _coerce_content_blocks(payload)

    result_payload: dict[str, Any] = {"content": content_blocks}
    if structured is not None:
        result_payload["structuredContent"] = structured
    return types.CallToolResult(**result_payload)


def _coerce_content_blocks(source: Any) -> list[types.ContentBlock]:
    if source is None:
        return []

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
    try:
        text = json.dumps(value, ensure_ascii=False)
    except Exception:
        text = str(value)
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
    text = str(payload)
    return types.ReadResourceResult(
        contents=[types.TextResourceContents(uri=uri, mimeType=mime, text=text)]
    )
