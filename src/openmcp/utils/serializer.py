# ==============================================================================
#                  © 2025 Dedalus Labs, Inc. and affiliates
#                            Licensed under MIT
#               github.com/dedalus-labs/openmcp-python/LICENSE
# ==============================================================================

"""JSON serialization utilities for MCP protocol types.

This module provides utilities for converting Pydantic models and other Python
types into JSON-serializable structures, particularly for dumping MCP protocol
messages to JSON.
"""

from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

# Universal serializer that handles any nested combination of:
# - Pydantic models
# - Lists, dicts, tuples
# - Enums, datetimes, UUIDs
# - Primitives (str, int, bool, None)
_json_adapter: TypeAdapter[Any] = TypeAdapter(Any)


def to_json(obj: Any, *, by_alias: bool = True) -> Any:
    """Convert any object to a JSON-serializable structure.

    This function recursively converts Pydantic models, nested structures,
    and complex types into primitive Python types suitable for JSON serialization.

    Args:
        obj: Object to serialize (Pydantic model, dict, list, or primitive)
        by_alias: Use field aliases from Pydantic models (default: True)

    Returns:
        JSON-serializable structure (dict, list, str, int, bool, None)

    Example:
        >>> from openmcp.types import CallToolResult, TextContent
        >>> result = CallToolResult(content=[TextContent(type="text", text="hello")])
        >>> to_json(result)
        {'content': [{'type': 'text', 'text': 'hello'}], 'isError': False, ...}
    """
    return _json_adapter.dump_python(obj, mode="json", by_alias=by_alias)


__all__ = ["to_json"]
