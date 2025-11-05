# Elicitation

**Problem**: Servers need to request user input during tool execution—confirmations, form data, or multi-step wizard flows—without breaking the JSON-RPC request/response contract or resorting to side channels.

**Solution**: The elicitation capability lets servers send `elicitation/create` requests to clients, specifying a user-facing message and a JSON Schema for the expected input fields. The client presents UI (dialog, form, etc.) and returns the user's response: accept with data, decline, or cancel.

**OpenMCP**: Call `server.request_elicitation(params)` from any tool or resource handler. OpenMCP validates the schema (top-level properties only, per spec), sends the request over the active session, and propagates the client's response or raises `McpError` on timeout (60s default) or client rejection.

```python
from openmcp import MCPServer, types, tool

server = MCPServer("approval-workflow")

with server.binding():
    @tool(description="Delete a file after confirmation")
    async def delete_file(path: str) -> str:
        # Request confirmation from client
        result = await server.request_elicitation(
            types.ElicitRequestParams(
                message=f"Are you sure you want to delete {path}?",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "confirm": {"type": "boolean"}
                    },
                    "required": ["confirm"]
                }
            )
        )

        if result.action == "accept" and result.content.get("confirm"):
            # Proceed with deletion
            return f"Deleted {path}"
        else:
            return "Deletion cancelled"
```

- Spec receipt: `https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation`
- NEW in MCP 2025-06-18 (this capability did not exist in prior protocol versions)
- Client must advertise `elicitation` capability during handshake; requests fail with `METHOD_NOT_FOUND` otherwise
- The 60s timeout is configurable via `ElicitationService(timeout=90.0)` if you need longer user-think time
- Actions are mutually exclusive: `accept` (submitted data), `decline` (explicit no), `cancel` (dismissed)

---

## Specification (NEW in 2025-06-18)

Elicitation was introduced in the 2025-06-18 protocol revision to provide a standard mechanism for human-in-the-loop interactions. Prior versions required ad-hoc patterns or external channels; now the protocol formalizes the request/response contract.

### Request Flow

1. Server checks client capabilities for `elicitation` support
2. Server sends `elicitation/create` with message and schema
3. Client presents UI to user (modal, form, CLI prompt, etc.)
4. Client returns `ElicitResult` with action and optional content
5. Server processes the response or handles rejection/timeout

### Protocol Messages

**Request**: `elicitation/create`


```json
{
  "method": "elicitation/create",
  "params": {
    "message": "Provide your name and email",
    "requestedSchema": {
      "type": "object",
      "properties": {
        "name": {"type": "string"},
        "email": {"type": "string"}
      },
      "required": ["name", "email"]
    }
  }
}
```


**Response**: `ElicitResult`

```json
{
  "action": "accept",
  "content": {
    "name": "Alice",
    "email": "alice@example.com"
  }
}
```

---

## Server-Side Usage

Call `server.request_elicitation()` from any async context where you need user input. The method requires an active MCP session (i.e., you must be inside a tool/resource/prompt handler).

```python
from openmcp import MCPServer, types, tool

server = MCPServer("data-collector")

with server.binding():
    @tool(description="Register a new account")
    async def register(username: str) -> str:
        # Multi-field form elicitation
        result = await server.request_elicitation(
            types.ElicitRequestParams(
                message="Complete your profile",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "email": {"type": "string"},
                        "age": {"type": "integer"},
                        "newsletter": {"type": "boolean"}
                    },
                    "required": ["email"]
                }
            )
        )

        if result.action != "accept":
            return "Registration cancelled"

        email = result.content["email"]
        age = result.content.get("age", "not provided")
        newsletter = result.content.get("newsletter", False)
        return f"Registered {username} with email {email}"
```

### Error Handling

```python
from mcp.shared.exceptions import McpError
from openmcp import types

try:
    result = await server.request_elicitation(params)
except McpError as exc:
    if exc.error.code == types.METHOD_NOT_FOUND:
        # Client doesn't support elicitation
        return "Cannot request confirmation from this client"
    elif exc.error.code == types.INTERNAL_ERROR:
        # Timeout or other server-side issue
        return "Request timed out"
    else:
        # Client returned error (e.g., validation failure)
        return f"Client error: {exc.error.message}"
```

---

## Client Handler Implementation

Clients advertise support via `capabilities.elicitation` and implement a handler for `elicitation/create`. The handler must present UI and return an `ElicitResult`.

```python
from openmcp import MCPClient, types

client = MCPClient()

@client.handle_elicitation()
async def handle_elicitation(params: types.ElicitRequestParams) -> types.ElicitResult:
    # Present UI to user (implementation-specific)
    print(params.message)
    print("Schema:", params.requestedSchema)

    # Collect input (simplified for example)
    user_input = input("Enter 'yes' to accept: ")

    if user_input.lower() == "yes":
        # Build content matching schema
        content = {}
        for prop in params.requestedSchema["properties"]:
            content[prop] = input(f"{prop}: ")

        return types.ElicitResult(action="accept", content=content)
    else:
        return types.ElicitResult(action="decline")
```


**Key Points**:

- Handler must be registered before connecting
- Schema validation is server-side; client is responsible for UI presentation
- Client can return `decline` or `cancel` without content
- Timeout handling is client responsibility (present a cancel button, etc.)

