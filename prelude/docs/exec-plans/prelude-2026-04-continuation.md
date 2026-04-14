# Prelude Continuation Plan (2026-04)

## Objective

Stabilize grounding quality and retrieval reliability in `prelude/` while keeping current TUI + minimal-agent flow intact.

## Scope

- `prelude/app/agent/*`
- `prelude/rag/*`
- `prelude/scripts/build_index.py`
- `prelude/tests/*`

## Checklist

- [ ] Grounding constraints in system prompt are explicit and testable.
- [ ] Retrieval output semantics are unambiguous (`distance` vs `similarity`).
- [ ] Tool-result truncation strategy is adjusted to reduce evidence loss.
- [ ] Source URL quality is validated on rebuilt index artifacts.
- [ ] Regression tests cover the above behaviors.
- [ ] `make verify` passes.

## Progress Log

- 2026-04-12: Created plan skeleton and aligned `prelude/AGENTS.md` with six principles.
- 2026-04-12: Added `prelude/Makefile` verify gates (`pytest` + TUI build).

## Exit Criteria

- All checklist items are completed.
- Relevant tests are green in local verification.
- Remaining gaps are listed in `tech-debt-tracker.md` with next actions.
