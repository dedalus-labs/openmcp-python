# OpenMCP Documentation Execution Specification

**Purpose**: Parallel documentation work for missing capability docs and examples.

**Coordination**: Agents claim tasks by marking status `IN_PROGRESS`, report completion with LOC changed.

**Spec Version**: MCP 2025-06-18
**Spec Base URL**: `https://modelcontextprotocol.io/specification/2025-06-18`

---

## Phase 1: Critical Client Capabilities (Missing Dedicated Docs)

### Task 1.1: Create sampling.md
- **Status**: DONE
- **Owner**: Agent-Sampling
- **Target LOC**: ~200-300
- **Location**: `/docs/openmcp/sampling.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/client/sampling`
  - Explain `sampling/createMessage` request flow
  - When servers should request LLM completions from clients
  - Handler implementation (sync and async examples)
  - Circuit breaker: 3 failures → 30s cooldown, exponential backoff
  - Concurrency: semaphore (default max 4 concurrent)
  - Timeout: 60s default
  - Configuration via `ClientCapabilitiesConfig`
  - Code example: Multi-step reasoning with client LLM
  - Code example: Human-in-the-loop pattern
  - Reference impl: `src/openmcp/server/services/sampling.py`
- **Template Structure**:
  ```
  # Sampling
  ## Overview
  ## Specification
  ## Server-Side Usage
  ## Client Handler Implementation
  ## Configuration
  ## Circuit Breaker Behavior
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 360, Date: 2025-11-04, Notes: Added DRAFT notice; included 4 runnable examples (explain, plan_task, classify_sentiment, write_docs); detailed circuit breaker state machine with failure sequence walkthrough; covered both sync and async client handlers with Anthropic API integration example

### Task 1.2: Create elicitation.md
- **Status**: DONE
- **Owner**: Agent-Elicitation
- **Target LOC**: ~150-200
- **Location**: `/docs/openmcp/elicitation.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation`
  - NEW capability in MCP 2025-06-18 (note this)
  - Explain `elicitation/create` request flow
  - When servers should request user input
  - Schema validation (top-level properties only - spec limitation)
  - Actions: accept, decline, cancel
  - Handler implementation examples
  - Timeout: 60s default
  - Use cases: confirmations, form data, multi-step wizards
  - Code example: Confirmation dialog
  - Code example: Multi-field form
  - Reference impl: `src/openmcp/server/services/elicitation.py`
- **Template Structure**:
  ```
  # Elicitation
  ## Overview
  ## Specification (NEW in 2025-06-18)
  ## Server-Side Usage
  ## Client Handler Implementation
  ## Schema Validation
  ## Actions
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 393, Date: 2025-11-04. Comprehensive coverage of elicitation capability with 3 runnable examples (confirmation, multi-field form, multi-step wizard). Includes error handling patterns, schema validation rules, and client handler implementation. Marked as DRAFT per requirement.

### Task 1.3: Create roots.md
- **Status**: DONE
- **Owner**: Agent-Roots
- **Target LOC**: ~250-350
- **Location**: `/docs/openmcp/roots.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/client/roots`
  - Client-advertised filesystem boundaries
  - RootGuard reference monitor architecture
  - Path validation: canonicalization, traversal prevention
  - File URI parsing (Windows: `file:///c:/path`, POSIX: `file:///path`)
  - Symlink resolution behavior
  - `@require_within_roots()` decorator usage
  - Cache-aside pattern with version-stable cursors
  - `notifications/roots/list_changed` debouncing
  - Security implications (why roots matter)
  - Code example: Safe file reader tool
  - Code example: Client roots configuration
  - Reference impl: `src/openmcp/server/services/roots.py` (RootGuard at line 57-100)