---

## Schema Validation

The server validates `requestedSchema` to ensure spec compliance. Per the protocol, only **top-level properties** are supported—no nested objects, arrays, or complex composition.

### Validation Rules

1. Root `type` must be `"object"`
2. `properties` must be a non-empty object
3. Each property schema must have `type` in: `string`, `number`, `integer`, `boolean`

4. Nested structures, `anyOf`, `allOf`, etc. are **not supported**

### Valid Example

```python
{
    "type": "object",
    "properties": {
        "username": {"type": "string"},
        "age": {"type": "integer"},
        "subscribe": {"type": "boolean"}
    },
    "required": ["username"]

}
```

### Invalid Example (nested object)

```python
{
    "type": "object",
    "properties": {
        "user": {
            "type": "object",  # ❌ nested objects not allowed
            "properties": {"name": {"type": "string"}}
        }
    }
}
```

If validation fails, `request_elicitation()` raises `McpError` with code `INVALID_PARAMS` before sending to the client.

---

## Actions

The `ElicitResult.action` field indicates the user's response:

- **`accept`**: User submitted the form. `content` contains field values matching the schema.
- **`decline`**: User explicitly rejected the action. `content` is `None`.
- **`cancel`**: User dismissed the dialog without making a choice. `content` is `None`.

### Handling Actions

```python
result = await server.request_elicitation(params)

match result.action:
    case "accept":
        # Process result.content
        data = result.content
        return f"Processed: {data}"

    case "decline":
        # User said no
        return "Action declined by user"

    case "cancel":
        # User dismissed
        return "Action cancelled"
```

Servers should treat `decline` and `cancel` as similar (user did not proceed) but can distinguish if the semantics matter (e.g., logging user rejection vs. timeout).

---

## Examples

### Example 1: Confirmation Dialog

```python
from openmcp import MCPServer, types, tool

server = MCPServer("file-manager")

with server.binding():
    @tool(description="Delete a sensitive file")
    async def delete_sensitive(path: str) -> str:
        result = await server.request_elicitation(
            types.ElicitRequestParams(
                message=f"⚠️ Delete sensitive file {path}?",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "confirm": {"type": "boolean"}
                    },
                    "required": ["confirm"]
                }
            )
        )

        if result.action == "accept" and result.content.get("confirm"):
            # Perform deletion
            return f"Deleted {path}"
        return "Deletion cancelled"
```

### Example 2: Multi-Field Form

```python
from openmcp import MCPServer, types, tool

server = MCPServer("user-onboarding")

with server.binding():
    @tool(description="Create a new project")
    async def create_project(name: str) -> str:
        result = await server.request_elicitation(
            types.ElicitRequestParams(
                message=f"Configure project '{name}'",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "public": {"type": "boolean"},
                        "max_users": {"type": "integer"}
                    },
                    "required": ["description"]
                }
            )
        )

        if result.action != "accept":
            return "Project creation cancelled"

        desc = result.content["description"]
        public = result.content.get("public", False)
        max_users = result.content.get("max_users", 10)

        return f"Created project '{name}': {desc} (public={public}, max_users={max_users})"
```

### Example 3: Multi-Step Wizard

```python
from openmcp import MCPServer, types, tool

server = MCPServer("deployment-wizard")

with server.binding():
    @tool(description="Deploy application with guided setup")
    async def deploy(app_name: str) -> str:
        # Step 1: Environment selection
        env_result = await server.request_elicitation(
            types.ElicitRequestParams(
                message="Select deployment environment",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "environment": {"type": "string"}  # e.g., "staging" or "production"
                    },
                    "required": ["environment"]
                }
            )
        )

        if env_result.action != "accept":
            return "Deployment cancelled"

        environment = env_result.content["environment"]

        # Step 2: Resource configuration
        config_result = await server.request_elicitation(
            types.ElicitRequestParams(
                message=f"Configure resources for {environment}",
                requestedSchema={
                    "type": "object",
                    "properties": {
                        "cpu_cores": {"type": "integer"},
                        "memory_gb": {"type": "integer"},
                        "auto_scale": {"type": "boolean"}
                    },
                    "required": ["cpu_cores", "memory_gb"]
                }
            )
        )

        if config_result.action != "accept":
            return "Deployment cancelled"

        cpu = config_result.content["cpu_cores"]
        memory = config_result.content["memory_gb"]
        auto_scale = config_result.content.get("auto_scale", False)

        return f"Deployed {app_name} to {environment} ({cpu} cores, {memory}GB, auto_scale={auto_scale})"
```

---

## See Also

- **Tools**: `docs/openmcp/tools.md` (tool handlers that can call elicitation)
- **Resources**: `docs/openmcp/resources.md` (resource handlers with elicitation)
- **Sampling**: `docs/openmcp/sampling.md` (server-to-client LLM requests)
- **Context**: `docs/openmcp/context.md` (`get_context()` for logging inside handlers)
- **Spec**: `https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation`

---

**DRAFT NOTICE**: This documentation describes a NEW capability in MCP 2025-06-18. Client implementations are still maturing; expect DX refinements before stable release. The core protocol contract (request/response/actions) is stable, but handler APIs may evolve based on field feedback.
