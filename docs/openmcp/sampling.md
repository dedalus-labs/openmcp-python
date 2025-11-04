# Sampling

**DRAFT**: This documentation describes the sampling capability as currently implemented. API surface may change before public release.

**Problem**: MCP servers sometimes need to request completions from the client's LLM during tool execution—for example, to perform multi-step reasoning, generate natural language output, or delegate decision-making back to the model. Without a standardized mechanism, servers must implement their own LLM integration or forgo these capabilities entirely.

**Solution**: The sampling capability allows servers to send `sampling/createMessage` requests to clients, asking them to invoke their LLM and return a completion. Clients that advertise the `sampling` capability act as a proxy between the server and the underlying model.

**OpenMCP**: The `SamplingService` implements the server side of this flow, enforcing reliability patterns (circuit breaker, concurrency limits, timeouts) to prevent cascading failures when requesting LLM completions from clients.

## Specification

https://modelcontextprotocol.io/specification/2025-06-18/server/sampling

The sampling capability enables servers to request LLM completions from clients through the `sampling/createMessage` JSON-RPC request. This is a **server-to-client** request: the server acts as requester, and the client handles the request by invoking its LLM and returning the result.

Key characteristics:
- **Capability advertisement**: Clients advertise `sampling` in the `initialize` handshake; servers check this before sending requests.
- **Request structure**: Servers send `CreateMessageRequest` with messages, model preferences, sampling parameters, and optional metadata.
- **Response structure**: Clients return `CreateMessageResult` containing the model's completion, stop reason, and token usage statistics.
- **Error handling**: Missing capability → `METHOD_NOT_FOUND` (-32601). Clients may also return application-level errors for rate limits, content policy violations, or model failures.

## Server-Side Usage

When your server needs to invoke the client's LLM, construct a `CreateMessageRequestParams` and call `SamplingService.create_message()`. This method handles capability checks, concurrency control, timeout enforcement, and circuit breaker logic automatically.

```python
from openmcp import MCPServer, tool
from openmcp.types import CreateMessageRequestParams, Role, SamplingMessage

server = MCPServer("reasoner")

@tool(description="Explain a concept using the client's LLM")
async def explain(topic: str) -> str:
    """Use client's LLM to generate an explanation."""
    params = CreateMessageRequestParams(
        messages=[
            SamplingMessage(
                role=Role.user,
                content={"type": "text", "text": f"Explain {topic} in simple terms"}
            )
        ],
        modelPreferences={"hints": [{"name": "claude-3-5-sonnet-20241022"}]},
        maxTokens=1000,
    )

    result = await server.sampling_service.create_message(params)
    return result.content.text
```

The `create_message()` method:
1. Verifies the client advertised the sampling capability (raises `METHOD_NOT_FOUND` if missing)
2. Enforces concurrency limits (default: max 4 concurrent requests per session)
3. Applies circuit breaker logic (3 failures → 30s cooldown)
4. Adds a `requestId` to metadata if not already present
5. Sends the request to the client via the MCP session
6. Waits up to 60 seconds (default timeout) for the response
7. Returns `CreateMessageResult` on success, raises `McpError` on failure

## Client Handler Implementation

Clients must implement a handler for `sampling/createMessage` requests if they advertise the sampling capability. The handler receives `CreateMessageRequest` and returns `CreateMessageResult`.

**Minimal handler** (sync):

```python
from mcp.types import CreateMessageRequest, CreateMessageResult, TextContent, Role, StopReason

def handle_sampling(request: CreateMessageRequest) -> CreateMessageResult:
    """Simple echo handler for demonstration."""
    messages = request.params.messages
    last_message = messages[-1].content.text if messages else "Hello"

    return CreateMessageResult(
        model="echo-model",
        content=TextContent(type="text", text=f"Echo: {last_message}"),
        role=Role.assistant,
        stopReason=StopReason.endTurn,
    )
```

**Production handler** (async with real LLM):

