# Examples Gallery

The `examples/` directory contains runnable scripts that demonstrate every capability. Each example
assumes a Python virtual environment with the project’s dependencies installed (see `README.md`).

## Index

| Example | Path | Highlights |
| ------- | ---- | ---------- |
| Hello Trip | `examples/hello_trip/` | Tools, resources, prompts, HTTP/STDIO transports. |
| Full Capability Demo | `examples/full_demo/` | Tools/resources/prompts, completions, sampling, elicitation, logging, progress. |
| Authorization Stub | `examples/auth_stub/` | Shows how to enable `AuthorizationConfig` and provide a dummy token validator. |
| Progress & Logging | `examples/progress_logging.py` | Uses `get_context()` to emit progress telemetry and structured log messages. |
| Cancellation | `examples/cancellation.py` | Client-side cancellation using `MCPClient.cancel_request`. |

Below are excerpts illustrating common patterns.

## 1. Registering Capabilities

```python
from openmcp import MCPServer, tool, resource, prompt

server = MCPServer("full-demo")

with server.binding():
    @tool(description="Adds numbers")
    async def add(a: int, b: int) -> int:
        return a + b

    @resource("resource://info", mime_type="text/plain")
    def info() -> str:
        return "Demo resource"

    @prompt(name="plan", description="Plan an itinerary")
    def plan_prompt(args: dict[str, str]) -> list[tuple[str, str]]:
        destination = args.get("destination", "somewhere")
        return [
            ("assistant", "You are a planner."),
            ("user", f"Plan a trip to {destination}"),
        ]
```

## 2. Progress Reporting

```python
from openmcp import get_context, tool

@tool(description="Processes batches")
async def process(batch: list[str]) -> str:
    ctx = get_context()
    async with ctx.progress(total=len(batch)) as progress:
        for item in batch:
            await progress.advance(1, message=f"Processed {item}")
    return "done"
```

## 3. Sampling & Elicitation Hooks

```python
from openmcp import MCPServer

server = MCPServer("full-demo")

async def sampling(ref, params, context):
    # produce a synthetic completion without calling an LLM
    return types.CreateMessageResult(
        content=[types.TextContent(type="text", text="Sampled result")]
    )

async def elicitation(ref, params, context):
    return types.ElicitResult(fields={"confirm": True})

# Register handlers via server.completions/sampling/elicitation services…
```

## 4. Authorization Stub

`examples/auth_stub/server.py` demonstrates enabling `AuthorizationConfig`. It accepts the bearer token
`demo-token` and rejects others.

```python
from openmcp import MCPServer, AuthorizationConfig
from openmcp.server.authorization import AuthorizationContext, AuthorizationError

server = MCPServer(
    "auth-demo",
    authorization=AuthorizationConfig(enabled=True, required_scopes=["mcp:read"]),
)

class DemoProvider:
    async def validate(self, token: str) -> AuthorizationContext:
        if token != "demo-token":
            raise AuthorizationError("invalid token")
        return AuthorizationContext(subject="demo", scopes=["mcp:read"], claims={})

server.set_authorization_provider(DemoProvider())
```

Run the example and call the metadata endpoint:

```bash
uv run python examples/auth_stub/server.py
curl -H "Authorization: Bearer demo-token" http://127.0.0.1:3000/mcp
```

## 5. Cancellation

`examples/cancellation.py` shows cancelling long-running tool calls from the client. The script starts a
server locally, issues a tool call, and cancels after two seconds.

## Running Examples

Most examples use `uv` to manage the environment:

```bash
uv run python examples/full_demo/server.py
uv run python examples/full_demo/client.py
```

If you prefer manually activating a virtual environment, install dependencies using
`pip install -e .[dev]` and run the scripts directly.

Each example contains inline comments describing the important configuration knobs. Feel free to copy
and adapt them to your own projects.
