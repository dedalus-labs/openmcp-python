# Server Guide

This chapter documents `openmcp.server.MCPServer`, its capability services, and all runtime knobs that
influence wire behavior.

## Constructing `MCPServer`

```python
from openmcp import MCPServer, AuthorizationConfig
from mcp.server.transport_security import TransportSecuritySettings

server = MCPServer(
    name="demo",
    version="0.1.0",
    instructions="Example server",
    website_url="https://demo.local",
    icons=[],
    notification_flags=NotificationFlags(
        prompts_changed=True,
        resources_changed=True,
        tools_changed=True,
    ),
    http_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:8000"],
    ),
    authorization=AuthorizationConfig(
        enabled=True,
        required_scopes=["mcp:read"],
        authorization_servers=["https://as.dedaluslabs.ai"],
        fail_open=False,
    ),
)
```

### Constructor Parameters

| Parameter            | Type                                     | Default | Notes |
| -------------------- | ---------------------------------------- | ------- | ----- |
| `name`               | `str`                                    | —       | Identifier advertised in `initialize` response. |
| `version`            | `str | None`                             | `None`  | Optional server version shown to clients. |
| `instructions`       | `str | None`                             | `None`  | Free-form guidance for clients. |
| `website_url`        | `str | None`                             | `None`  | Optional informational URL. |
| `icons`              | `list[types.Icon] | None`                | `None`  | Icons exposed via `initialize`. |
| `notification_flags` | `NotificationFlags | None`               | all `False` | Controls whether list change notifications are advertised. |
| `experimental_capabilities` | `Mapping[str, Mapping[str, Any]] | None` | {} | Copied into the `experimental` section of capabilities. |
| `lifespan`           | `Callable[[Server], Any]`                | SDK default | Hook for custom startup/shutdown tasks. |
| `transport`          | `str | None`                             | `"streamable-http"` | Default transport for `serve()`. |
| `notification_sink`  | `NotificationSink | None`                | `DefaultNotificationSink()` | Handles outbound notifications. |
| `http_security`      | `TransportSecuritySettings | None`       | DNS rebinding protection on | Applies only to streamable HTTP transport. |
| `authorization`      | `AuthorizationConfig | None`             | disabled | When enabled, serves PRM and enforces bearer tokens. |
| `streamable_http_stateless` | `bool` | `False` | When `True`, each Streamable HTTP request is handled independently with no session tracking—useful for FaaS deployments. |
| `allow_dynamic_tools` | `bool` | `False` | Enables runtime mutations of tools/prompts/resources. When `True`, you **must** emit the corresponding list-change notifications. |

### Notification Flags

- `prompts_changed`, `resources_changed`, `tools_changed`: when set, the server advertises the ability
  to emit `notifications/.../list_changed`. Call `notify_prompts_list_changed()` / etc. after mutating
  registries.

### Capability stability

OpenMCP defaults to **static** capability lists: declare tools, prompts, and resources inside `with server.binding(): …` during startup and never mutate them at runtime. This yields deterministic contracts that enterprise clients rely on.

Set `allow_dynamic_tools=True` to opt into **dynamic** mode. Dynamic servers may re-enter `server.binding()` after startup and mutate capability registries, but they **must**:

1. Emit the appropriate list-change notification (`await server.notify_tools_list_changed()` / etc.).
2. Communicate clearly with clients that the surface is fluid.
3. Avoid surprises—wrap mutations behind feature flags, version your APIs, and document expected behaviour.

Static mode raises an error if you attempt to mutate capabilities after `serve()` starts; dynamic mode allows it and logs warnings when you forget to notify clients.

## Capability Services

### Tools

- Register inside `binding()`:

  ```python
  with server.binding():
      @tool(description="Adds two numbers")
      async def add(a: int, b: int) -> int:
          ctx = get_context()
          await ctx.debug("adding", data={"a": a, "b": b})
          return a + b
  ```

- Input schema inference uses `pydantic.TypeAdapter`; unsupported annotations fall back to
  `{ "type": "object", "additionalProperties": True }`.
