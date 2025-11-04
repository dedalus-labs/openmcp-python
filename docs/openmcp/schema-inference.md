# Schema Inference

**DRAFT**: This documentation describes the schema inference mechanism as currently implemented. API surface may change before public release.

**Problem**: MCP requires tools to declare JSON schemas for their input parameters and output structures. Manually writing these schemas is error-prone, verbose, and diverges from the single source of truth—the function signature itself. Type annotations already describe parameter constraints; duplicating this information in JSON Schema introduces maintenance burden.

**Solution**: OpenMCP automatically derives JSON schemas from Python type annotations using Pydantic's `TypeAdapter`. Tool authors write typed function signatures, and the framework generates spec-compliant schemas at registration time. This ensures the declared schema always matches the actual implementation.

**OpenMCP**: The `ToolsService` implements schema inference for both input and output schemas during tool registration (lines 180-269 of `src/openmcp/server/services/tools.py`). Input schemas are derived from function parameters, output schemas from return annotations, with automatic scalar boxing to satisfy MCP's object-only structured content requirement.

## Specification

While the Model Context Protocol itself does not prescribe schema inference mechanisms, the JSON Schema format for tool declarations is specified in:

https://modelcontextprotocol.io/specification/2025-06-18/server/tools

The `tools/list` response includes an `inputSchema` (required) and optionally an `outputSchema` for each tool. Both must be valid JSON Schema objects describing the expected input parameters and output structure respectively.

## Input Schema Generation

The input schema is derived from the function signature by inspecting each parameter and constructing a `TypedDict` that mirrors the parameter names and types. This `TypedDict` is then passed to Pydantic's `TypeAdapter.json_schema()` to generate the canonical JSON Schema.

### Algorithm

1. **Inspect parameters**: Extract all `POSITIONAL_OR_KEYWORD` and `KEYWORD_ONLY` parameters using `inspect.signature()`.
2. **Build annotations dictionary**: For each parameter:
   - Use the parameter's type annotation if present, otherwise default to `Any`.
   - Wrap optional parameters (those with defaults) in `NotRequired[]`.
   - Record default values separately.
3. **Construct TypedDict**: Dynamically create a `TypedDict` class with the annotations dictionary.
4. **Generate schema**: Pass the `TypedDict` to `TypeAdapter(typed_dict).json_schema()`.
5. **Enhance schema**: Add parameter descriptions, default values, and compute the `required` list (parameters without defaults).
6. **Clean schema**: Remove `$defs`, prune `title` fields, set `additionalProperties: false`.

### Fallback Behavior

If parameter inspection or schema generation fails (e.g., unsupported parameter kinds like `*args` or `**kwargs`, Pydantic errors), the system falls back to:

```json
{"type": "object", "additionalProperties": true}
```

This permissive schema accepts any JSON object but provides no validation. Tools should avoid variadic parameters if schema validation is desired.

## Output Schema Generation

The output schema is derived from the function's return type annotation. Unlike input schemas, output schemas are optional—tools may omit them to disable structured content validation.

### Algorithm

1. **Extract return annotation**: Inspect `signature.return_annotation`.
2. **Resolve deferred types**: Use `get_type_hints()` to evaluate forward references and string annotations, including closure namespace resolution for locally defined types.
3. **Check blocklist**: Skip schema generation if the return type is an MCP content type (e.g., `CallToolResult`, `TextContent`, `ImageContent`) or a Union containing such types.
4. **Generate schema**: Pass the annotation to `resolve_output_schema()` from `openmcp.utils.schema`, which:
   - Derives the base schema via `TypeAdapter.json_schema(mode="serialization")`.
   - Wraps scalar schemas into objects (e.g., `int` → `{"type": "object", "properties": {"result": {"type": "integer"}}}`) to satisfy MCP's object requirement.
   - Adds vendor extension `x-dedalus-box` to record boxing metadata.
5. **Clean schema**: Remove `$defs`, prune `title` fields.

### Blocklist

The following MCP content types are explicitly excluded from output schema generation:

