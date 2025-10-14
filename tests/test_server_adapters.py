from __future__ import annotations

import base64

from openmcp import types
from openmcp.server.adapters import normalize_resource_payload, normalize_tool_result


def test_normalize_tool_result_from_string() -> None:
    result = normalize_tool_result("hello")
    assert isinstance(result, types.CallToolResult)
    assert result.content and result.content[0].text == "hello"
    assert result.structuredContent is None


def test_normalize_tool_result_with_structured_tuple() -> None:
    structured = {"foo": "bar"}
    result = normalize_tool_result(("hi", structured))
    assert result.structuredContent == structured
    assert result.content[0].text == "hi"


def test_normalize_tool_result_from_dict_payload() -> None:
    payload = {
        "content": [types.TextContent(type="text", text="ok")],
        "structuredContent": {"status": "fine"},
        "isError": False,
    }
    result = normalize_tool_result(payload)
    assert isinstance(result, types.CallToolResult)
    assert result.content[0].text == "ok"
    assert result.structuredContent == {"status": "fine"}


def test_normalize_resource_payload_bytes() -> None:
    data = b"\x00\x01demo"
    result = normalize_resource_payload("resource://demo/blob", "application/octet-stream", data)
    assert isinstance(result, types.ReadResourceResult)
    content = result.contents[0]
    assert isinstance(content, types.BlobResourceContents)
    assert content.mimeType == "application/octet-stream"
    assert base64.b64decode(content.blob) == data


def test_normalize_resource_payload_text_default_mime() -> None:
    result = normalize_resource_payload("resource://demo/text", None, "hello")
    content = result.contents[0]
    assert isinstance(content, types.TextResourceContents)
    assert content.mimeType == "text/plain"
    assert content.text == "hello"


def test_normalize_resource_payload_passthrough() -> None:
    existing = types.ReadResourceResult(
        contents=[types.TextResourceContents(uri="resource://demo/ready", mimeType="text/plain", text="ok")]
    )
    assert normalize_resource_payload("resource://demo/ready", None, existing) is existing
