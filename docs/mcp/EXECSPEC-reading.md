# MCP Docs Reading Execution Spec

**Purpose**: Track progress and open questions while reading the upstream MCP documentation set.  
**Owner**: Codex (senior engineer)  
**Last Updated**: 2025-11-04

---

## Scope

Read every document under `docs/mcp`, capture notable requirements, ambiguities, and design cues that should influence OpenMCP. Use this file to log status and comments so future contributors can pick up where we leave off.

---

## Progress Log

| Section | Status | Notes |
| ------- | ------ | ----- |
| `core/lifecycle/index.md` | DONE (2025-11-04) | Lifecycle broken into init → operation → shutdown; includes mermaid overview and cites spec source. |
| `core/lifecycle/lifecycle-phases.md` | DONE (2025-11-04) | Highlights strict init sequence (initialize → response → initialized), version header requirements, capability negotiation matrix, and transport-specific shutdown guidance. |
| `core/understanding-mcp-clients/index.md` | DONE (2025-11-04) | Clarifies host vs protocol client responsibilities; each client manages exactly one server session. |
| `core/understanding-mcp-clients/core-client-features.md` | DONE (2025-11-04) | Details client-provided features (sampling, roots, elicitation) with flows and UX expectations; emphasizes human-in-loop checkpoints. |
| `core/understanding-mcp-servers/index.md` | DONE (2025-11-04) | Defines MCP servers as capability providers (tools/resources/prompts) for host apps. |
| `core/understanding-mcp-servers/core-server-features.md` | DONE (2025-11-04) | Breaks down tools/resources/prompts protocols, UX patterns, and control surfaces (model vs app vs user). |
| `core/understanding-mcp-servers/bringing-servers-together.md` | DONE (2025-11-04) | Illustrates multi-server orchestration with a travel scenario combining prompts, resources, and tools. |
| `core/architecture/index.md` | DONE (2025-11-04) | Summarizes client-host-server architecture and JSON-RPC foundation. |
| `core/architecture/design-principles.md` | DONE (2025-11-04) | Lists guiding principles: easy servers, composability, isolation, progressive capabilities. |
| `core/architecture/core-components.md` | DONE (2025-11-04) | Defines host/client/server roles and responsibilities in the execution model. |
| `core/architecture/capability-negotiation.md` | DONE (2025-11-04) | Describes capability exchange during init and its effect on allowed operations/notifications. |
| `core/lifecycle/error-handling.md` | DONE (2025-11-04) | Emphasizes fallback cases (version mismatch, capability negotiation failure) + sample error payload. |
| `core/lifecycle/timeouts.md` | DONE (2025-11-04) | Recommends per-request timeouts, cancellation on expiry, optional progress-based extensions. |
| `core/authorization/index.md` | DONE (2025-11-04) | Points to authorization spec entry and revision. |
| `core/authorization/introduction.md` | DONE (2025-11-04) | Frames HTTP-focused OAuth 2.1-based authorization; STDIO excluded. |
| `core/authorization/authorization-flow.md` | DONE (2025-11-04) | Details OAuth discovery, dynamic registration, bearer usage, token validation, error codes. |
| `core/authorization/security-considerations.md` | DONE (2025-11-04) | Enumerates OAuth security mandates: PKCE, audience binding, HTTPS, redirect safety, token passthrough bans. |
| `core/cancellation/index.md` | DONE (2025-11-04) | Introduces optional cancellation via notifications. |
| `core/cancellation/behavior-requirements.md` | DONE (2025-11-04) | Specifies constraints (cannot cancel initialize, only same-direction in-flight requests). |
| `core/cancellation/cancellation-flow.md` | DONE (2025-11-04) | Shows cancellation payload structure (requestId + reason). |
| `core/cancellation/error-handling.md` | DONE (2025-11-04) | Advises ignoring invalid/late cancellation notifications. |
| `core/cancellation/implementation-notes.md` | DONE (2025-11-04) | Recommends logging + UI exposure of cancellations. |
| `core/cancellation/timing-considerations.md` | DONE (2025-11-04) | Highlights race conditions where cancellation can arrive after completion. |
| `core/ping/index.md` | DONE (2025-11-04) | Introduces optional ping utility. |
| `core/ping/overview.md` | DONE (2025-11-04) | States ping is simple request/response initiated by either party. |
| `core/ping/message-format.md` | DONE (2025-11-04) | Defines ping JSON-RPC payload (no params). |
| `core/ping/behavior-requirements.md` | DONE (2025-11-04) | Requires empty response + describes timeout handling. |
| `core/ping/error-handling.md` | DONE (2025-11-04) | Notes repeated failure should count as connection failure. |
| `core/ping/implementation-considerations.md` | DONE (2025-11-04) | Recommends configurable cadence, avoid overuse. |
| `core/ping/usage-patterns.md` | DONE (2025-11-04) | Shows simple ping/pong sequence. |
| `core/progress/index.md` | DONE (2025-11-04) | Introduces optional progress notifications. |
| `core/progress/progress-flow.md` | DONE (2025-11-04) | Specifies progressToken negotiation + payload shape (monotonic progress). |
| `core/progress/behavior-requirements.md` | DONE (2025-11-04) | Clarifies tokens must reference active requests; notifications optional frequency. |
| `core/progress/implementation-notes.md` | DONE (2025-11-04) | Recommends tracking tokens, rate limiting, stop on completion. |
| `core/security-best-practices/index.md` | DONE (2025-11-04) | Entry point for security guidance. |
| `core/security-best-practices/introduction.md` | DONE (2025-11-04) | Sets scope: complements authorization, targets implementers. |
| `core/security-best-practices/attacks-and-mitigations.md` | DONE (2025-11-04) | Details confused deputy, token passthrough, session hijack mitigation requirements. |
| `core/transports/index.md` | DONE (2025-11-04) | Lists standard transports (stdio, streamable HTTP) + custom support. |
| `core/transports/stdio.md` | DONE (2025-11-04) | Specifies subprocess launch, newline-delimited JSON, stderr logging expectations. |
| `core/transports/streamable-http.md` | DONE (2025-11-04) | Defines POST/SSE behavior, headers, resumability, protocol-version header handling, and backwards compatibility guidance. |
| `core/transports/custom-transports.md` | DONE (2025-11-04) | Allows bespoke transports as long as JSON-RPC semantics maintained. |