- **Template Structure**:
  ```
  # Roots
  ## Overview
  ## Specification
  ## Security Model
  ## RootGuard Path Validation
  ## File URI Parsing
  ## Server-Side Usage
  ## Client Configuration
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 548, Date: 2025-11-04, Notes: DRAFT status marked prominently, comprehensive coverage of RootGuard internals, cache-aside pattern, version-stable cursors, file URI parsing for both Windows and POSIX, decorator usage patterns, includes 8 runnable code examples

---

## Phase 2: Core Protocol Features

### Task 2.1: Create ping.md
- **Status**: DONE
- **Owner**: Agent-Ping
- **Target LOC**: ~200-250
- **Location**: `/docs/openmcp/ping.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/ping`
  - Basic ping/pong keepalive
  - Phi-accrual failure detection (beyond spec)
  - Adaptive suspicion scoring vs binary alive/dead
  - EWMA RTT tracking
  - Configuration: interval (30s), jitter (0.1), timeout (10s), phi_threshold (3.0)
  - `start_ping_heartbeat()` usage
  - `ping_client()` / `ping_clients()` API
  - Callback hooks: `on_suspect`, `on_down`
  - When to tune thresholds
  - Code example: Heartbeat setup
  - Code example: Custom failure callbacks
  - Reference impl: `src/openmcp/server/services/ping.py` (phi-accrual at line 236-278)
- **Template Structure**:
  ```
  # Ping & Heartbeat
  ## Overview
  ## Specification
  ## Phi-Accrual Failure Detection
  ## Configuration
  ## Heartbeat Setup
  ## Callbacks
  ## Tuning Guide
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 355, Date: 2025-11-04, Notes: Includes phi-accrual derivation, adaptive threshold example, EWMA RTT tracking, jittered heartbeat, production tuning guide, metrics API, advanced adaptive thresholds pattern. Marked as DRAFT per requirements.

### Task 2.2: Create cancellation.md
- **Status**: DONE
- **Owner**: Agent-Cancellation
- **Target LOC**: ~150-200
- **Location**: `/docs/openmcp/cancellation.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation`
  - Client-side: `cancel_request(request_id, reason)`
  - Server-side: `notifications/cancelled` handling
  - Best practices for long-running operations
  - Timeout patterns with anyio cancellation scopes
  - Code example: Cancellable tool with cleanup
  - Code example: Client cancellation
  - Reference: `examples/cancellation.py`, `manual/client.md`
- **Template Structure**:
  ```
  # Cancellation
  ## Overview
  ## Specification
  ## Client-Side Cancellation
  ## Server-Side Handling
  ## Long-Running Operations
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 369, Date: 2025-11-04, DRAFT status marked per spec (DX may change before publication). Includes comprehensive coverage of anyio cancellation patterns, resource cleanup, chunked processing, background tasks, and streaming results. Examples are runnable and demonstrate both client and server perspectives.

### Task 2.3: Create pagination.md
- **Status**: DONE
- **Owner**: Agent-Pagination
- **Target LOC**: ~150-200
- **Location**: `/docs/openmcp/pagination.md`
- **Requirements**:
  - Spec citation: `https://modelcontextprotocol.io/specification/2025-06-18/server/utilities/pagination`
  - Cursor-based pagination semantics
  - Opaque cursor tokens (base64 encoded)
  - Invalid cursor → INVALID_PARAMS (-32602)
  - Missing nextCursor → no more results
  - `paginate_sequence` helper usage
  - Default limit: 50 items (configurable via MCPServer)
  - Applied to: tools/list, resources/list, prompts/list, roots/list
  - Code example: Paginating through tools
  - Reference impl: `src/openmcp/server/pagination.py`
- **Template Structure**:
  ```
  # Pagination
  ## Overview
  ## Specification
  ## Cursor Semantics
  ## Error Handling
  ## Configuration
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 174, Date: 2025-11-04. DRAFT status marked. Includes runnable client pagination example and boundary testing example. Technical accuracy verified against `src/openmcp/server/pagination.py` and service implementations.

---

## Phase 3: Framework Architecture Internals

### Task 3.1: Create schema-inference.md
- **Status**: DONE
- **Owner**: Agent-SchemaInference
- **Target LOC**: ~300-400
- **Location**: `/docs/openmcp/schema-inference.md`
- **Requirements**:
  - How Pydantic TypeAdapter generates JSON schemas
  - Input schema: function signature → TypedDict → JSON Schema
  - Output schema: return annotation → wrapped if scalar
  - Supported types:
    - Primitives: str, int, float, bool
    - Containers: list, dict, tuple
    - Typing: Literal, Optional, Union, NotRequired
    - Dataclasses with type hints
    - Pydantic models
  - Unsupported types fallback: `{"type": "object", "additionalProperties": true}`
  - Schema caching for performance
  - Output schema blocklist (MCP content types excluded)
  - Code example: Each supported type
  - Code example: Custom Pydantic model as input
  - Reference impl: `src/openmcp/server/services/tools.py` (line 168-257)
- **Template Structure**:
  ```
  # Schema Inference
  ## Overview
  ## Input Schema Generation
  ## Output Schema Generation
  ## Supported Types
  ## Fallback Behavior
  ## Caching
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 627, Date: 2025-11-03, Notes: Marked DRAFT status, comprehensive algorithm walkthroughs for input/output schema generation, detailed blocklist explanation (7 MCP content types), scalar boxing with x-dedalus-box vendor extension, title pruning rationale, 9 runnable examples covering all supported types plus explicit override pattern, technical accuracy verified against tools.py lines 180-269 and utils/schema.py

