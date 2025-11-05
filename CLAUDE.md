# CLAUDE.md - OpenMCP coding guidelines

This repository implements the Model Context Protocol (MCP) in the smallest,
spec-faithful form we can devise.  Follow these conventions when touching the
codebase.

## Core philosophy

1. **Read the spec first.** Every feature funnels back to the canonical
   documentation under `docs/mcp/spec`.  When unsure, start by re-reading:
   - Base lifecycle: `docs/mcp/core/lifecycle/lifecycle-phases.md`
   - Tool capability: `docs/mcp/spec/schema-reference/tools-call.md`
   - Streamable HTTP transport: reference SDK under
     `references/python-sdk/src/mcp/server/streamable_http*.py`

2. **Smallest bytes, sharp edges.** We prioritize the minimal surface that gives
   end users the full protocol.  Avoid abstractions until the spec forces them.
   - No blanket helpers that obscure JSON-RPC semantics.
   - Keep decorators thin; let `mcp.types` enforce schema shape.

3. **Receipt-based development.** Every public API or behavior should name the
   spec clause that motivated it.  Use docstrings or comments that reference the
   path in `docs/mcp/spec`.  Examples: “see `tools/list` description in
   `docs/mcp/spec/schema-reference/tools-list.md`”.

4. **One thing per module.** Aim for single-responsibility files (e.g. the
   server wrapper, the tool decorator, logging utilities).  This matches the
   UNIX ethos of small, composable units.

5. **Configurable transports, zero surprises.** Support only the official
   transports described in the spec (STDIO, Streamable HTTP).  Default to
   Streamable HTTP because it is the more general case, but allow explicit
   overrides so authors own the ergonomics.

6. **Dependency discipline.** Every new dependency must justify its byte cost.
   Right now we rely on:
   - The reference MCP SDK (`references/python-sdk`) for wire-level fidelity.
   - `pydantic` TypeAdapter for JSON Schema derivation (see the spec’s schema
     section).
   - Optional extras (e.g., `rich`, `orjson`) remain outside the core and are documented for integrators who need them.
   Resist additional dependencies unless the spec mandates them.

7. **Tests as spec receipts.** Each pytest should focus on a discrete protocol
   guarantee—registration, allow-lists, schema inference, serve dispatch.  Keep
   coverage high with minimal fixtures.

8. **Documentation as a map back to the spec.** README and quickstarts must
   reference the exact spec snippets they implement.  Example: note that tool
   discovery maps to `docs/mcp/spec/schema-reference/tools-list.md`.

## Workflow notes

- Treat `references/python-sdk` as the source of truth for transports and
  JSON-RPC message types.  We patch behavior only when we have a spec section to
  justify the divergence.
- Prefer ambient registration (contextvars/AsyncLocalStorage) rather than
  instance decorators.  This keeps the authoring experience consistent with the
  spec’s tooling examples.
- Keep `test.py` as a canonical “one-liner” demo.  Anything bulkier belongs in
  the docs.

## Future work (guardrails)

- [x] Wire up **completion** capability end-to-end (ambient registration, capability
  advert, handler) per `docs/mcp/capabilities/completion/*.md` and the message
  contract in `docs/mcp/spec/schema-reference/completion-complete.md`.
- [x] Finish the **prompts** primitive (list/get + ambient authoring) per
  `docs/mcp/capabilities/prompts` and
  `docs/mcp/spec/schema-reference/prompts-*.md`; add receipt docstrings.
- [x] Extend tests with binary/resource subscription cases described in
  `docs/mcp/spec/schema-reference/resources-read.md` and
  `resources-subscribe.md`.
- [x] Document capability receipts in README + module docstrings once the above
  land; cite the relevant spec paths explicitly.

- Pydantic TypeAdapter drives JSON Schema today; ensure it matches any schema
  changes in `docs/mcp/spec/schema-reference`.
- Plugin discovery (`importlib.metadata.entry_points`) must remain optional and
  spec-cited when implemented.
- TypeScript/Go ports should mirror the same receipts and minimalism.

Stay disciplined: small files, clear spec links, zero unnecessary bytes.
