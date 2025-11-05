# OpenMCP Server Quality Execution Spec

**Purpose**: Establish guardrails that keep OpenMCP servers spec-compliant even when applications swap or disable default services.

**Background**: Today, any `MCPServer` instance that can complete the import handshake is considered "valid". The framework does not verify that required capabilities remain wired or that services still respect behaviours the spec calls for (ping responsiveness, list-change notifications, cancellation handling, etc.). We need proactive checks and tests so "composable" does not drift into "undefined".

**Scope**: Runtime validation, service-level contracts, and documentation of non-negotiable invariants. Transport ergonomics, docs, and client work are out of scope for this spec.

---

## Phase 1 – Runtime Guardrails

1. **`MCPServer.validate()` self-test (blocking)**
   - Fail fast when core services are missing or misconfigured.
   - Check that each advertised capability has a concrete service bound (`tools`, `prompts`, `resources`, `roots`, `sampling`, `elicitation`, `logging`).
   - Verify notification hooks (`notify_*`) delegate to a sink.
   - Emit actionable error messages telling integrators what to fix.

2. **Default startup validation**
   - `serve*` helpers call `validate()` before opening transports (opt-out flag for power users).
   - Tests cover "happy path" and at least one failure scenario (e.g., `server.prompts = None`).

## Phase 2 – Service Contracts

1. **Protocol definitions**
   - Introduce typing.Protocols (e.g., `PromptsServiceProtocol`) describing the minimal surface each service must expose.
   - Enforce via `MCPServer` type hints and runtime isinstance checks in `validate()`.

2. **Spec-driven behaviour tests**
   - Add integration tests that simulate capability usage and confirm side effects:
     - Ping handler registers heartbeat, updates suspicion scores.
     - Tools/resources/prompt list handlers emit list-changed notifications when toggled.
     - Cancellation flow respects notification semantics.

## Phase 3 – Developer Feedback Loop

1. **Diagnostics**
   - Boot logs summarise enabled capabilities and highlight disabled ones.
   - Warnings when list-changed notifications are permanently disabled while capability is advertised.

2. **Documentation update**
   - Author a "Server invariants" section describing the non-negotiable guarantees and how to run `validate()` manually.

## Phase 4 – Logging Minimalism

1. **Minimal runtime dependencies**
   - Replace `openmcp.utils.logger` Rich/orjson setup with a stdlib-only configuration helper.
   - Allow optional JSON mode via a user-supplied serializer callback so downstream apps can opt into `orjson` (document the pattern without bundling it).

2. **Documentation & examples**
   - Update logging docs to explain the minimalist philosophy and how to integrate custom logging stacks.
   - Add an example demonstrating how to wire OpenMCP logging to an application-defined serializer (e.g., using `orjson`).

3. **Validation**
   - Ensure `tests/test_logging.py` continues to pass and cover the new helper behaviour.

## Completion Criteria

- `MCPServer.validate()` implemented and invoked from default serve paths.
- Service protocols defined and used for runtime checks.
- New tests cover failure cases for removed/misaligned services and success cases for default stack.
- Logging helper is stdlib-only by default, with documented extension points.
- Release notes/docs updated to explain the validation story.
- No regressions across existing test suite.
