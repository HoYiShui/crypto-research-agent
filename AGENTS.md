## Principles

1. The repository is the only system of record: knowledge not in the repo does not exist for agents. Discussions, mental decisions, and external documents - if they affect development, they must be captured as versioned artifacts in the repo.
2. This file is a map, not an encyclopedia: keep it around ~100 lines and point to deeper docs in `docs/`. Each layer should expose only local information plus navigation to the next step.
3. Encode taste as rules: prefer linter checks, structural tests, and CI gates as hard constraints rather than natural-language instructions. Mechanically verifiable > prose guidelines.
4. Plans are first-class artifacts: execution plans should include progress logs, be versioned, and be centralized under each active layer's `docs/exec-plans/` (for current implementation: `prelude/docs/exec-plans/`).
5. Continuous garbage collection: repay technical debt in small, continuous increments instead of saving it for a large cleanup. Gap tracking is in each layer's `docs/exec-plans/tech-debt-tracker.md` (for current implementation: `prelude/docs/exec-plans/tech-debt-tracker.md`).
6. When stuck, fix the environment, not effort: when an agent struggles, ask "What context, tooling, or constraints are missing?" and then add them to the repo.
