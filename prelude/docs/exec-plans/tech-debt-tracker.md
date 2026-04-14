# Tech Debt Tracker

Central backlog for small, continuous debt repayment.

| ID | Area | Debt | Impact | Next Action | Owner | Status | Updated |
|---|---|---|---|---|---|---|---|
| TD-001 | Agent grounding | Prompt lacks hard refusal/citation policy for low-confidence retrieval | Medium | Add strict grounding policy + tests in `prelude/tests` | TBD | Open | 2026-04-12 |
| TD-002 | Retrieval UX | `Score` label may be interpreted as similarity while value is distance | Medium | Rename display field or convert to similarity with formula docs | TBD | Open | 2026-04-12 |
| TD-003 | Tool protocol | `tool_result` is truncated at 2000 chars, evidence may be lost | Medium | Introduce chunked/structured tool-result strategy + tests | TBD | Open | 2026-04-12 |
| TD-004 | RAG index quality | Legacy index may still contain relative `source_url` records | Low | Rebuild index and add post-build URL quality check script/test | TBD | Open | 2026-04-12 |
| TD-005 | CI hard gate | No repository CI workflow enforcing `prelude` verification | Medium | Add GitHub Action for `make verify` (prelude scope) | TBD | Open | 2026-04-12 |

## Operating Rules

- Update `Updated` on every status change.
- Close items only when validated by command/test output.
- Keep items small; split large debt into multiple IDs.