- `CallToolResult`
- `ServerResult`
- `TextContent`
- `ImageContent`
- `AudioContent`
- `ResourceLink`
- `EmbeddedResource`

If the return annotation is (or contains via `Union`) any of these types, the output schema is set to `None`. This prevents redundant schema declarations for types already understood by MCP transports.

### Scalar Boxing

MCP's structured content must be a JSON object. If a tool returns a scalar (e.g., `int`, `str`, `bool`), the schema inference wraps the scalar into an object with a single `result` property:

```python
# Tool returns int
def answer() -> int:
    return 7

# Generated schema
{
    "type": "object",
    "properties": {"result": {"type": "integer"}},
    "required": ["result"],
    "x-dedalus-box": {"field": "result"}
}

# Actual structured content
{"result": 7}
```

The `x-dedalus-box` vendor extension records the wrapping field name so clients can unwrap the scalar if desired. The normalization layer automatically boxes scalar return values into this format.

## Supported Types

### Primitives

```python
from openmcp import tool

@tool()
def greet(name: str, age: int, active: bool = True) -> str:
    return f"Hello {name}, age {age}"

# Input schema inferred:
# {
#   "type": "object",
#   "properties": {
#     "name": {"type": "string", "description": "Parameter name"},
#     "age": {"type": "integer", "description": "Parameter age"},
#     "active": {"type": "boolean", "description": "Parameter active", "default": true}
#   },
#   "required": ["name", "age"],
#   "additionalProperties": false
# }

# Output schema inferred:
# {
#   "type": "object",
#   "properties": {"result": {"type": "string"}},
#   "required": ["result"],
#   "x-dedalus-box": {"field": "result"}
# }
```

### Containers

```python
@tool()
def analyze(values: list[int], metadata: dict[str, str]) -> dict[str, float]:
    return {"mean": sum(values) / len(values)}

# Input schema properties:
# "values": {"type": "array", "items": {"type": "integer"}}
# "metadata": {"type": "object", "additionalProperties": {"type": "string"}}

# Output schema:
# {
#   "type": "object",
#   "properties": {
#     "mean": {"type": "number"}
#   },
#   "additionalProperties": false
# }
```

### Literal

```python
from typing import Literal

@tool()
def set_mode(mode: Literal["fast", "accurate", "balanced"]) -> str:
    return f"Mode set to {mode}"

# Input schema for mode:
# {"enum": ["fast", "accurate", "balanced"], "type": "string"}
```

### Optional and Union

```python
from typing import Optional

@tool()
def find(query: str, limit: Optional[int] = None) -> list[str]:
    return []

# Input schema properties:
# "query": {"type": "string"}
# "limit": {"anyOf": [{"type": "integer"}, {"type": "null"}], "default": null}

# Output schema:
# {
#   "type": "object",
#   "properties": {
#     "result": {"type": "array", "items": {"type": "string"}}
#   },
#   "required": ["result"],
#   "x-dedalus-box": {"field": "result"}
# }
```

### NotRequired (PEP 655)

```python
from typing import NotRequired, TypedDict

class SearchParams(TypedDict):
    query: str
    max_results: NotRequired[int]

@tool()
def search(params: SearchParams) -> list[str]:
    return []

# Input schema properties:
# "query": {"type": "string"}
# "max_results": {"type": "integer"}  # Not in required list
# required: ["query"]
```

### Dataclasses

```python
from dataclasses import dataclass

@dataclass
class Address:
    street: str
    city: str
    postal_code: int

@dataclass
class Profile:
    name: str
    address: Address
    tags: list[str]

@tool()
def create_profile(name: str, street: str, city: str) -> Profile:
    return Profile(
        name=name,
        address=Address(street=street, city=city, postal_code=94107),
        tags=["new"]
    )

# Output schema:
# {
#   "type": "object",
#   "properties": {
#     "name": {"type": "string"},
#     "address": {
#       "type": "object",
#       "properties": {
#         "street": {"type": "string"},
#         "city": {"type": "string"},
#         "postal_code": {"type": "integer"}
#       },
#       "additionalProperties": false
#     },
#     "tags": {"type": "array", "items": {"type": "string"}}
#   },
#   "additionalProperties": false
# }
```

