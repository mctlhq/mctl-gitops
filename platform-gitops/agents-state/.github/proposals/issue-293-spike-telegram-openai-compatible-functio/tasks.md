# Tasks: issue-293-spike-telegram-openai-compatible-functio

- [ ] 1. Add `roadmap/spikes/telegram-openai-tool-loop.yaml`: `SpikeDefinition`, issue mctlhq/.github#293, `lifecycle: proposed`, outcomes `GO_HETZNER_DEV_NEBIUS_PROD`/`GO_NEBIUS_ONLY`/`NEEDS_SCHEMA_ADAPTER`/`NOT_A_FIT`, `timebox.decisionBy: "2026-11-10"`, `execution.devloop: true`, `evidence.report: docs/spikes/telegram-openai-tool-loop.md`, no `decision`, and a header comment that the owner records the verdict — DoD: `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes.
- [ ] 2. Write the report skeleton `docs/spikes/telegram-openai-tool-loop.md`: header with proposed verdict, non-claims, evidence tags and pins; S1 to S4 tables; full-run table; cost ledger; decision rule; per-model verdicts; follow-ups; re-open triggers. Every unmeasured cell says "not run" or "unknown (not observed)" — DoD: all tables from the issue are present with the agreed columns.
- [ ] 3. (depends on 2) Smoke S1: in mctl-telegram at a pinned commit, marshal each of the 11 `mcplib.Tool.InputSchema` values from `buildToolSet` and check them as OpenAI `tools[].function.parameters`, then send one request per provider with all 11 tools — DoD: S1 table filled; any rejected keyword is named.
- [ ] 4. (depends on 3) Smoke S3: confirm `cf-aig-collect-log: false` and `cf-aig-skip-cache: true` on `custom-hetzner` and `custom-nebius` (gateway log total stays 0, no cache hits) BEFORE any fixture with conversation content — DoD: S3 table filled; if not honoured, stop and record it.
- [ ] 5. (depends on 4) Smoke S2: 5 fixtures x 3 models with `tool_choice: auto`, Hetzner at `AGENT_OPENAI_MIN_INTERVAL=6s` — DoD: S2 table filled with no message bodies.
- [ ] 6. Smoke S4: read the mctl-telegram `audit_logs` migration and FK, and decide between a NULL `user_id` and auditing under the job's user — DoD: answer and recommendation recorded with a `[CODE]` pin.
- [ ] 7. (depends on 5, and on the mctl-telegram slice-3 runner interface) Full C1 run per model (`AGENT_C1_EVAL_PROMPT=catalog`): HarnessVersion, suite digest, n/32, leaks, binding violations, wrong auto-sends, p50/p95, cost per fixture from `usage` and the price table, and 429 count; Nebius stops at USD 5 — DoD: full-run table filled, or marked "not run" with the reason if slice 3 is missing at the timebox.
- [ ] 8. (depends on 3-7) Apply the decision rule: one-line verdict per model and one proposed outcome (marked provisional if task 7 did not run) — DoD: the report header and the verdict section agree.
- [ ] 9. Add the report to `# Spikes` in `AGENTS.md` — DoD: one-line entry naming #293 and the proposed verdict.
- [ ] 10. Open a PR that refs (does not close) #293 — DoD: PR open; the owner then records `decision` and sets `lifecycle: decided` with follow-ups.

## Tests
- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes, and `pytest roadmap/tests/test_validate_spike.py` stays green.
- [ ] T2. Negative check: adding a `decision` while `lifecycle: proposed` fails validation (the schema's `else: not required decision`).
- [ ] T3. Grep the report and the PR diff for secret-shaped strings (`sk-`, `Bearer `, Vault values) and for message bodies. None may be present.
- [ ] T4. Recompute every cost from the recorded `usage` tokens and the 1.40 / 4.40 USD per MTok price table. The Nebius total is <= USD 5.
- [ ] T5. Confirm that no file under mctl-gitops `platform-gitops/services/` changed during the spike (diff the pinned commit range).

## Rollback
Revert the PR. It adds only `roadmap/spikes/telegram-openai-tool-loop.yaml`, `docs/spikes/telegram-openai-tool-loop.md` and one `AGENTS.md` line, and changes no runtime or gitops state. If a run misbehaves (gateway logging found on, a 429 storm, or spend near the cap), stop the runner and revoke or rotate the affected Vault key if exposure is suspected. Nothing deployed needs reverting.
