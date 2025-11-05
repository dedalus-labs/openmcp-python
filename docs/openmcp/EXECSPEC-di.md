# Dependency Injection & Tool Allow-Lists – Execution Spec

**Owner:** Codex  
**Last updated:** 2025-11-04

## Objective
Deliver a FastAPI-inspired dependency injection (DI) system for OpenMCP so
server authors can gate capabilities with `Depends` predicates, share
request-scoped state, and express business rules (e.g. plan tiers, feature
flags) without manual wiring.

## Desired UX

```python
from openmcp import MCPServer, Depends, tool

server = MCPServer("pro-demo")

def get_current_account() -> Account:
    ...

def require_pro(account: Account) -> bool:
    return account.tier == "pro"

@tool(enabled=Depends(require_pro, get_current_account))
async def premium_forecast(...):
    ...
```

- `Depends(callable, *subdeps)` matches FastAPI semantics; lambdas allowed but
  named callables recommended.
- Dependencies resolve once per MCP request (`tools/list`, tool call, etc.)
  and are cached for reuse inside that request.
- Tools without dependencies continue to be always available.
- If a dependency raises or returns falsy, the tool is hidden from `tools/list`
  responses for that request.

## Scope & Non-Goals

- **In scope:** Tools (`enabled=`).  Framework should extend to resources &
  prompts later with minimal changes.
- **Out of scope (v1):**
  - Global dependency overrides (FastAPI’s `app.dependency_overrides`).
  - Yield dependencies / teardown callbacks.
  - Security scopes.

## Architecture Overview

| Concern | OpenMCP touchpoints | FastAPI reference |
|---------|---------------------|-------------------|
| Spec storage | `src/openmcp/tool.py` (`ToolSpec.enabled`) | `fastapi/param_functions.py` |
| Allow-list evaluation | `src/openmcp/server/services/tools.py::_refresh_tools` | N/A (custom) |
| Request context | `src/openmcp/context.py`, `get_context()` | `fastapi/dependencies/utils.py` (request state) |
| Dependency resolver | **New** `src/openmcp/server/dependencies.py` + `models.py` | `fastapi/dependencies/utils.py`, `models.py` |
| Public API | expose `Depends` via `openmcp.__init__` | `fastapi/__init__.py` |
| Example | `examples/tools/allow_list.py` | FastAPI docs + FastMCP context examples |

We’ll port the minimal subset of FastAPI’s dependency machinery:

1. `Depends` descriptor & metadata models (callable references, cache flags).
2. Dependency graph resolver (`solve_dependencies` analogue) that respects
   async/sync callables and caches results per request.
3. Context integration via `ContextManager` to hold per-request cache.

## Implementation Tasks

### 1. Clean up provisional DI helper
- Remove `src/openmcp/utils/deps.py` (barebones contextvar helper) or refactor
  into the new system once scaffolding exists.

### 2. Dependency primitives
- Create `src/openmcp/server/dependencies/models.py` with dataclasses:
  - `DependencyParameter` (callable, use_cache, sub-dependencies).
  - `ResolvedDependency` (value, any cleanup hook placeholder).
- Implement `Depends` in `src/openmcp/server/dependencies/__init__.py` and
  re-export from `openmcp/__init__.py`.

### 3. Resolver (`dependencies/solver.py`)
- Adapt FastAPI’s `solve_dependencies` to OpenMCP:
  - Input: dependency graph, context (optional).
  - Build graph recursively; detect duplicates.
  - Execute callables (await if coroutine).  Cache per-request using context’s
    dependency cache dictionary (add to `Context` model).
  - Support repeated dependencies and nested `Depends`.

### 4. Integrate with tools
- Update `tool()` decorator (`src/openmcp/tool.py`) to accept `Depends`.
- During `ToolsService._refresh_tools()` evaluation, detect `Depends` and
  resolve via new solver.  If result truthy → attach tool; else skip.
- Ensure errors in dependency evaluation prevent the tool from being exposed
  (log warning).

### 5. Provide built-in dependencies
- Wrap existing helpers so they can be used in dependency chains:
  - `get_context()` (existing) adapts seamlessly.
  - Later: `get_request()`, `get_access_token()` etc. (non-blocking for v1).

### 6. Testing
- Create `tests/server/test_dependencies.py`:
  1. **Basic injection** – dependency returns value passed to tool.
  2. **Duplicate caching** – dependency invoked once despite multiple uses.
  3. **Context propagation** – dependency can access current context (`get_context()`).
  4. **Allow-list gating** – `enabled=Depends(require_pro)` hides tool when
     dependency false.
- Reference FastAPI tests for expected behaviour:
  - `fastapi/tests/test_dependency_paramless.py`
  - `fastapi/tests/test_dependency_duplicates.py`
  - `fastapi/tests/test_dependency_contextvars.py`
  - `fastapi/tests/test_dependency_cache.py`

### 7. Examples & docs
- Rewrite `examples/tools/allow_list.py` to depend on new DI system
  (per-request dependency scope via CLI `--user` flag).
- Update docs (`docs/openmcp/tools.md`, cookbook) with DI guidance.

## Risks & Mitigations

- **Pre-request evaluation**: Tool registration happens outside requests.
  -> Guard resolver to run in a temporary scope or defer to runtime request.
- **Async/sync mishandling**: ensure resolver branches on `iscoroutinefunction`.
- **State leakage**: use contextvars to isolate per request caches.
- **Complexity creep**: keep implementation minimal; skip overrides/yield for v1.

## Deliverables

✅ New dependency module (`Depends`, resolver, models).

✅ Tools integration & runtime allow-list gating.

✅ Updated allow-list example + docs (tools.md, cookbook.md).

✅ Dependency-focused test suite passing under `uv run pytest` (`tests/server/test_dependencies.py`).