### Pydantic Models

```python
from pydantic import BaseModel, Field

class User(BaseModel):
    username: str = Field(..., min_length=3, max_length=20)
    email: str = Field(..., pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    age: int = Field(..., ge=0, le=120)

@tool()
def register_user(user: User) -> str:
    return f"Registered {user.username}"

# Input schema properties:
# "username": {"type": "string", "minLength": 3, "maxLength": 20}
# "email": {"type": "string", "pattern": "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$"}
# "age": {"type": "integer", "minimum": 0, "maximum": 120}

# Output schema (scalar string boxed):
# {
#   "type": "object",
#   "properties": {"result": {"type": "string"}},
#   "required": ["result"],
#   "x-dedalus-box": {"field": "result"}
# }
```

### Union Types

```python
from typing import Union

@dataclass
class ChatAction:
    kind: Literal["chat"]
    message: str

@dataclass
class NavigateAction:
    kind: Literal["navigate"]
    url: str

UnionAction = Union[ChatAction, NavigateAction]

@tool()
def choose_action(chat: bool) -> UnionAction:
    if chat:
        return ChatAction(kind="chat", message="hi")
    return NavigateAction(kind="navigate", url="https://example.com")

# Output schema uses anyOf:
# {
#   "anyOf": [
#     {
#       "type": "object",
#       "properties": {
#         "kind": {"enum": ["chat"], "type": "string"},
#         "message": {"type": "string"}
#       },
#       "additionalProperties": false
#     },
#     {
#       "type": "object",
#       "properties": {
#         "kind": {"enum": ["navigate"], "type": "string"},
#         "url": {"type": "string"}
#       },
#       "additionalProperties": false
#     }
#   ]
# }
```

## Unsupported Types and Fallback

Certain constructs cannot be reliably converted to JSON Schema:

- **Variadic parameters**: Functions using `*args` or `**kwargs` fall back to `{"type": "object", "additionalProperties": true}`.
- **Complex generics**: Deeply nested or exotic type expressions may cause Pydantic to raise errors, triggering the permissive fallback.
- **Dynamic types**: Runtime type construction (e.g., `type()` calls, metaclass magic) is invisible to static inspection.

When schema generation fails, the framework logs a debug message and returns the permissive fallback. Tools should use explicit, well-typed signatures to ensure accurate schemas.

## Schema Caching

Schema generation is performed once at tool registration time and cached in `ToolsService._tool_defs`. Repeated calls to `tools/list` or `tools/call` do not re-derive schemas. This ensures:

- **Consistency**: The schema never changes after registration.
- **Performance**: Pydantic's TypeAdapter invocation is expensive; caching amortizes the cost.
- **Stability**: Clients can rely on schema invariants across sessions.

To invalidate the cache, re-register the tool or restart the server.

## Title Pruning

Pydantic's JSON Schema generator includes `title` fields for every type, property, and nested object. These titles bloat the schema without adding semantic value for MCP clients. The `_prune_titles()` function recursively strips all `title` keys from the generated schema.

Example:

```python
# Before pruning
{
    "title": "AnalyticsTool",
    "type": "object",
    "properties": {
        "count": {"title": "Count", "type": "integer"}
    }
}

# After pruning
{
    "type": "object",
    "properties": {
        "count": {"type": "integer"}
    }
}
```

This reduces schema size by 20-40% depending on type complexity.

## Examples

### Basic Tool with Mixed Types

