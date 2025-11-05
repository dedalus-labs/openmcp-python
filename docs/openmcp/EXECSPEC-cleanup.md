# Cleanup Execution Specification – Dynamic Capabilities Rollout

**Owner:** Codex  
**Last updated:** 2025-11-04  
**Context:** Track remaining polish items after the dynamic-capability + logging overhaul.

---

## Objective
Resolve the outstanding issues called out during the final review so that the dynamic-capability documentation, examples, and safeguards are airtight.

## Tasks

| # | Task | Details | Status |
|---|------|---------|--------|
| 1 | Verify new advanced examples start cleanly | Ensure `examples/advanced/feature_flag_server.py` and `examples/advanced/custom_logging.py` have executable entry points (`if __name__ == "__main__":`). Run `uv run …` to confirm. | DONE |
| 2 | Remove stray experimental directories | Delete `old-school-server/` and `pytorch/` unless they belong under `examples/` with docs. | DONE |
| 3 | Confirm dependency updates | Review `pyproject.toml` / `uv.lock` for newly added packages (e.g. logging dependencies). Regenerate lockfile if adjustments required. | DONE |
| 4 | Audit exports | Double-check `src/openmcp/utils/__init__.py` and `src/openmcp/server/__init__.py` only re-export supported symbols. | DONE |
| 5 | Run full test suite | `pytest` plus targeted integration tests to ensure dynamic mode warnings and notifications behave as expected. (Resolved by aligning notification method spelling; `uv run pytest` → 280 passed, coverage 89.21%.) | DONE |
| 6 | Document example in README | Mention new advanced examples in top-level README if not already called out. | DONE |

## Sign-off criteria
- Both advanced examples run via `uv run`.
- Workspace contains no ad-hoc experimental directories.
- Dependency manifests are intentional and consistent.
- `pytest` passes without regressions.
- Documentation references match the final example layout.

Upon completion, update this file with dates and initials, then submit alongside the main PR.  