```python
import anthropic
from mcp.types import CreateMessageRequest, CreateMessageResult, TextContent, Role, StopReason

async def handle_sampling(request: CreateMessageRequest) -> CreateMessageResult:
    """Invoke Anthropic API for sampling requests."""
    client = anthropic.AsyncAnthropic()  # uses ANTHROPIC_API_KEY env var

    # Convert MCP messages to Anthropic format
    messages = [
        {"role": msg.role, "content": msg.content.text}
        for msg in request.params.messages
    ]

    # Respect model preferences if provided
    model = "claude-3-5-sonnet-20241022"
    if request.params.modelPreferences and request.params.modelPreferences.hints:
        model = request.params.modelPreferences.hints[0].name or model

    # Call the LLM
    response = await client.messages.create(
        model=model,
        messages=messages,
        max_tokens=request.params.maxTokens or 4096,
        temperature=request.params.temperature or 1.0,
    )

    # Convert response to MCP format
    return CreateMessageResult(
        model=response.model,
        content=TextContent(type="text", text=response.content[0].text),
        role=Role.assistant,
        stopReason=StopReason[response.stop_reason] if response.stop_reason else StopReason.endTurn,
    )
```

Register the handler when connecting to the server:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="python",
    args=["server.py"],
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        # Advertise sampling capability
        await session.initialize(capabilities={"sampling": {}})

        # Register handler
        session.set_request_handler("sampling/createMessage", handle_sampling)

        # Server can now call sampling API
        ...
```

## Configuration

The `SamplingService` accepts two configuration parameters:

```python
from openmcp.server.services.sampling import SamplingService

service = SamplingService(
    timeout=60.0,        # Maximum seconds to wait for client response
    max_concurrent=4,    # Maximum concurrent sampling requests per session
)
```

Adjust these based on your workload:
- **Increase `max_concurrent`** if you have many parallel tool calls that independently need sampling
- **Decrease `max_concurrent`** if you want to limit load on the client's LLM
- **Increase `timeout`** for complex prompts that require long processing times
- **Decrease `timeout`** for interactive scenarios where fast failure is preferred

The `MCPServer` constructor passes these through to the service:

```python
from openmcp import MCPServer

server = MCPServer(
    "my-server",
    sampling_timeout=120.0,      # 2 minute timeout
    sampling_max_concurrent=8,   # 8 concurrent requests
)
```

## Circuit Breaker Behavior

The sampling service implements a **per-session circuit breaker** to prevent cascading failures when the client's LLM is unavailable or overloaded. The circuit breaker tracks consecutive failures and enforces a cooldown period after repeated errors.

**State machine**:
1. **Closed** (normal operation): Requests proceed normally. Consecutive failure count = 0.
2. **Tracking failures**: Each timeout or error increments `consecutive_failures`. Successful requests reset the counter to 0.
3. **Open** (cooldown): After **3 consecutive failures**, the circuit opens and rejects new requests for **30 seconds** with `SERVICE_UNAVAILABLE` (-32000).
4. **Half-open**: After cooldown expires, the next request is allowed through. Success resets the counter; failure restarts the cooldown.

**Failure triggers**:
- Request timeout (>60s by default)
- Any `McpError` raised by the client handler
- Transport-level failures (connection lost, session closed)

**Why this matters**:
- Prevents your server from repeatedly hammering an overloaded client
- Gives the client's LLM time to recover from rate limits or capacity issues
- Fails fast during the cooldown period instead of queueing up slow requests
- Per-session isolation means one misbehaving client doesn't affect others

**Example failure sequence**:

```python
# Request 1: timeout after 60s → consecutive_failures = 1
# Request 2: timeout after 60s → consecutive_failures = 2
# Request 3: timeout after 60s → consecutive_failures = 3, cooldown_until = now + 30s
# Request 4 (t+5s): rejected immediately with SERVICE_UNAVAILABLE
# Request 5 (t+35s): allowed through (cooldown expired)
#   - If success → consecutive_failures = 0, circuit closed
#   - If failure → consecutive_failures = 4, cooldown_until = now + 30s
```

You cannot currently configure the threshold (3 failures) or cooldown duration (30s). These values are derived from production incident patterns and will become configurable if telemetry shows different workloads require tuning.

## Examples

### Multi-Step Reasoning

Use the client's LLM to break down a complex problem into steps:

```python
from openmcp import MCPServer, tool, get_context
from openmcp.types import CreateMessageRequestParams, Role, SamplingMessage

