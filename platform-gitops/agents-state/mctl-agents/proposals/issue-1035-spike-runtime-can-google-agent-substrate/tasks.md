# Tasks: issue-1035-spike-runtime-can-google-agent-substrate

- [ ] 1. Pin upstream: read `agent-substrate/substrate` at a tagged release or HEAD commit (docs/architecture.md, CRDs/APIs, install manifests, runtime handlers, LICENSE) and the GKE actor lifecycle docs. Write section 1 of `docs/spikes/1035-agent-substrate.md` — DoD: commit SHA, access date, license, required runtimes (gVisor/runsc, KVM), API maturity and GKE-only features are each cited with a link to code or docs; vendor figures are labeled `vendor-claim`.
- [ ] 2. Duplicate/ownership map (depends on 1): verify the current state/HEAD of #760, #757, #885, mctl-telegram#1088, #881/#883, mctl-gitops#2438 and the mctl-bridge repo (slot lifecycle, pause/resume, fencing) — DoD: one row each with state, verified date, relation and binding constraint; a Bridge field that could not be read is `unknown`.
- [ ] 3. Identity and state map: map the conversation ID, `agent_jobs` job and token, WorkItem/ContextSnapshot (`orchestrator/context_snapshot.py`, `orchestrator/work_context/`), Temporal workflow ID (`orchestrator/temporal/`), Argo workflow name, ADR-010 claim epoch (`orchestrator/lifecycle/`), claude-remote session, Bridge slot and approval ref to a hypothetical Actor ID — DoD: every row has a durability class and `must_stay_in_mctl`.
- [ ] 4. Capability gap matrix C1-C12 (depends on 1, 2, 3) — DoD: every row is `covered` (with an owning issue/ADR/file), `gap`, `not-applicable` or `unknown`, with evidence; an explicit "no adapter needed" baseline paragraph is included.
- [ ] 5. Workload scorecard W1-W3 (depends on 4) — DoD: each workload is scored independently with `in_process_state_useful`, current reconstruction cost and a Phase B feasibility token; unmeasured metrics are `unknown`; prerequisites conflicting with the 2026-10-29 runsc decision give `NOT_FEASIBLE_ON_CURRENT_HOSTS`.
- [ ] 6. Governance invariants G1-G8 and adapter boundary (depends on 3) — DoD: each invariant states how it is preserved or why it cannot be; the boundary `MCTL identity -> governed lifecycle request -> Substrate Actor/Worker` names MCTL as authority for identity, approvals, job state, budgets and evidence, with cold reconstruct as the fallback.
- [ ] 7. Phase B plan (gated) (depends on 5) — DoD: fixture, A/B arms, metrics, the six negative cases, a disposable-environment constraint (no MCTL nodes/tokens/data/paid/KVM) and the exact owner approval required; marked "not executed".
- [ ] 8. Decision section (depends on 4-7) — DoD: exactly one `STATUS:` line from {REUSE_CURRENT_RUNTIME, ADOPT_SUBSTRATE_ADAPTER, DEFER} (DRAFT allowed only before review); for DEFER, a revisit trigger and owner; stop conditions, rollback concept and the smallest next step; no implementation issue opened.
- [ ] 9. Add `tests/test_spike_1035_report.py`, modeled on `tests/test_spike_881_report.py` (depends on 8) — DoD: `uv run pytest tests/test_spike_1035_report.py` passes, and it fails on each malformed case listed under Tests.

## Tests

- [ ] T1. Exactly one `STATUS:` line whose token is in {DRAFT, REUSE_CURRENT_RUNTIME, ADOPT_SUBSTRATE_ADAPTER, DEFER}.
- [ ] T2. Gap matrix rows C1-C12 present; each status is in {covered, gap, not-applicable, unknown}; evidence is non-empty; `covered` rows cite an issue (`#\d+`), an ADR or a repo path.
- [ ] T3. Scorecard has exactly W1, W2, W3, each with a feasibility token in {FEASIBLE_DISPOSABLE, NOT_FEASIBLE_ON_CURRENT_HOSTS, NOT_WORTH_TESTING}.
- [ ] T4. No metric cell contains a number unless the row's evidence has a run link or a `vendor-claim` label.
- [ ] T5. STATUS DEFER requires "Revisit trigger:" and "Owner:" lines; STATUS ADOPT_SUBSTRATE_ADAPTER requires exactly one named workload and a run link.
- [ ] T6. Governance invariants G1-G8 are all present and non-empty.
- [ ] T7. The upstream pin line contains a 40-hex commit SHA or a tag plus an access date.

## Rollback

The change is additive documentation plus one test. Roll back by reverting the merge commit, which removes `docs/spikes/1035-agent-substrate.md`, any `docs/spikes/1035/` directory and `tests/test_spike_1035_report.py`. No cluster, gitops, secret or feature-flag state changes, so there is nothing to undo at runtime.
