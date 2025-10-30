# OpenMCP Overview

OpenMCP is a thin, spec-faithful wrapper over the Model Context Protocol (MCP) reference SDK. It
adds light ergonomics—ambient registration, schema inference, simplified transports—while keeping the
wire behaviour identical to the MCP specification.

## Architectural Layers

```
┌────────────────────────────────────────────────────────────┐
│ Application code (tools, resources, prompts, examples)     │
├────────────────────────────────────────────────────────────┤
│ OpenMCP convenience layer                                  │
│  • MCPServer / MCPClient                                   │
│  • Capability services (tools/resources/prompts/…)         │
│  • Context helpers (logging/progress/authorization)        │
│  • Transport adapters (STDIO, Streamable HTTP)             │
├────────────────────────────────────────────────────────────┤
│ MCP reference SDK (mcp.server, mcp.client, mcp.types)      │
├────────────────────────────────────────────────────────────┤
│ Runtime (asyncio/anyio, Starlette/Uvicorn, OS transport)   │
└────────────────────────────────────────────────────────────┘
```

The reference SDK handles protocol lifecycle (initialize → initialized → normal operation) and JSON-RPC
plumbing. OpenMCP layers on:

- **Registration ergonomics** – decorators and `binding()` scopes to declare capabilities.
- **Schema handling** – `pydantic` powered inference plus normalization adapters.
- **Operational glue** – pagination helpers, heartbeat service, subscription bookkeeping.
- **Opt-in security hooks** – transport security defaults, authorization scaffolding.

## Lifecycle Snapshot

1. **Initialization**: `MCPClient` sends `initialize`, negotiating protocol version and capabilities.
2. **Operation**: Client issues `tools/list`, `resources/read`, etc.; server services dispatch to
   registered handlers, log/progress helpers use `get_context()`.
3. **Shutdown**: Transport closes (STDIO exit, HTTP connection close). The SDK cleans up session state.

All OpenMCP services respect the MCP spec receipts listed in `docs/mcp/core/` and `docs/mcp/capabilities/`.
When the framework offers optional behaviour (e.g., list-change notifications, subscriptions), the
configuration defaults mirror the spec’s SHOULD/SHOULD NOT guidance.

## Capabilities at a Glance

| Capability     | Implementation                                                | Key docs                        |
| -------------- | ------------------------------------------------------------- | ------------------------------- |
| Tools          | `src/openmcp/server/services/tools.py`                        | `docs/openmcp/manual/server.md` |
| Resources      | `src/openmcp/server/services/resources.py`                    | `docs/openmcp/manual/server.md` |
| Prompts        | `src/openmcp/server/services/prompts.py`                      | `docs/openmcp/manual/server.md` |
| Completions    | `src/openmcp/server/services/completions.py`                  | `docs/openmcp/manual/server.md` |
| Sampling       | `src/openmcp/server/services/sampling.py`                     | `docs/openmcp/manual/server.md` |
| Elicitation    | `src/openmcp/server/services/elicitation.py`                  | `docs/openmcp/manual/server.md` |
| Logging        | `src/openmcp/server/services/logging.py`, `get_context()`     | `docs/openmcp/manual/server.md` |
| Progress       | `src/openmcp/progress.py`, `get_context().progress()`         | `docs/openmcp/manual/server.md` |
| Authorization  | `src/openmcp/server/authorization.py` (opt-in scaffolding)    | `docs/openmcp/manual/security.md` |
| Transports     | `src/openmcp/server/transports/*`, `src/openmcp/client/transports.py` | `docs/openmcp/manual/server.md` |

The following sections dive into server behaviour, client behaviour, configuration, operational
security, and a gallery of end-to-end examples.