server = MCPServer("planner")

@tool(description="Break down a task into actionable steps")
async def plan_task(task: str) -> list[str]:
    """Generate step-by-step plan using client's LLM."""
    ctx = get_context()
    await ctx.info("Generating plan", data={"task": task})

    params = CreateMessageRequestParams(
        messages=[
            SamplingMessage(
                role=Role.user,
                content={
                    "type": "text",
                    "text": (
                        f"Break down this task into 3-5 concrete steps:\n\n{task}\n\n"
                        "Return ONLY a numbered list, one step per line."
                    )
                }
            )
        ],
        maxTokens=500,
        temperature=0.7,
    )

    result = await server.sampling_service.create_message(params)

    # Parse numbered list from response
    lines = result.content.text.strip().split("\n")
    steps = [line.split(".", 1)[1].strip() for line in lines if line and line[0].isdigit()]

    await ctx.info("Plan generated", data={"steps": steps})
    return steps
```

Client usage:

```bash
$ mcp-client call plan_task '{"task": "Deploy a new web service"}'
[
  "Provision infrastructure (compute, storage, networking)",
  "Configure CI/CD pipeline for automated builds",
  "Deploy containerized application to staging environment",
  "Run integration tests and smoke tests",
  "Promote to production with blue-green deployment"
]
```

### Human-in-the-Loop Pattern

Delegate uncertain decisions back to the LLM:

```python
from openmcp import MCPServer, tool
from openmcp.types import CreateMessageRequestParams, Role, SamplingMessage

server = MCPServer("classifier")

@tool(description="Classify text sentiment using client's LLM")
async def classify_sentiment(text: str) -> str:
    """Use LLM for sentiment classification instead of heuristics."""
    params = CreateMessageRequestParams(
        messages=[
            SamplingMessage(
                role=Role.user,
                content={
                    "type": "text",
                    "text": (
                        f"Classify the sentiment of this text as positive, negative, or neutral:\n\n"
                        f"{text}\n\n"
                        f"Respond with ONLY ONE WORD: positive, negative, or neutral"
                    )
                }
            )
        ],
        maxTokens=10,
        temperature=0.0,  # deterministic classification
    )

    result = await server.sampling_service.create_message(params)
    sentiment = result.content.text.strip().lower()

    # Validate response
    if sentiment not in ("positive", "negative", "neutral"):
        return "neutral"  # fallback for unexpected responses

    return sentiment
```

### Iterative Refinement

Chain multiple sampling requests to refine output:

```python
from openmcp import MCPServer, tool
from openmcp.types import CreateMessageRequestParams, Role, SamplingMessage

server = MCPServer("writer")

@tool(description="Generate and refine documentation")
async def write_docs(topic: str) -> str:
    """Generate docs in two passes: draft, then refinement."""
    # First pass: generate draft
    draft_params = CreateMessageRequestParams(
        messages=[
            SamplingMessage(
                role=Role.user,
                content={
                    "type": "text",
                    "text": f"Write a brief technical explanation of {topic}"
                }
            )
        ],
        maxTokens=300,
    )
    draft_result = await server.sampling_service.create_message(draft_params)
    draft = draft_result.content.text

    # Second pass: refine for clarity
    refine_params = CreateMessageRequestParams(
        messages=[
            SamplingMessage(
                role=Role.user,
                content={
                    "type": "text",
                    "text": f"Improve this explanation for clarity and add an example:\n\n{draft}"
                }
            )
        ],
        maxTokens=400,
    )
    refine_result = await server.sampling_service.create_message(refine_params)

    return refine_result.content.text
```

## See Also

- **Elicitation**: Request structured user input instead of LLM completions (`docs/openmcp/elicitation.md`)
- **Context API**: Access logging and progress from within tools (`docs/openmcp/context.md`)
- **Tools**: Build tools that can invoke sampling (`docs/openmcp/tools.md`)
- **MCP Specification**: Official sampling capability spec (https://modelcontextprotocol.io/specification/2025-06-18/server/sampling)
