# Tasks: issue-343-spike-evaluate-cloudflare-kitesurf-as-a

- [ ] 1. Re-verify pins and dedup before writing.
  - Re-resolve `cloudflare/kitesurf` HEAD and record the SHA used. Re-read the README, blog and benchmarks at that SHA and date, and read the CDP coverage, WebMCP and dependency notices from the pinned tree if reachable, otherwise UNKNOWN.
  - Grep `roadmap/spikes/` for an existing binding of mctlhq/.github#343 or the name `cloudflare-kitesurf`.
  - DoD: the pins table is ready, and no duplicate manifest or name exists.
- [ ] 2. (depends on 1) Write the "Non-claims and evidence tags", "Evidence pins" and "Owner and overlap map" sections of `docs/spikes/cloudflare-kitesurf.md`.
  - DoD: every related issue (#18, #151, #181, #308, #314, #330, gitops#2544, mctl-agents#1035, telegram#1088) has an owner and an overlap statement.
  - DoD: the report states that no epic, implementation issue or follow-up was created.
- [ ] 3. (depends on 2) Write the current-state workload matrix and the capability compatibility matrix.
  - DoD: rows cover agent WebFetch/WebSearch (gitops `agent-platform/policy.yaml` and execution profiles), tenant `namax66/news-factory` headless Chromium with `NEWS_CHROMIUM_SANDBOX: "false"`, preview Playwright (#330), and Telegram/support web access.
  - DoD: every cell is VERIFIED, UNKNOWN, NOT_RUN or UNOBSERVED, with no blank cells. Vendor claims are tagged `[VENDOR]`.
- [ ] 4. (depends on 3) Write the minimal backend contract and the routing/fallback section.
  - DoD: the contract has operations, deadlines, the failure classes, `evidence_ref`/`trace_id` and cleanup.
  - DoD: the routing section has the read-only fallback rule, no automatic replay of `interact` or side effects, the idempotency key, the circuit breaker, observation fields and an operator troubleshooting table.
  - DoD: the section states that MCTL is the only identity, policy, approval, budget and audit authority.
- [ ] 5. (depends on 3) Write the threat model.
  - DoD: SSRF/metadata, redirect and DNS rebinding, sandbox escape, tenant bleed, cookie/token exposure, DOM/screenshot prompt injection, retention, egress, usage abuse and the unauthenticated engine endpoint each have an attack, control, deterministic negative test and enforcement owner.
- [ ] 6. (depends on 4, 5) Write the benchmark protocol and the no-go thresholds.
  - DoD: fixtures F1-F4 (including the negative cases), n ≥ 30, all metrics, the cost formula with UNKNOWN rates, the spend ceiling and time box, local vs hosted comparison, and thresholds fixed before measurement.
  - DoD: every result cell is `NOT_RUN (requires separate authorization)`.
- [ ] 7. (depends on 6) Write the four-option decision matrix, the counter-evidence, vendor lock-in vs self-host, and the proposed verdict `REFERENCE_ONLY`.
  - DoD: the verdict is tied explicitly to missing evidence and the absence of a platform browser workload, with re-activation triggers toward `HYBRID_FALLBACK`.
  - DoD: the verdict is worded as proposed, not decided.
- [ ] 8. (depends on 7) Add `roadmap/spikes/cloudflare-kitesurf.yaml`.
  - Fields: `lifecycle: proposed`, issue mctlhq/.github#343, outcomes `ADOPT_LIGHTWEIGHT, HYBRID_FALLBACK, REFERENCE_ONLY, REJECT`, `execution.devloop: true`, `evidence.report: docs/spikes/cloudflare-kitesurf.md`, and no `decision`.
  - Add one `AGENTS.md` "Spikes" entry.
  - DoD: the files are added and the commit carries the `Agent:` trailer required by `AGENTS.md`.

## Tests

- [ ] T1. `python3 roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new manifest.
- [ ] T2. `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` passes.
- [ ] T3. `python3 roadmap/scripts/lifecycle_guard.py --base-ref origin/main` passes. The new spike is `proposed`, with no decided or completed transitions.
- [ ] T4. Report lint by grep:
  - no `PASS` appears in any benchmark or negative-test result cell;
  - every number from kitesurf.dev is on a line tagged `[VENDOR]`;
  - every 40-hex pin in the report resolves to the commits named in requirements.md.
- [ ] T5. Scope check: `git diff --stat` touches only `docs/spikes/cloudflare-kitesurf.md`, `roadmap/spikes/cloudflare-kitesurf.yaml` and `AGENTS.md`.

## Rollback

Revert the single commit, or close the PR. The change is documentation plus one proposed `SpikeDefinition` with no runtime, infrastructure, Cloudflare or issue-state effect, so a revert restores the previous state completely. If only the verdict is disputed, the owner edits the report or records a different `decision` later. Nothing else needs undoing.
