# Result Normalization

**DRAFT**: This documentation describes result normalization as currently implemented. API surface may change before public release.

**Problem**: Tool and resource handlers can return diverse Python types—dataclasses, Pydantic models, dicts, scalars, tuples, bytes—but the MCP specification requires structured responses (`CallToolResult` for tools, `ReadResourceResult` for resources) with specific content encoding. Forcing every handler to manually construct these wrapper types creates boilerplate and inconsistency.

**Solution**: OpenMCP normalizers automatically coerce arbitrary handler return values into spec-compliant result types. Tool handlers can return anything; the normalizer produces `CallToolResult` with both human-readable `content` blocks and machine-parseable `structuredContent`. Resource handlers return text or binary data; the normalizer produces `ReadResourceResult` with appropriate MIME types and encoding.

**OpenMCP**: Two core functions—`normalize_tool_result()` and `normalize_resource_payload()`—handle all coercion logic. They convert typed objects to JSON-compatible structures, generate content blocks, infer MIME types, and ensure results always conform to the MCP specification.

## Specification

Tool result normalization aligns with:
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools (tools/call result structure)

Resource result normalization aligns with:
- https://modelcontextprotocol.io/specification/2025-06-18/server/resources (resources/read result structure)

Key characteristics:
- **Type flexibility**: Handlers return native Python types; normalizers handle conversion
- **Automatic structuredContent**: Typed objects become JSON-serializable dicts without manual serialization
- **MIME type inference**: Resources default to `text/plain` or `application/octet-stream` based on payload type
- **Content block generation**: Scalars, iterables, and nested structures all become valid `ContentBlock` sequences
- **Error passthrough**: `CallToolResult` with `isError=True` passes through unchanged

## Tool Result Normalization

The `normalize_tool_result()` function accepts any Python value and returns a `CallToolResult` with:
- **content**: List of `ContentBlock` (text, image, audio, resource links, embedded resources)
- **structuredContent**: Optional dict representation of the result for machine parsing

### Supported Return Types

#### 1. CallToolResult (passthrough)

If your handler already returns `CallToolResult`, the normalizer returns it unchanged. This gives you full control over content blocks, structured data, and error flags.

```python
from openmcp import tool
from openmcp.types import CallToolResult, TextContent

@tool(description="Manual result construction")
async def custom_response() -> CallToolResult:
    return CallToolResult(
        content=[
            TextContent(type="text", text="Operation succeeded"),
        ],
        structuredContent={"status": "ok", "timestamp": "2025-11-03T10:00:00Z"},
    )
```

**Result**:
```json
{
  "content": [{"type": "text", "text": "Operation succeeded"}],
  "structuredContent": {"status": "ok", "timestamp": "2025-11-03T10:00:00Z"}
}
```

#### 2. Dictionaries with CallToolResult Fields

If your handler returns a dict containing `content`, `structuredContent`, `isError`, or `_meta`/`meta`, the normalizer attempts to construct a `CallToolResult` from it. On failure, it falls back to the generic dict path.

```python
@tool(description="Dict with result fields")
async def dict_result() -> dict:
    return {
        "content": [{"type": "text", "text": "Custom content"}],
        "structuredContent": {"value": 42},
    }
```

**Result**: Converted to `CallToolResult` with the provided fields.

#### 3. Dataclasses

Dataclasses are converted to dicts via `dataclasses.asdict()` and treated as structured data.

```python
from dataclasses import dataclass

@dataclass
class MathResult:
    operation: str
    result: int
    units: str

@tool(description="Return a dataclass")
async def calculate() -> MathResult:
    return MathResult(operation="addition", result=42, units="meters")
```

**Result**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"operation\": \"addition\", \"result\": 42, \"units\": \"meters\"}"
    }
  ],
  "structuredContent": {
    "operation": "addition",
    "result": 42,
    "units": "meters"
  }
}
```

#### 4. Pydantic Models

Pydantic models are converted to dicts via `model_dump(mode="json")` and treated as structured data. Exception: MCP content types (`TextContent`, `ImageContent`, etc.) are treated as content blocks, not dicts.

```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int
    email: str

@tool(description="Return a Pydantic model")
async def get_person() -> Person:
    return Person(name="Alice", age=30, email="alice@example.com")
```

**Result**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"name\": \"Alice\", \"age\": 30, \"email\": \"alice@example.com\"}"
    }
  ],
  "structuredContent": {
    "name": "Alice",
    "age": 30,
    "email": "alice@example.com"
  }
}
```

#### 5. Tuples (Payload + Structured)

If your handler returns a 2-tuple `(payload, structured)`, the first element becomes the `content` block source, and the second becomes `structuredContent`.

```python
@tool(description="Return tuple with explicit structured data")
async def tuple_result() -> tuple[str, dict]:
    payload = "Operation completed"
    structured = {"status": "success", "duration_ms": 123}
    return (payload, structured)
```

**Result**:
```json
{
  "content": [{"type": "text", "text": "Operation completed"}],
  "structuredContent": {"status": "success", "duration_ms": 123}
}
```

#### 6. Dictionaries (Generic)