*(Add rows as new sections are reviewed.)*

---

## Open Questions / Follow-ups

- _None yet._

---

## How to Contribute

1. Read a document under `docs/mcp`.
2. Update the table above with `IN_PROGRESS` or `DONE`, date, and key notes.
3. Add any follow-up questions or alignment concerns to the Open Questions list.
| `getting-started/architecture-overview/index.md` | DONE (2025-11-04) | Overview plus links to scope, concepts, example. |
| `getting-started/architecture-overview/scope.md` | DONE (2025-11-04) | Lists MCP ecosystem components; clarifies MCP is context protocol only. |
| `getting-started/architecture-overview/concepts-of-mcp.md` | DONE (2025-11-04) | Defines host/client/server participants, data vs transport layers, primitives and notifications. |
| `getting-started/architecture-overview/example.md` | DONE (2025-11-04) | Step-by-step JSON-RPC walkthrough: init, tools/list, tools/call, notifications. |
| `getting-started/build-an-mcp-client/index.md` | DONE (2025-11-04) | Tutorial for Python client: stdio transport, Claude integration, tool-loop handling, best practices. |
| `getting-started/build-an-mcp-client/next-steps.md` | DONE (2025-11-04) | Links to server/client galleries. |
| `getting-started/build-an-mcp-server/index.md` | DONE (2025-11-04) | Weather server tutorial (Python/Node/Java), logging guidance, STDIO config, host integration steps. |
| `getting-started/build-an-mcp-server/what-s-happening-under-the-hood.md` | DONE (2025-11-04) | Summarizes client→Claude→tool execution pipeline. |
| `getting-started/build-an-mcp-server/troubleshooting.md` | DONE (2025-11-04) | Troubleshooting tips (Claude logs, config paths, API errors). |
| `getting-started/build-an-mcp-server/next-steps.md` | DONE (2025-11-04) | Links to client tutorial, examples, debugging, LLM assistance. |
| `getting-started/model-context-protocol/index.md` | DONE (2025-11-04) | Marketing overview: workflow steps, ecosystem stats, CTA. |
| `getting-started/what-is-the-model-context-protocol-mcp/index.md` | DONE (2025-11-04) | Intro analogy (USB-C), high-level description of MCP connecting AI apps to systems. |
| `getting-started/what-is-the-model-context-protocol-mcp/what-can-mcp-enable.md` | DONE (2025-11-04) | Highlights use-case examples (calendar, design tools, enterprise data). |
| `getting-started/what-is-the-model-context-protocol-mcp/why-does-mcp-matter.md` | DONE (2025-11-04) | Benefits by persona (developers, AI apps, end-users). |
| `getting-started/what-is-the-model-context-protocol-mcp/start-building.md` | DONE (2025-11-04) | CTA cards linking to server/client build tutorials. |
| `getting-started/what-is-the-model-context-protocol-mcp/learn-more.md` | DONE (2025-11-04) | Points to architecture concepts doc. |
| `getting-started/connect-to-local-mcp-servers/index.md` | DONE (2025-11-04) | Tutorial intro for wiring Claude Desktop to local servers; emphasises file access with user approval. |
| `getting-started/connect-to-local-mcp-servers/prerequisites.md` | DONE (2025-11-04) | Requires Claude Desktop + Node.js setup. |
| `getting-started/connect-to-local-mcp-servers/understanding-mcp-servers.md` | DONE (2025-11-04) | Describes filesystem server capabilities and approval workflow. |
| `getting-started/connect-to-local-mcp-servers/installing-the-filesystem-server.md` | DONE (2025-11-04) | Step-by-step config edits for Claude Desktop to launch filesystem server (npx command, path config). |
| `getting-started/connect-to-local-mcp-servers/using-the-filesystem-server.md` | DONE (2025-11-04) | Provides example prompts and approval UX. |
| `getting-started/connect-to-local-mcp-servers/troubleshooting.md` | DONE (2025-11-04) | Log locations, manual server run, APPDATA env tips. |
| `getting-started/connect-to-local-mcp-servers/next-steps.md` | DONE (2025-11-04) | Suggests exploring other servers, remote setups, deeper learning. |
| `getting-started/connect-to-remote-mcp-servers/index.md` | DONE (2025-11-04) | Intro to remote connectors for Claude/other clients. |
| `getting-started/connect-to-remote-mcp-servers/understanding-remote-mcp-servers.md` | DONE (2025-11-04) | Explains benefits of hosted servers (availability, service integration). |
| `getting-started/connect-to-remote-mcp-servers/what-are-custom-connectors.md` | DONE (2025-11-04) | Defines Claude custom connectors for remote MCP. |
| `getting-started/connect-to-remote-mcp-servers/connecting-to-a-remote-mcp-server.md` | DONE (2025-11-04) | Step-by-step for adding connectors and authenticating. |
| `getting-started/connect-to-remote-mcp-servers/best-practices-for-using-remote-mcp-servers.md` | DONE (2025-11-04) | Security tips and connector management guidance. |
| `getting-started/connect-to-remote-mcp-servers/next-steps.md` | DONE (2025-11-04) | Next actions: build servers, explore gallery, connect local, read architecture. |
| `getting-started/example-clients/index.md` | DONE (2025-11-04) | Lists MCP-capable applications. |
| `getting-started/example-clients/feature-support-matrix.md` | DONE (2025-11-04) | Comprehensive table of client capability support (resources/prompts/tools/etc.). |
| `getting-started/example-clients/client-details.md` | DONE (2025-11-04) | Per-client descriptions and key features; includes links. |
| `getting-started/example-clients/adding-mcp-support-to-your-application.md` | DONE (2025-11-04) | Encourages submissions; links to SDK docs. |
| `getting-started/example-clients/updates-and-corrections.md` | DONE (2025-11-04) | Notes community-maintained list and how to report changes. |
| `getting-started/example-servers/index.md` | DONE (2025-11-04) | Overview of server gallery. |
| `getting-started/example-servers/reference-implementations.md` | DONE (2025-11-04) | Lists current + archived reference servers with descriptions. |
| `getting-started/example-servers/official-integrations.md` | DONE (2025-11-04) | Points to official integrator list in repo. |
| `getting-started/example-servers/community-implementations.md` | DONE (2025-11-04) | Links to community server section. |
| `getting-started/example-servers/getting-started.md` | DONE (2025-11-04) | Quick commands to run TypeScript/Python reference servers. |
| `getting-started/mcp-inspector/index.md` | DONE (2025-11-04) | Intro to MCP Inspector tool. |
| `getting-started/mcp-inspector/getting-started.md` | DONE (2025-11-04) | Shows `npx` invocation patterns for npm/pypi/local servers. |
| `getting-started/mcp-inspector/feature-overview.md` | DONE (2025-11-04) | Walkthrough of tabs (resources/prompts/tools/logs). |
| `getting-started/mcp-inspector/best-practices.md` | DONE (2025-11-04) | Suggested iterative testing workflow + edge cases. |
| `getting-started/mcp-inspector/next-steps.md` | DONE (2025-11-04) | Links to repo + debugging guide. |
| `getting-started/sdks/index.md` | DONE (2025-11-04) | Intro to official SDK catalog. |
| `getting-started/sdks/available-sdks.md` | DONE (2025-11-04) | Lists 10 language SDK repos. |
| `getting-started/sdks/getting-started.md` | DONE (2025-11-04) | Notes parity across SDKs; encourages language-specific docs. |
| `getting-started/sdks/next-steps.md` | DONE (2025-11-04) | CTA to build server/client tutorials. |
| `getting-started/using-uvx/index.md` | DONE (2025-11-04) | Minimal example command `uvx mcp-server-git`. |
| `getting-started/using-pip/index.md` | DONE (2025-11-04) | Shows pip install/run and sample Claude config JSON. |
| `getting-started/using-pip/additional-resources.md` | DONE (2025-11-04) | Links to MCP server resources + discussions. |
| `capabilities/capabilities-overview/index.md` | DONE (2025-11-04) | Summarizes prompt/resource/tool hierarchy and control. |
| `capabilities/completion/index.md` | DONE (2025-11-04) | Introduces completion capability for argument autocomplete. |
| `capabilities/completion/user-interaction-model.md` | DONE (2025-11-04) | Notes IDE-like dropdowns but UI flexible. |
| `capabilities/completion/capabilities.md` | DONE (2025-11-04) | Servers must advertise `completions`. |
| `capabilities/completion/message-flow.md` | DONE (2025-11-04) | Shows request/response loop as user types. |
| `capabilities/completion/protocol-messages.md` | DONE (2025-11-04) | Defines `completion/complete` params and response structure (max 100, context args). |
| `capabilities/completion/data-types.md` | DONE (2025-11-04) | Documents `CompleteRequest`/`CompleteResult` fields. |
| `capabilities/completion/error-handling.md` | DONE (2025-11-04) | Specifies JSON-RPC codes for capability errors. |
| `capabilities/completion/implementation-considerations.md` | DONE (2025-11-04) | Recommends relevance sorting, fuzzy match, client debounce/cache. |
| `capabilities/completion/security.md` | DONE (2025-11-04) | Requires validation, rate limiting, guarding sensitive suggestions. |
| `capabilities/logging/index.md` | DONE (2025-11-04) | Describes structured log notifications and level control. |
| `capabilities/logging/user-interaction-model.md` | DONE (2025-11-04) | UI pattern unspecified. |
| `capabilities/logging/capabilities.md` | DONE (2025-11-04) | Servers advertise `logging`. |
| `capabilities/logging/log-levels.md` | DONE (2025-11-04) | Uses RFC 5424 severity table. |
| `capabilities/logging/message-flow.md` | DONE (2025-11-04) | Sequence for setLevel and notifications. |
| `capabilities/logging/protocol-messages.md` | DONE (2025-11-04) | Defines `logging/setLevel` request and `notifications/message` payload. |
| `capabilities/logging/error-handling.md` | DONE (2025-11-04) | Error codes for invalid levels/config. |
| `capabilities/logging/implementation-considerations.md` | DONE (2025-11-04) | Suggests rate limiting, context, UI filtering. |
| `capabilities/logging/security.md` | DONE (2025-11-04) | Prohibits secrets in logs; stresses validation/access control. |
| `capabilities/pagination/index.md` | DONE (2025-11-04) | Describes cursor-based pagination utility. |
| `capabilities/pagination/pagination-model.md` | DONE (2025-11-04) | Explain opaque cursor + server-chosen page size. |
| `capabilities/pagination/response-format.md` | DONE (2025-11-04) | Shows `nextCursor` in response. |
| `capabilities/pagination/request-format.md` | DONE (2025-11-04) | Request example using cursor param. |
| `capabilities/pagination/pagination-flow.md` | DONE (2025-11-04) | Sequence diagram for repeated fetch. |
| `capabilities/pagination/operations-supporting-pagination.md` | DONE (2025-11-04) | Lists list endpoints supporting pagination. |
| `capabilities/pagination/implementation-guidelines.md` | DONE (2025-11-04) | Guidelines for stable cursors, treating tokens as opaque. |
| `capabilities/pagination/error-handling.md` | DONE (2025-11-04) | Invalid cursor → -32602. |
| `capabilities/prompts/index.md` | DONE (2025-11-04) | Defines prompt templates exposure. |
| `capabilities/prompts/user-interaction-model.md` | DONE (2025-11-04) | Prompts are user-controlled; slash command example. |
| `capabilities/prompts/capabilities.md` | DONE (2025-11-04) | Servers declare `prompts` capability + `listChanged`. |
| `capabilities/prompts/protocol-messages.md` | DONE (2025-11-04) | Specifies `prompts/list`, `prompts/get`, `list_changed`. |
| `capabilities/prompts/message-flow.md` | DONE (2025-11-04) | Sequence for discovery, usage, notifications. |
| `capabilities/prompts/data-types.md` | DONE (2025-11-04) | Enumerates prompt definitions, message content types (text/image/audio/resource). |
| `capabilities/prompts/error-handling.md` | DONE (2025-11-04) | Standard JSON-RPC errors for invalid prompts. |
| `capabilities/prompts/implementation-considerations.md` | DONE (2025-11-04) | Highlights argument validation + pagination. |
| `capabilities/prompts/security.md` | DONE (2025-11-04) | Require validation to prevent injection. |
| `capabilities/resources/index.md` | DONE (2025-11-04) | Describes resources as unique URI context data. |
| `capabilities/resources/user-interaction-model.md` | DONE (2025-11-04) | Resources are application-managed; UI examples. |
| `capabilities/resources/capabilities.md` | DONE (2025-11-04) | Capability options `subscribe`/`listChanged`. |
| `capabilities/resources/protocol-messages.md` | DONE (2025-11-04) | Defines list/read/templates/subscribe flows. |
| `capabilities/resources/message-flow.md` | DONE (2025-11-04) | Sequence covering discovery, read, subscriptions. |
| `capabilities/resources/data-types.md` | DONE (2025-11-04) | Details resource metadata, text/blob payloads, annotations. |
| `capabilities/resources/common-uri-schemes.md` | DONE (2025-11-04) | Guidance for https/file/git/custom schemes. |
| `capabilities/resources/error-handling.md` | DONE (2025-11-04) | Error codes (-32002 etc.) for resource failures. |
| `capabilities/resources/security-considerations.md` | DONE (2025-11-04) | Stresses URI validation, access controls, encoding. |
| `capabilities/tools/index.md` | DONE (2025-11-04) | Introduces tool invocation mechanism. |
| `capabilities/tools/user-interaction-model.md` | DONE (2025-11-04) | Tools are model-controlled; recommend human approval. |
| `capabilities/tools/capabilities.md` | DONE (2025-11-04) | Servers declare `tools` with optional `listChanged`. |
| `capabilities/tools/protocol-messages.md` | DONE (2025-11-04) | Defines list/call/list_changed flows. |
| `capabilities/tools/message-flow.md` | DONE (2025-11-04) | Diagram showing LLM-driven invocation cycle. |
| `capabilities/tools/data-types.md` | DONE (2025-11-04) | Describes tool metadata, content types, structuredContent, output schema. |
| `capabilities/tools/error-handling.md` | DONE (2025-11-04) | Differentiates protocol errors vs `isError` results. |
| `capabilities/tools/security-considerations.md` | DONE (2025-11-04) | Input validation, access control, user confirmations. |
| `capabilities/roots/index.md` | DONE (2025-11-04) | Describes client-advertised filesystem roots. |
| `capabilities/roots/user-interaction-model.md` | DONE (2025-11-04) | Roots typically managed via workspace pickers. |
| `capabilities/roots/capabilities.md` | DONE (2025-11-04) | Clients declare `roots` + `listChanged`. |
| `capabilities/roots/protocol-messages.md` | DONE (2025-11-04) | Defines `roots/list` and `notifications/roots/list_changed`. |
| `capabilities/roots/message-flow.md` | DONE (2025-11-04) | Sequence for discovery and updates. |
| `capabilities/roots/data-types.md` | DONE (2025-11-04) | Root objects (file:// URI + name). |
| `capabilities/roots/implementation-guidelines.md` | DONE (2025-11-04) | Client consent UI guidance; server caching/respect boundaries. |
| `capabilities/roots/error-handling.md` | DONE (2025-11-04) | Error codes (-32601, -32603) for unsupported roots. |
| `capabilities/roots/security-considerations.md` | DONE (2025-11-04) | Emphasizes path validation, permissions, root boundary enforcement. |
| `capabilities/elicitation/index.md` | DONE (2025-11-04) | New client capability for structured user input. |
| `capabilities/elicitation/user-interaction-model.md` | DONE (2025-11-04) | Warns against sensitive data; require clear UI. |
| `capabilities/elicitation/capabilities.md` | DONE (2025-11-04) | Clients advertise `elicitation`. |
| `capabilities/elicitation/message-flow.md` | DONE (2025-11-04) | Sequence of request → UI → response. |
| `capabilities/elicitation/protocol-messages.md` | DONE (2025-11-04) | Defines `elicitation/create` and possible responses. |
| `capabilities/elicitation/request-schema.md` | DONE (2025-11-04) | Describes allowed flat JSON schema (primitive types). |
| `capabilities/elicitation/response-actions.md` | DONE (2025-11-04) | Explains `accept` vs `decline` vs `cancel`. |
| `capabilities/elicitation/security-considerations.md` | DONE (2025-11-04) | Ban sensitive requests, require approval, validation, rate limits. |
