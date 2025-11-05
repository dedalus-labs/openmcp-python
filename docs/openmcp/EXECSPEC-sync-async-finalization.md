# EXECSPEC: Sync/Async Finalization & TOML Validation

**Status**: In Progress
**Date**: 2025-06-18
**Priority**: P0 (Blocking quality gates)

## Context

Thread completion requiring:
1. Validation that `maybe_await_with_args` is correctly integrated across all services
2. Resolution of pyproject.toml schema violations (lines 133, 171, 176, 212, 286, 293, 313, 321, 329)
3. Test coverage for sync/async tool execution patterns
4. Documentation of sync/async support

## Architecture Decision

The codebase already uses `maybe_await_with_args` from `utils/coro.py` to support both sync and async functions. This matches FastMCP's pattern but is already implemented. No new code needed—just validation, test coverage, and TOML fixes.

## Parallel Work Streams

### Stream A: Integration Verification [Agent: Explore]
**Owner**: Explore agent (thorough mode)
**Deliverables**:
- Validate all capability services use `maybe_await_with_args` correctly
- Check resource/prompt/tool/completion handlers
- Verify no direct `await spec.fn()` calls remain
- Report any gaps

**Files to check**:
- `src/openmcp/server/services/*.py`
- `src/openmcp/client/core.py`

**Exit criteria**: All user-facing callable handlers use `maybe_await_with_args`

---

### Stream B: TOML Schema Violations [Agent: General-purpose]
**Owner**: General-purpose agent
**Deliverables**:
- Fix pyproject.toml schema violations at lines:
  - 133, 171, 176: `exclude` and `dependency-constraints` in wrong sections
  - 212, 286, 293, 313, 321, 329: Invalid ruff lint configuration schemas
- Validate with VSCode TOML extension
- Ensure no regressions in uv/mypy/ruff/ty configurations

**Approach**:
1. Read pyproject.toml sections 130-180 (uv config)
2. Read ruff config sections (lines 200-330)
3. Identify schema violations per "Even Better TOML" errors
4. Apply fixes following uv/ruff official schema
5. Validate with `uv lock --dry-run` and ruff check

**Exit criteria**: Zero TOML schema errors in VSCode

---

### Stream C: Test Coverage [Agent: General-purpose]
**Owner**: General-purpose agent
**Deliverables**:
- Tests for sync tools (def tool_fn() -> str)
- Tests for async tools (async def tool_fn() -> str)
- Tests for mixed sync/async in same server
- Tests for sync/async prompts/resources
- Integration test: client calling sync and async tools

**Files to create/update**:
- `tests/test_tools_sync_async.py` (new)
- `tests/test_prompts_sync_async.py` (new)
- Update `tests/test_tools.py` with sync examples

**Exit criteria**: >90% coverage on sync/async code paths in `utils/coro.py`

---

### Stream D: Documentation [Agent: General-purpose]
**Owner**: General-purpose agent
**Deliverables**:
- Update `examples/tools/allow_list.py` with sync tool examples
- Add `examples/tools/mixed_sync_async.py` showing both patterns
- Document in cookbook: "Sync vs Async Tools"
- Update README with sync/async support statement

**Exit criteria**: Examples run cleanly with mypy and demonstrate both patterns

---

## Integration Point

All agents report back when complete. Final validation:
1. Run full test suite: `uv run pytest`
2. Run type checking: `uv run mypy src/`
3. Run linting: `uv run ruff check`
4. Validate TOML: Check VSCode errors panel
5. Build package: `uv build`

## Success Criteria

- [ ] Zero TOML schema violations
- [ ] All services use `maybe_await_with_args` correctly (verified)
- [ ] Tests pass for sync and async tools/prompts/resources
- [ ] Examples demonstrate both patterns
- [ ] Documentation covers sync/async support
- [ ] No type errors, lint errors, or test failures