Plain dicts become both content (as JSON text) and `structuredContent`.

```python
@tool(description="Return a plain dict")
async def dict_tool() -> dict:
    return {"key": "value", "count": 10}
```

**Result**:
```json
{
  "content": [{"type": "text", "text": "{\"key\": \"value\", \"count\": 10}"}],
  "structuredContent": {"key": "value", "count": 10}
}
```

#### 7. Scalars (str, int, float, bool)

Scalar values become text content. If JSON-serializable, they also become `structuredContent` wrapped in a `{"result": ...}` dict.

```python
@tool(description="Return a string")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

@tool(description="Return an integer")
async def count() -> int:
    return 42
```

**Result for string**:
```json
{
  "content": [{"type": "text", "text": "Hello, Alice!"}],
  "structuredContent": {"result": "Hello, Alice!"}
}
```

**Result for integer**:
```json
{
  "content": [{"type": "text", "text": "42"}],
  "structuredContent": {"result": 42}
}
```

#### 8. None

`None` produces an empty content list. No `structuredContent` is generated.

```python
@tool(description="Return None")
async def noop() -> None:
    return None
```

**Result**:
```json
{
  "content": []
}
```

#### 9. Bytes/Bytearray

Binary data is base64-encoded and returned as text content. The encoded string is the content; no `structuredContent` is generated.

```python
@tool(description="Return binary data")
async def binary() -> bytes:
    return b"\x89PNG\r\n\x1a\n"
```

**Result**:
```json
{
  "content": [{"type": "text", "text": "iVBORw0KGgo="}]
}
```

#### 10. Iterables (Lists, etc.)

Iterables are recursively flattened. Each item is converted to a content block and concatenated.

```python
@tool(description="Return a list of strings")
async def list_tool() -> list[str]:
    return ["first", "second", "third"]
```

**Result**:
```json
{
  "content": [
    {"type": "text", "text": "first"},
    {"type": "text", "text": "second"},
    {"type": "text", "text": "third"}
  ],
  "structuredContent": {"result": ["first", "second", "third"]}
}
```

### structuredContent Generation

The normalizer generates `structuredContent` automatically when:
- The return value is JSON-serializable (primitives, dicts, lists)
- The return value is a dataclass or Pydantic model (converted to dict)
- The return value is a tuple, and the second element is a dict

The generation uses `_jsonify()`, which recursively converts:
- Primitives (`str`, `int`, `float`, `bool`, `None`) → passthrough
- Dicts → recursively convert values, stringify keys
- Lists/tuples/sets → recursively convert elements
- Dataclasses → `asdict()`, then recurse
- Pydantic models → `model_dump(mode="json")`, then recurse
- Non-serializable objects → `_JSONIFY_SENTINEL` (no `structuredContent` generated)

If `_jsonify()` succeeds:
- Dicts are used directly as `structuredContent`
- Non-dicts are wrapped in `{"result": value}`

## Resource Result Normalization

The `normalize_resource_payload()` function accepts a resource URI, optional MIME type, and any payload, returning a `ReadResourceResult` with:
- **contents**: List of `TextResourceContents` or `BlobResourceContents`

### Supported Return Types

#### 1. ReadResourceResult (passthrough)

If your handler already returns `ReadResourceResult`, it passes through unchanged.

```python
from openmcp import resource
from openmcp.types import ReadResourceResult, TextResourceContents

@resource(uri="custom://response")
async def custom_resource() -> ReadResourceResult:
    return ReadResourceResult(
        contents=[
            TextResourceContents(
                uri="custom://response",
                mimeType="application/json",
                text='{"status": "ok"}',
            )
        ]
    )
```

**Result**: Unchanged.

#### 2. TextResourceContents or BlobResourceContents

Single content objects are wrapped in a `ReadResourceResult` with a single-item list.

```python
from openmcp.types import TextResourceContents

@resource(uri="simple://text")
async def simple_text() -> TextResourceContents:
    return TextResourceContents(
        uri="simple://text",
        mimeType="text/plain",
        text="Hello, world!",
    )
```

**Result**:
```json
{
  "contents": [
    {"uri": "simple://text", "mimeType": "text/plain", "text": "Hello, world!"}
  ]
}
```

#### 3. Lists of TextResourceContents or BlobResourceContents

Lists of content objects are wrapped in a `ReadResourceResult`.

```python
@resource(uri="multi://content")
async def multi_content() -> list:
    return [
        TextResourceContents(uri="multi://1", mimeType="text/plain", text="First"),
        TextResourceContents(uri="multi://2", mimeType="text/plain", text="Second"),
    ]
```

**Result**:
```json
{
  "contents": [
    {"uri": "multi://1", "mimeType": "text/plain", "text": "First"},
    {"uri": "multi://2", "mimeType": "text/plain", "text": "Second"}
  ]
}
```

#### 4. Dictionaries

If the dict can be validated as `TextResourceContents` or `BlobResourceContents` (by merging with the provided URI), the normalizer constructs the appropriate content type. Otherwise, it falls back to the string path.

