# Server Capability Audit

This document tracks how OpenMCP’s server implementation maps onto the
behaviors described in
`docs/mcp/core/understanding-mcp-servers/core-server-features.md` and the
related spec receipts. Line references point to the primary implementation.

| Spec focus | Requirement | OpenMCP implementation | Notes |
| --- | --- | --- | --- |
| Tools (`tools/list`, `tools/call`) | Provide discoverable tool metadata and execute handlers with JSON‑schema input validation. | `src/openmcp/server/services/tools.py:11-200` builds schemas via `TypeAdapter`, manages allow-lists (`allow_tools`) and enabled predicates, attaches handlers, and normalizes results through `normalize_tool_result`. | Schema inference falls back to permissive objects when annotations are unsupported (documented in `docs/openmcp/tools.md`). |
| Tool gating & discovery UX | Allow applications to control visible tools and notify clients of list changes. | `tools.allow_tools`, `NotificationFlags.tools_changed`, `notify_list_changed()` (`src/openmcp/server/services/tools.py:110-143`). | No additional consent UI; defers to host application per MCP guidance. |
| Resources (`resources/list`, `resources/read`, templates, subscriptions) | Surface static resources, template URIs, and support subscription updates with MIME metadata. | `src/openmcp/server/services/resources.py:16-192` plus subscription manager. | Parameter-completion UX is intentionally left to host clients; server-side support documented in `docs/openmcp/resources.md`. |
| Prompts (`prompts/list`, `prompts/get`) | Register structured prompt templates with argument validation. | `src/openmcp/server/services/prompts.py:17-200` validates required arguments, normalizes content blocks, and emits list-changed notifications. | Prompt auto-completion of argument values is not implemented server-side (aligned with spec – clients provide UX). |
| Progress & logging | Offer spec-compliant progress stream and logging hooks accessible from handlers. | `src/openmcp/progress.py:1-419`, `src/openmcp/context.py:38-174`, documented in `docs/openmcp/context.md` and `docs/openmcp/progress.md`. | Progress helper enforces monotonicity, coalesces emissions, and integrates with request context. |
| Client notifications (`logging/setLevel`, `notifications/...`) | Provide built-in logging level handler and notification sink. | `src/openmcp/server/services/logging.py`, `src/openmcp/server/notifications.py`, registered in `MCPServer.__init__` (`src/openmcp/server/app.py:90-214`). | Default sink mirrors to Python logging and propagates notifications. |
| Sampling & elicitation proxies | Expose sampling and elicitation capability handlers required by richer clients. | `src/openmcp/server/app.py:200-334` wires `SamplingService` and `ElicitationService`. | behavior mirrors reference SDK; additional business logic can extend services. |
| Roots support | Ensure `roots/list`, `roots/read`, and guard utilities exist for safe file access. | `src/openmcp/server/services/roots.py`, `require_within_roots` decorator (`src/openmcp/server/app.py:467-522`). | Integrates with `client` roots capability via `MCPClient`. |
| Transport coverage | Provide STDIO and Streamable HTTP transports with DNS-rebinding protection defaults. | `src/openmcp/server/transports/base.py`, `stdio.py`, `streamable_http.py`; registry wiring in `src/openmcp/server/app.py:151-208`. | Security defaults documented in `docs/openmcp/transports.md`; custom transports can be plugged via `register_transport`. |
| Health monitoring | Track active sessions and expose ping helpers/heartbeat. | `src/openmcp/server/services/ping.py:19-215`, called from `MCPServer.start_ping_heartbeat`. | Ping service obeys PHI failure detector semantics; tests cover both asyncio and trio modes. |

### Identified gaps / follow-ups

* **Prompt/resource parameter suggestions** – the spec describes UI-driven completion. OpenMCP intentionally exposes raw templates and leaves completion to clients; no server changes required, but documentation clarifies this.
* **Advanced autoschema** – richer schema derivation (e.g., dataclasses, Pydantic models) is being tracked separately (see autoschema enhancement work).

