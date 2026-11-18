# Tasks: issue-1096-spike-devloop-evaluate-claude-code-code

All tasks are documentation and fixture data only. No runtime code, settings,
`.claude/` configuration, SDK/CLI bump or Code Mode execution.

- [ ] 1. Re-fetch https://code.claude.com/docs/en/code-mode and pin fetch date, and record mctl-agents commit, `claude-agent-sdk` pin and bundled CLI version (`_cli_version.py`) — DoD: a "Sources and pins" section in `docs/spikes/1096-claude-code-code-mode.md` with URL+date, commit SHA, `0.2.174` / `2.1.310`; unfetched sources (release note, news) marked UNKNOWN.
- [ ] 2. Write the compatibility matrix across the six surfaces (depends on 1) — DoD: the table from design.md section 1 in the report, every cell sourced (doc URL or file path) or marked UNKNOWN; explicit statement that Code Mode is not applicable to headless DevLoop.
- [ ] 3. Write the no-duplicate/ownership map — DoD: section linking #597 (benchmark owner), #63 (PARK, M8 FAIL, not reopened), #242/#517 (first-turn is not E2E, citing `docs/benchmarks/capability-discovery.md`), #181/#151 (reuse ADR 014/022 controls), #35/#165, #343.
- [ ] 4. Write the threat model and per-child governance requirements (depends on 2) — DoD: table from design.md section 2 with each risk mapped to a concrete file/ADR (`orchestrator/options.py` hooks, `policy_checkpoint.py`, `capability_gateway.py`, `execution_identity.py`, `redaction.py`) or labelled GAP; unknowns fail closed.
- [ ] 5. Write `docs/spikes/1096/protocol.md` (depends on 4) — DoD: arms, pins, tasks A/B/C with oracles, 5 reps x 3 tasks x 2 modes, randomization, metric definitions (initial vs total tokens, p50/p95, REPL overhead, denials, correlation completeness), vendor-claim column kept separate.
- [ ] 6. Write `docs/spikes/1096/negative-matrix.md` and `results-template.csv` (depends on 5) — DoD: N1-N10 and all 30 result rows present, every measured cell `NOT_RUN`.
- [ ] 7. Write `docs/spikes/1096/fixtures/README.md` manifest — DoD: lists synthetic repo snapshot SHA, sanitized CI-log bundle and two recorded fixture MCP response sets with sha256; no live user data, no production GitHub objects.
- [ ] 8. Write the recommendation memo (depends on 2-7) — DoD: exactly one outcome (`FURTHER_RESEARCH`), with gate, owner, expected cost, evidence and permission review stated; runtime transfer `REJECT` absent official SDK support; cross-links to #597, #181/#151.

## Tests

- [ ] T1. `grep -rn "PASS" docs/spikes/1096*` shows no measured cell marked PASS; all unexecuted cells read `NOT_RUN` or `UNKNOWN`.
- [ ] T2. `git diff --stat` touches only `docs/spikes/1096-claude-code-code-mode.md` and `docs/spikes/1096/**`.
- [ ] T3. Existing doc checks pass (`uv run pytest tests/` unaffected; `tools/check_diagrams.py` if the report adds a diagram).
- [ ] T4. A reviewer can trace every matrix cell to a URL+date or file path at the pinned commit.
- [ ] T5. No fixture contains a credential-shaped value (`orchestrator.redaction.contains_credential` over each fixture file returns False).

## Rollback

Revert the documentation commit. Nothing is deployed, configured or executed, so there is no runtime state to undo.