```python
from openmcp import MCPServer, tool
from typing import Optional

server = MCPServer("analytics")

@tool(description="Analyze data with optional filters")
async def analyze(
    dataset: str,
    limit: int = 100,
    filters: Optional[dict[str, str]] = None
) -> dict[str, int]:
    # Implementation...
    return {"records": 42, "filtered": 10}

# Input schema:
# {
#   "type": "object",
#   "properties": {
#     "dataset": {"type": "string", "description": "Parameter dataset"},
#     "limit": {"type": "integer", "description": "Parameter limit", "default": 100},
#     "filters": {
#       "anyOf": [
#         {"type": "object", "additionalProperties": {"type": "string"}},
#         {"type": "null"}
#       ],
#       "description": "Parameter filters",
#       "default": null
#     }
#   },
#   "required": ["dataset"],
#   "additionalProperties": false
# }

# Output schema:
# {
#   "type": "object",
#   "properties": {
#     "records": {"type": "integer"},
#     "filtered": {"type": "integer"}
#   },
#   "additionalProperties": false
# }
```

### Scalar Return Type (Boxed)

```python
@tool()
async def get_temperature(city: str) -> float:
    return 72.5

# Output schema:
# {
#   "type": "object",
#   "properties": {"result": {"type": "number"}},
#   "required": ["result"],
#   "x-dedalus-box": {"field": "result"}
# }

# Actual structured content returned:
# {"result": 72.5}
```

### Nested Dataclass with Optional Fields

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Location:
    latitude: float
    longitude: float

@dataclass
class WeatherReport:
    temperature: float
    location: Location
    humidity: Optional[float] = None

@tool()
async def weather(city: str) -> WeatherReport:
    return WeatherReport(
        temperature=72.5,
        location=Location(latitude=37.7749, longitude=-122.4194)
    )

# Output schema:
# {
#   "type": "object",
#   "properties": {
#     "temperature": {"type": "number"},
#     "location": {
#       "type": "object",
#       "properties": {
#         "latitude": {"type": "number"},
#         "longitude": {"type": "number"}
#       },
#       "additionalProperties": false
#     },
#     "humidity": {"anyOf": [{"type": "number"}, {"type": "null"}]}
#   },
#   "additionalProperties": false
# }
```

### Pydantic Model with Validation

```python
from pydantic import BaseModel, Field, EmailStr

class CreateUserRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=20, pattern=r'^[a-zA-Z0-9_]+$')
    email: EmailStr
    age: int = Field(..., ge=13, le=120)
    bio: Optional[str] = Field(None, max_length=500)

@tool()
async def create_user(request: CreateUserRequest) -> dict[str, str]:
    return {"user_id": "usr_123", "status": "created"}

# Input schema:
# {
#   "type": "object",
#   "properties": {
#     "username": {
#       "type": "string",
#       "minLength": 3,
#       "maxLength": 20,
#       "pattern": "^[a-zA-Z0-9_]+$",
#       "description": "Parameter username"
#     },
#     "email": {
#       "type": "string",
#       "format": "email",
#       "description": "Parameter email"
#     },
#     "age": {
#       "type": "integer",
#       "minimum": 13,
#       "maximum": 120,
#       "description": "Parameter age"
#     },
#     "bio": {
#       "anyOf": [{"type": "string", "maxLength": 500}, {"type": "null"}],
#       "description": "Parameter bio",
#       "default": null
#     }
#   },
#   "required": ["username", "email", "age"],
#   "additionalProperties": false
# }
```

### Explicit Schema Override

While automatic inference covers most cases, you can explicitly provide schemas by passing `input_schema` or `output_schema` to `@tool()`:

```python
@tool(
    input_schema={
        "type": "object",
        "properties": {
            "custom_field": {"type": "string", "enum": ["a", "b", "c"]}
        },
        "required": ["custom_field"],
        "additionalProperties": false
    }
)
async def custom_tool(**kwargs) -> str:
    return kwargs.get("custom_field", "default")

# Uses provided schema instead of inferring from **kwargs
```

This is useful for edge cases where inference produces incorrect results or when you need finer control over schema constraints.

## See Also

- [Tools](./tools.md) — Overview of the tools capability and registration patterns
- [Result Normalization](./result-normalization.md) — How return values are converted to MCP structured content
- `src/openmcp/server/services/tools.py` — Reference implementation (lines 180-269)
- `src/openmcp/utils/schema.py` — Schema utilities and scalar boxing logic
- [MCP Tools Specification](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