```python
@resource(uri="dict://resource")
async def dict_resource() -> dict:
    return {"mimeType": "application/json", "text": '{"key": "value"}'}
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "dict://resource",
      "mimeType": "application/json",
      "text": "{\"key\": \"value\"}"
    }
  ]
}
```

#### 5. Bytes/Bytearray (Blob)

Binary data is base64-encoded and returned as `BlobResourceContents`. MIME type defaults to `application/octet-stream` unless explicitly declared.

```python
@resource(uri="binary://image", mime_type="image/png")
async def binary_resource() -> bytes:
    return b"\x89PNG\r\n\x1a\n"
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "binary://image",
      "mimeType": "image/png",
      "blob": "iVBORw0KGgo="
    }
  ]
}
```

#### 6. Strings

Strings are returned as `TextResourceContents`. MIME type defaults to `text/plain` unless declared.

```python
@resource(uri="text://simple")
async def text_resource() -> str:
    return "Hello, world!"
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "text://simple",
      "mimeType": "text/plain",
      "text": "Hello, world!"
    }
  ]
}
```

#### 7. Dataclasses and Pydantic Models

Converted to dicts (via `asdict()` or `model_dump(mode="json")`), then JSON-serialized as text.

```python
from dataclasses import dataclass

@dataclass
class Config:
    version: str
    enabled: bool

@resource(uri="config://app", mime_type="application/json")
async def config_resource() -> Config:
    return Config(version="1.0", enabled=True)
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "config://app",
      "mimeType": "application/json",
      "text": "{\"version\": \"1.0\", \"enabled\": true}"
    }
  ]
}
```

#### 8. Other Types

Non-serializable objects are converted to strings via `str()`. JSON-serializable objects are converted via `json.dumps()`.

```python
@resource(uri="fallback://resource")
async def fallback() -> object:
    class CustomObject:
        def __str__(self):
            return "CustomObject representation"
    return CustomObject()
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "fallback://resource",
      "mimeType": "text/plain",
      "text": "CustomObject representation"
    }
  ]
}
```

## MIME Type Handling

Resource normalization uses the following MIME type priority:

1. **Explicit declaration**: If the `@resource` decorator or handler specifies `mime_type`, use it.
2. **Binary detection**: If payload is `bytes` or `bytearray`, default to `application/octet-stream`.
3. **Text fallback**: Otherwise, default to `text/plain`.

For tool results, MIME types are not applicable—content blocks use the `type` discriminator (`text`, `image`, `audio`, etc.) instead.

## Error vs Success Content

Tool handlers can indicate errors by returning `CallToolResult` with `isError=True`:

```python
from openmcp.types import CallToolResult, TextContent

@tool(description="Operation that may fail")
async def risky_operation(x: int) -> CallToolResult:
    if x < 0:
        return CallToolResult(
            content=[TextContent(type="text", text="Error: x must be non-negative")],
            isError=True,
        )
    return CallToolResult(
        content=[TextContent(type="text", text=f"Result: {x * 2}")],
        structuredContent={"result": x * 2},
    )
```

The normalizer does not modify `isError` flags—your handler controls error semantics. For resource handlers, errors should be raised as exceptions rather than encoded in return values.

## Examples

### Example: Returning Multiple Content Blocks

```python
from openmcp import tool
from openmcp.types import TextContent, ImageContent

@tool(description="Return mixed content")
async def mixed_content() -> list:
    return [
        TextContent(type="text", text="Here is an image:"),
        ImageContent(type="image", data="base64encodedimage", mimeType="image/png"),
    ]
```

**Result**:
```json
{
  "content": [
    {"type": "text", "text": "Here is an image:"},
    {"type": "image", "data": "base64encodedimage", "mimeType": "image/png"}
  ]
}
```

### Example: Resource with Custom MIME Type

```python
from openmcp import resource

@resource(uri="config://settings", mime_type="application/json")
async def settings() -> str:
    return '{"theme": "dark", "notifications": true}'
```

**Result**:
```json
{
  "contents": [
    {
      "uri": "config://settings",
      "mimeType": "application/json",
      "text": "{\"theme\": \"dark\", \"notifications\": true}"
    }
  ]
}
```

### Example: Nested Dataclass

```python
from dataclasses import dataclass

@dataclass
class Address:
    street: str
    city: str

@dataclass
class User:
    name: str
    address: Address

@tool(description="Return nested dataclass")
async def get_user() -> User:
    return User(
        name="Bob",
        address=Address(street="123 Main St", city="Springfield"),
    )
```

**Result**:
```json
{
  "content": [
    {
      "type": "text",
      "text": "{\"name\": \"Bob\", \"address\": {\"street\": \"123 Main St\", \"city\": \"Springfield\"}}"
    }
  ],
  "structuredContent": {
    "name": "Bob",
    "address": {"street": "123 Main St", "city": "Springfield"}
  }
}
```

## See Also

- [Tools](tools.md) - Tool registration and schema inference
- [Resources](resources.md) - Resource registration and URI templates
- [Context](context.md) - Access MCP context in handlers
- MCP Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- MCP Spec: https://modelcontextprotocol.io/specification/2025-06-18/server/resources
