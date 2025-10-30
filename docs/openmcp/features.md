# OpenMCP Features

**Protocol Version**: 2025-06-18
**Status**: Production

## Core Protocol

- Full MCP 2025-06-18 compliance (initialization, JSON-RPC 2.0, version negotiation)
- Request cancellation (`notifications/cancelled`)
- Progress tracking with token-based notifications
- Cursor-based pagination on all list endpoints
- Ping with phi-accrual failure detection (adaptive suspicion metric, RTT tracking)

## Server Capabilities

**Tools**
- Ambient registration via `@tool` decorator
- Automatic JSON Schema inference from Python type hints (Pydantic)
- `tools/list` (paginated), `tools/call`, `notifications/tools/list_changed`
- Allow-list filtering, output schema validation
- Result normalization (arbitrary types → `CallToolResult`)

**Resources**
- Static resources (`@resource`) and templates (`@resource_template`)
- `resources/list`, `resources/read`, `resources/templates/list`
- Full subscription support: `subscribe`, `unsubscribe`, `notifications/resources/updated`
- Text and blob (base64) content types
- Thread-safe subscription manager with weak references

**Prompts**
- `@prompt` decorator with argument schemas
- `prompts/list`, `prompts/get`, `notifications/prompts/list_changed`
- Message coercion (tuples/dicts → `PromptMessage`)
- Content blocks (text, image, audio, embedded resources)

**Completion**
- `completion/complete` for argument autocompletion
- Supports `PromptReference` and `ResourceTemplateReference`
- 100-item limit enforcement per spec

**Logging**
- `logging/setLevel`, `notifications/message`
- Per-session level tracking, Python logging bridge
- All 8 log levels (debug → emergency)

## Client Capabilities

**Sampling**
- `sampling/createMessage` - server requests LLM completions
- Concurrency control (semaphore), circuit breaker (3 failures → 30s cooldown)
- 60s timeout (configurable)

**Roots**
- `roots/list` with versioned caching, `notifications/roots/list_changed`
- Path validation (`RootGuard` prevents traversal attacks)
- `@require_within_roots()` decorator for handlers
- File URI parsing (Windows + POSIX), symlink resolution

**Elicitation** (NEW in 2025-06-18)
- `elicitation/create` - server requests structured user input
- Schema validation (top-level properties only)

## Transports

**STDIO**
- Newline-delimited JSON-RPC, spec-compliant

**Streamable HTTP**
- POST for requests, SSE streaming for server push
- Session management (`Mcp-Session-Id`), protocol version headers
- Security: DNS rebinding protection, host/origin allowlists
- OAuth metadata endpoint (`/.well-known/oauth-protected-resource`)

**Lambda HTTP** (client extension)
- POST-only mode for stateless serverless environments

## Operational Features

- **Schema inference**: Input/output schemas from Python types, caching
- **Result normalization**: Dataclasses, Pydantic models, tuples → spec types
- **Subscription management**: Bidirectional indexes, O(1) lookups, automatic cleanup
- **Notification broadcasting**: Observer registry, stale session cleanup
- **Context API**: `get_context()` for progress/logging in handlers
- **Authorization framework**: OAuth 2.1 scaffolding, provider protocol (no default provider)

## Enhancements Beyond Spec

- Phi-accrual failure detection (vs binary alive/dead)
- Circuit breakers on sampling/elicitation
- Schema caching to avoid repeated reflection
- `RootGuard` security validation
- Progress notification coalescing
- Telemetry hooks for monitoring

## Compliance: 98%

All mandatory protocol features implemented. All 9 optional capabilities fully supported (5 server-side, 4 client-side). Authorization framework present but requires external provider plugin.

## References

- **Cookbook**: `docs/openmcp/cookbook.md` - Copy-paste examples for every feature
- **Full examples**: `examples/` - hello_trip, full_demo, auth_stub, cancellation, progress_logging
- **Guides**: `docs/openmcp/manual/` - Server, client, security, configuration
- **Spec**: `docs/mcp/spec/` - Protocol specification