- Return annotations auto-populate `outputSchema`. Non-object types are wrapped as
  `{ "type": "object", "properties": { "result": <schema> }, "required": ["result"] }`.
- Runtime normalisation (`normalize_tool_result`) ensures `structuredContent` mirrors the returned
  data (dicts, dataclasses, pydantic models, scalars).
- Allow-/deny-lists: `server.allow_tools([...])` limits the exposed surface. Disabled tools remain
  registered and can be re-enabled later.
- Runtime mutations require `allow_dynamic_tools=True` and a follow-up call to
  `await server.notify_tools_list_changed()` so clients stay in sync.

### Resources & Templates

- `@resource(uri, mime_type=...)` registers synchronous callables returning `str` or `bytes`.
- `normalize_resource_payload` converts dataclasses/pydantic models to JSON text and wraps bytes as
  base64 blobs.
- Pagination default is 50 items; override via `_PAGINATION_LIMIT` or custom service.
- Templates: `@resource_template(uri_template=..., argument_schema=...)` adds parameterised resources.

### Prompts & Completions

- `@prompt(name, arguments=[...])` registers templates. Attachment uses `types.PromptMessage` or simple
  `(role, content)` tuples.
- `@completion(prompt="...", when="tool:plan_trip")` binds structured completions.
- The `CompletionService` accepts iterables of strings, `CompletionResult`, or raw mappings
  (`{"values": [...], "total": ...}`).

### Sampling & Elicitation

- Both services check client capabilities before forwarding.
- Sampling uses configurable semaphore (`MAX_CONCURRENT=4`) and cool-down thresholds.
- Elicitation validates schemas to ensure the server never requests unsupported types.

### Logging & Progress

- `get_context().info/debug/warning/error` send structured log notifications (see
  `docs/openmcp/context.md`).
- `get_context().progress(total)` yields a coalescing progress tracker respecting spec semantics.

### Authorization (Opt-in)

- When `AuthorizationConfig.enabled` is `True`:
  - PRM is served at `metadata_path` with `Cache-Control` headers and canonical resource URI.
  - The ASGI app is wrapped with bearer auth middleware. Use `set_authorization_provider()` to insert a
    provider that validates tokens (e.g., against JWKS).
  - `fail_open=True` allows fallback acceptance during outages (intended for dev only).

### Transport Helpers

- STDIO: `server.serve(transport="stdio")`
- Streamable HTTP: `server.serve(transport="streamable-http", host=..., port=..., path="/mcp")`
- Additional Uvicorn settings can be supplied via `uvicorn_options={"reload": True}`.
- Custom transport: implement `BaseTransport` and call `server.register_transport(name, factory)`.

All transport helpers log a single startup message through the server logger. Suppress it with
`server.serve(verbose=False)` or the transport-specific `announce=False` parameter, or adjust
verbosity via `openmcp.utils.logger.setup_logger()`.

## Operational Hooks

### Heartbeats & Ping

- `server.start_ping_heartbeat(task_group, interval=5.0, jitter=0.2, timeout=2.0, ...)` launches
  periodic liveness probes. Configure thresholds to suit deployment latency.
- `server.ping_client(session)` sends ad-hoc pings.

### Subscriptions

- `ResourcesService` tracks subscribers; call `server.notify_resource_updated(uri)` after data changes.
- Subscription manager handles garbage collection of dead sessions and duplicate registrations.

### Pagination Defaults

- `_PAGINATION_LIMIT` is 50; override by subclassing `MCPServer` or adjusting per-service.
- `paginate_sequence` slices lists and emits opaque cursors.

### Logging

- Uses the shared `openmcp.utils.get_logger` helper. Configure via environment (`OPENMCP_LOG_LEVEL`) or
  replace the `NotificationSink` to integrate external observability stacks.

## Putting It Together

A minimal HTTP server exposing tools, resources, prompts, sampling, and authorization scaffolding is
available in `examples/full_demo/server.py` (see `docs/openmcp/manual/examples.md`). For quick-start
instructions, check `docs/openmcp/getting-started.md`.