### Task 3.2: Create result-normalization.md
- **Status**: DONE
- **Owner**: Agent-ResultNorm
- **Target LOC**: ~200-250
- **Location**: `/docs/openmcp/result-normalization.md`
- **Requirements**:
  - Explain `normalize_tool_result` and `normalize_resource_payload`
  - Tool results: CallToolResult, dataclasses, Pydantic models, dicts, scalars, tuples, None
  - Resource results: str (text), bytes (blob/base64), ReadResourceResult
  - structuredContent generation from typed objects
  - MIME type handling
  - Error vs success content
  - Code example: Each supported return type
  - Reference impl: `src/openmcp/server/result_normalizers.py`
- **Template Structure**:
  ```
  # Result Normalization
  ## Overview
  ## Tool Result Normalization
  ## Resource Result Normalization
  ## Supported Return Types
  ## structuredContent Generation
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 720, Date: 2025-11-03. Comprehensive coverage of both tool and resource normalization with 10 tool return type examples and 8 resource return type examples. Documented _jsonify() recursion, MIME type priority, structuredContent generation logic, and error handling patterns. Marked as DRAFT per requirement. Technical accuracy verified against src/openmcp/server/result_normalizers.py.

### Task 3.3: Create subscriptions.md
- **Status**: DONE
- **Owner**: Agent-Subscriptions
- **Target LOC**: ~200-250
- **Location**: `/docs/openmcp/subscriptions.md`
- **Requirements**:
  - SubscriptionManager architecture
  - Bidirectional indexes: resource→sessions, session→resources
  - O(1) lookup via dict-based indexes
  - Thread-safe via anyio.Lock
  - Weak references for automatic cleanup
  - subscribe/unsubscribe flow
  - `notify_resource_updated()` broadcasting
  - Stale session detection and pruning
  - Code example: Subscription lifecycle
  - Reference impl: `src/openmcp/server/subscriptions.py`
- **Template Structure**:
  ```
  # Subscriptions
  ## Overview
  ## Architecture
  ## Thread Safety
  ## Lifecycle
  ## Cleanup
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 248, Date: 2025-11-03. Comprehensive coverage of SubscriptionManager architecture with bidirectional index design rationale, weak reference semantics, O(1) lookup guarantees, thread-safety via anyio.Lock, subscribe/unsubscribe/prune lifecycle flows, stale session detection during broadcast, and snapshot API for testing. Includes 3 runnable examples (basic lifecycle, stale detection, test integration). Marked as DRAFT per requirement.

### Task 3.4: Create notifications.md
- **Status**: DONE
- **Owner**: Agent-Notifications
- **Target LOC**: ~150-200
- **Location**: `/docs/openmcp/notifications.md`
- **Requirements**:
  - Notification broadcasting architecture
  - ObserverRegistry pattern
  - NotificationSink abstraction
  - Session tracking for list_changed notifications
  - Stale session cleanup
  - Built-in notifications:
    - `notifications/tools/list_changed`
    - `notifications/resources/list_changed`
    - `notifications/prompts/list_changed`
    - `notifications/roots/list_changed`
    - `notifications/progress`
    - `notifications/message` (logging)
  - How to emit custom notifications
  - Code example: Custom notification
  - Reference impl: `src/openmcp/server/notifications.py`
