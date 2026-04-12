# Prelude AGENTS Map

Scope: this file governs the `prelude/` layer only.

## 0) Navigation (map, not encyclopedia)

- Runtime entrypoints:
  - `prelude/main.py` (CLI mode)
  - `prelude/tui/src/index.ts` (TUI)
  - `prelude/app/bridge/pi_bridge.py` (TUI bridge)
- Agent core:
  - `prelude/app/agent/agent_loop.py`
  - `prelude/app/agent/tools.py`
  - `prelude/app/agent/system_prompt.py`
- RAG pipeline:
  - `prelude/scripts/build_index.py`
  - `prelude/rag/parsers/html_to_markdown.py`
  - `prelude/rag/chunkers/semantic_chunker.py`
  - `prelude/rag/embedders/embedding_pipeline.py`
- Project docs:
  - `prelude/docs/rag/rag_workflow.md`
  - `prelude/docs/research/rag-pipeline-incident-log.md`
  - `prelude/docs/todo/2026-04-06-rag-grounding-findings.md`
  - `prelude/docs/exec-plans/` (plans, logs, debt tracking)

## 1) Repo is the only system of record

- Any development-impacting decision must land in repo artifacts in the same task:
  - behavior/spec changes -> code + tests
  - incident/bug discovery -> `prelude/docs/research/*` or `prelude/docs/todo/*`
  - execution intent/progress -> `prelude/docs/exec-plans/*`
- Do not leave decisions only in chat.

## 2) Keep this file as a map

- Keep `prelude/AGENTS.md` around ~100 lines.
- Add only local rules + file pointers.
- Deep explanations go to `prelude/docs/`, not here.

## 3) Encode taste as mechanical rules

Use these checks as merge gates for `prelude/` work:

```bash
cd prelude
make verify
```

Current enforced checks:
- `uv run pytest -q`
- `pnpm --dir tui build`

Rule: no behavior change without at least one test proving it, unless explicitly marked as temporary and logged in `prelude/docs/exec-plans/tech-debt-tracker.md`.

## 4) Plans are first-class artifacts

- Store plans under `prelude/docs/exec-plans/`.
- Every active plan must include:
  - objective
  - checklist
  - progress log with dates
  - exit criteria
- Prelude continuation plan entrypoint:
  - `prelude/docs/exec-plans/prelude-2026-04-continuation.md`

## 5) Continuous garbage collection

- Track debt in `prelude/docs/exec-plans/tech-debt-tracker.md`.
- Each prelude change should either:
  - repay one debt item, or
  - add/update one debt record with owner/next action.

## 6) Fix environment before spending more effort

When blocked, first add missing context/tools/constraints to repo:
- reproducible command
- failing symptom
- root cause hypothesis
- permanent mitigation (script/config/test/doc)

Incident baseline:
- `prelude/docs/research/rag-pipeline-incident-log.md`

If a failure is recurrent and undocumented, stop feature work and document/automate the fix path first.