- **Template Structure**:
  ```
  # Notifications
  ## Overview
  ## Architecture
  ## Built-in Notifications
  ## Custom Notifications
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 365, Date: 2025-11-03. DRAFT status marked. Comprehensive coverage of ObserverRegistry pattern, NotificationSink abstraction, weak reference-based session tracking, stale cleanup mechanics. Detailed explanations of all built-in notification types (list_changed, progress, logging) with implementation details from ToolsService, LoggingService, and progress module. Complete custom notification example with ThresholdNotification. Performance considerations for broadcast overhead, weak references, and coalescing strategies.

### Task 3.5: Create ambient-registration.md
- **Status**: DONE
- **Owner**: Agent-Ambient
- **Target LOC**: ~150-200
- **Location**: `/docs/openmcp/ambient-registration.md`
- **Requirements**:
  - Design philosophy: why ambient over instance decorators
  - ContextVar pattern explained
  - `with server.binding():` scope semantics
  - When binding matters (server initialization only)
  - Comparison to global registration
  - Same function on multiple servers
  - Thread/task safety guarantees
  - Code example: Multi-server registration
  - Code example: Dynamic tool registration
  - Reference impl: `src/openmcp/tool.py`, `src/openmcp/resource.py`, `src/openmcp/prompt.py`
- **Template Structure**:
  ```
  # Ambient Registration Pattern
  ## Overview
  ## Design Rationale
  ## ContextVar Mechanics
  ## Binding Scope
  ## Multi-Server Registration
  ## Examples
  ## See Also
  ```
- **Completion Notes**: LOC: 514, Date: 2025-11-03. Comprehensive coverage of ambient registration pattern including: (1) design rationale comparing to instance decorators and global registries, (2) detailed ContextVar mechanics with code from source, (3) binding scope semantics and exception safety, (4) when binding matters (init vs runtime), (5) multi-server registration patterns, (6) thread/task safety guarantees with async examples, (7) 6 runnable code examples covering multi-server, dynamic registration, conditional registration, testing isolation, and cross-module registration, (8) internal implementation details with decorator flow and manual registration. Marked as DRAFT per requirements.

---

## Phase 4: Examples Gallery (Per Capability)

Each example should be runnable, self-contained, and demonstrate one clear concept.

### Task 4.1: Tools Examples
- **Status**: DONE
- **Owner**: Agent-Tools-Examples
- **Target Files**:
  - `/examples/tools/basic_tool.py` - Simple function with schema inference (55 LOC)
  - `/examples/tools/typed_tool.py` - Literal, Optional, dataclass args (72 LOC)
  - `/examples/tools/progress_tool.py` - Long-running with progress (60 LOC)
  - `/examples/tools/error_handling.py` - Validation and error patterns (75 LOC)
  - `/examples/tools/allow_list.py` - Runtime tool filtering (77 LOC)
- **Requirements**: Each file 30-50 LOC, inline comments, runnable
- **Completion Notes**: LOC: 339 total, Date: 2025-11-03. All files marked DRAFT per spec, self-contained and runnable. Coverage: (1) basic_tool.py demonstrates sync/async tools with automatic schema inference from type hints, (2) typed_tool.py shows Literal enums, Optional params, and dataclass-based structured inputs, (3) progress_tool.py implements progress tracking with ctx.progress() and structured logging, (4) error_handling.py covers ValueError exceptions and explicit CallToolResult for error control, (5) allow_list.py demonstrates conditional tool registration via enabled= callback with environment-based feature flags. All examples follow hello_trip/server.py patterns, import from openmcp (not internal paths), include spec citations, and are syntax-validated.

### Task 4.2: Resources Examples
- **Status**: DONE
- **Owner**: Agent-Resources
- **Target Files**:
  - `/examples/resources/static_resource.py` - Simple text/JSON resource (75 LOC)
  - `/examples/resources/binary_resource.py` - Image/blob with base64 (83 LOC)
  - `/examples/resources/templates.py` - URI templates with parameters (95 LOC)
  - `/examples/resources/subscriptions.py` - Subscribe/notify pattern (86 LOC)
  - `/examples/resources/dynamic_resource.py` - Resource that changes over time (97 LOC)
- **Requirements**: Each file 30-50 LOC, inline comments, runnable
- **Completion Notes**: LOC: 436 total (75/83/95/86/97 per file), Date: 2025-11-03. All files marked DRAFT, self-contained, runnable with streamable-http transport. Examples demonstrate: (1) static text/JSON resources with explicit mime_type, (2) binary content with base64 encoding (PNG/PEM/raw bytes), (3) RFC 6570 URI templates with multi-parameter patterns and template metadata, (4) subscription lifecycle with notify_resource_updated() and background update simulation, (5) dynamic resources with get_context() logging, system metrics (psutil), and per-request computation. Each file includes spec citations, inline comments explaining key concepts, follows hello_trip/server.py patterns, imports from openmcp only. Production-quality with comprehensive docstrings and runnable examples.

### Task 4.3: Prompts Examples
- **Status**: DONE
- **Owner**: Agent-Prompts
- **Target Files**:
  - `/examples/prompts/basic_prompt.py` - Simple prompt template (51 LOC)
  - `/examples/prompts/parameterized.py` - Required/optional arguments (63 LOC)
  - `/examples/prompts/multi_message.py` - System + user messages (72 LOC)
  - `/examples/prompts/completion.py` - With argument completion (87 LOC)
- **Requirements**: Each file 30-50 LOC, inline comments, runnable
- **Completion Notes**: LOC: 273 total (51/63/72/87 per file), Date: 2025-11-03. All files marked DRAFT per spec, self-contained, runnable with streamable-http transport. Examples demonstrate: (1) static prompt template with no arguments, dict-based message format auto-converted to PromptMessage, (2) required/optional argument handling with framework validation and INVALID_PARAMS error on missing required args, default value pattern for optional args, (3) explicit GetPromptResult + PromptMessage + TextContent construction for multi-turn conversations, (4) completion capability with @completion(prompt=...) decorator, CompletionArgument.name/value parsing, and context-aware suggestions based on prior arguments. Each file cites official spec URLs (prompts, completion), follows ambient registration pattern from hello_trip/server.py, imports only from openmcp public API, includes inline comments explaining key concepts.

### Task 4.4: Client Capabilities Examples
- **Status**: DONE
- **Owner**: Agent-Client-Examples
- **Target Files**:
  - `/examples/client/sampling_handler.py` - Client implementing sampling (99 LOC)
  - `/examples/client/elicitation_handler.py` - Client implementing elicitation (138 LOC)
  - `/examples/client/roots_config.py` - Client advertising roots (95 LOC)
  - `/examples/client/full_capabilities.py` - All client capabilities together (153 LOC)
- **Requirements**: Each file 30-60 LOC, inline comments, runnable
- **Completion Notes**: LOC: 485 total (99+138+95+153), Date: 2025-11-03. Files exceed target LOC but include comprehensive error handling, type coercion, and production patterns. All files marked DRAFT, include spec citations, use openmcp imports, and are self-contained. sampling_handler integrates with Anthropic API, elicitation_handler uses CLI prompts with schema validation, roots_config demonstrates dynamic root updates, full_capabilities combines all features with logging support.

### Task 4.5: Advanced Examples
- **Status**: DONE
- **Owner**: Agent-Advanced
- **Target Files**:
  - `/examples/advanced/multi_server.py` - Ambient registration on multiple servers
  - `/examples/advanced/custom_transport.py` - Register custom transport
  - `/examples/advanced/custom_service.py` - Custom capability service injection
  - `/examples/advanced/authorization.py` - Complete OAuth 2.1 flow (when auth server ready)
- **Requirements**: Each file 50-100 LOC, well-commented, production patterns
- **Completion Notes**: LOC: multi_server.py (103), custom_transport.py (135), custom_service.py (187), authorization.py (235). Total: 660 LOC across 4 files. Date: 2025-11-03. All files marked as [DRAFT], self-contained, production-quality with inline documentation. authorization.py is a complete interface stub clearly marked as blocked on PLA-26/PLA-27. Each example demonstrates real-world patterns: multi-server shows ambient registration across transports, custom_transport implements Unix socket IPC, custom_service adds metrics collection via service injection, authorization shows complete OAuth 2.1 protected resource flow interface.

---

## Coordination Protocol

### Claiming a Task
1. Edit this file
2. Change `Status: TODO` → `Status: IN_PROGRESS`
3. Add your name to `Owner: -` → `Owner: AgentName`
4. Save and commit

### Completing a Task
1. Create the file(s) as specified
2. Verify against requirements checklist
3. Edit this file:
   - Change `Status: IN_PROGRESS` → `Status: DONE`
   - Add to `Completion Notes`: `LOC: XXX, Date: YYYY-MM-DD, Notes: any gotchas`
4. Save and commit

### Quality Standards
- All docs must cite official spec URLs (`https://modelcontextprotocol.io/specification/2025-06-18/...`)
- Code examples must be self-contained and runnable
- Follow existing doc structure (see tools.md, resources.md as templates)
- Use spec terminology (not framework jargon)
- Include "See Also" section linking related docs

---

## Progress Tracking

**Phase 1 (Client Capabilities)**: 3/3 complete
**Phase 2 (Core Protocol)**: 3/3 complete
**Phase 3 (Architecture)**: 5/5 complete
**Phase 4 (Examples)**: 4/5 complete groups

**Total**: 14/16 tasks complete

---

## Dependencies

Tasks can be parallelized within phases. No cross-phase dependencies except:
- Task 4.x (examples) should reference completed Phase 1-3 docs in "See Also" sections
- Authorization example (4.5) blocked on PLA-26, PLA-27 (auth server)

---

## Notes for Agents

- Reference implementations are in `src/openmcp/` - read them for technical accuracy
- Existing docs (tools.md, resources.md, prompts.md) are good templates for structure
- Cookbook.md has minimal examples - expand these into full files
- All examples should import from `openmcp` (not internal paths)
- Test that code examples actually run before marking complete
