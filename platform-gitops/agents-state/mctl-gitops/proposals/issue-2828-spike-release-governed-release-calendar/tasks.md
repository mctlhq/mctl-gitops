# Tasks: issue-2828-spike-release-governed-release-calendar

Revision 2 covers **S0 only**: research, read-only inventory and inert
offline experiments. Nothing here may be done by an automatic workflow, the
Tier 2 implementer or the shepherd. These tasks run only after an explicit
owner GO on this proposal and are carried out by a human-directed research
run. Every artifact goes under `docs/spikes/2828-release-calendar/`,
`tests/research/release_calendar_s0/` or `tests/fixtures/release-calendar-s0/`
and is **not** referenced by any workflow, CWFT, chart or
`validate-manifests.yml`. No production cluster, production repository
setting, ruleset, AppProject, release gate, ledger or calendar is touched.

S1 (shadow evaluator), S2 (enforcement and exceptions) and S3 (generated Argo
CD windows) are deliberately **not** listed as tasks. Each needs its own
reviewed proposal and owner (security) GO after S0's exit gate.

## S0 tasks

- [ ] 1. Re-verify Table A/B of design.md with read-only access: ruleset 18465404 including `bypass_actors` (needs an admin read by the owner; otherwise stays `unknown`), deploy keys, org-level rulesets (for `agy-formal-review`), the live Argo CD version, live AppProjects and any live `syncWindows` (`argocd proj windows list`, read-only, by the owner) — DoD: `docs/spikes/2828-release-calendar/inventory.md` has every path P1-P15 labelled `enforced` / `detected-after-write` / `not-covered` / `unknown` with a citation and date; failed reads are `unknown`.
- [ ] 2. Re-read P7 per source and mark the stale runbook claim (`docs/runbooks/mctl-api-release-hold.md:66`) — DoD: inventory lists P7a (chart pinned `c5e5d6f9...`), P7b (`infra-components/mctl-platform/mctl-api` at `main`) and P7c (all `main`-tracking Applications) separately; a follow-up to correct the runbook is mapped to #2528's successor or filed only after owner GO.
- [ ] 3. Measure commit-to-sync-start latency from existing read-only data (the `argocd-freshness.yml` run history, and Argo CD Application `status.operationState` timestamps if the owner can export them) — DoD: p50/p95/max with sample size and date range, or an explicit "unknown" with the reason; the 7-minute #970 figure is not reused unless re-measured.
- [ ] 4. Generate the scope mapping from a render (depends on 1): `helm template` of `platform-gitops/bootstrap` plus ApplicationSet expansion of `platform-gitops/services/*/*` and `tenants/*` at a pinned SHA — DoD: `tests/fixtures/release-calendar-s0/app-map.json` lists `GitOps path -> Application -> AppProject -> namespace` for every Application, including shared-chart fan-out (`helm-charts/base-service`, `helm-charts/tenant`); T60-T64 pass.
- [ ] 5. Write the offline policy model `tests/research/release_calendar_s0/model.py` implementing the design.md section 2 truth table, time semantics and R-P1..R-P8 (stdlib + PyYAML + `zoneinfo`, injected clock, `python3 -I`) — DoD: T1-T13 pass; the module is imported by no workflow.
- [ ] 6. Build the inert Argo CD v3.3.8 harness (kind/k3d, chart `argo-cd` 9.5.9, local git server, dummy multi-wave Applications in two AppProjects); the script refuses any kube context other than its own (depends on 4) — DoD: harness reproducible from the spike directory; no mctl or production credential used.
- [ ] 7. Run the merge-queue / point-of-effect fixtures and the in-flight experiment (depends on 5, 6) — DoD: results of T20-T25 recorded; the memo states exactly which paths can be labelled at the point of effect and confirms or corrects the v3.3.8 in-flight behaviour ("paused, resumes after window").
- [ ] 8. Evaluate the exception design (depends on 6): a local model of the section 5 protocol against a local Postgres with the `action_approval_requests` CAS statement copied from mctl-api `action_approvals.go` at `2a8de33`, plus the E1/E2 Argo carve-outs on the harness — DoD: T30-T37 and T40-T44 recorded; the memo recommends E1, E2 or "neither safe yet"; open questions for the mctl-api owner (kind, consumer authentication) are listed under mctl-api#1022.
- [ ] 9. Translation matrix and vendor evidence (depends on 5, 6): implement an offline generator *prototype* inside `tests/research/` that classifies and, where translatable, emits `syncWindows` YAML to stdout only; re-read vendor primary docs — DoD: T50-T56 pass; the vendor table carries URLs, access date and "unknown" for prices not stated in primary docs.
- [ ] 10. Base-trust fixtures in a local throwaway git repository (depends on 5) — DoD: T70-T73 pass against the base-pinned runner pattern; T74 (same-named `validate` job vs integration-bound context) recorded as reproduced only in an owner-provided sandbox repository, otherwise `unknown`.
- [ ] 11. Write the decision memo `docs/spikes/2828-release-calendar/decision.md` (depends on 1-10): refreshed S0 decision matrix, recommended outcome, MVP name and coverage statement, residual risks, follow-ups mapped to existing issues (#2543, #2668, #2528 runbook, mctl-api#1022, .github#181, .github#254, mctl-agents#217) — DoD: every review finding P1-1..P3-11 has a "resolved by / still open" line.
- [ ] 12. Independent re-review and owner decision (depends on 11) — DoD: a reviewer other than the investigator comments on #2828; the owner records the outcome; `.status.yaml` is changed only by that human process.

## Tests

All tests are offline or run on the inert harness. None run in CI for mctl-gitops.

Policy model (task 5)
- [ ] T1. No window matches the Application -> `default` (`ALLOW`); `default` missing or not `allow` -> `UNKNOWN` (truth-table rows 0-1).
- [ ] T2. Half-open: instant == start -> `DENY`; instant == end -> `ALLOW`.
- [ ] T3. Spring-forward: a window starting at a non-existent local time starts at the first instant after the gap.
- [ ] T4. Fall-back: a deny window whose start or end is ambiguous covers the longer span; an allow window covers the shorter span.
- [ ] T5. Active allow and active deny for one Application -> `DENY` (row 2).
- [ ] T6. Allow windows match the Application, interval outside all of them -> `DENY` (row 4); only deny windows match and none is active -> `ALLOW` (row 5).
- [ ] T7. Partial freeze: deny on Application X does not refuse a change to Y; a change touching X and Y is `DENY` (R-P4).
- [ ] T8. Interval judgement: `t_check` outside a window but `t_effect_max` inside -> `DENY`.
- [ ] T9. Unknown field, duplicate key, invalid zone, unsupported recurrence part, window longer than `max_window` -> `UNKNOWN`.
- [ ] T10. Fri 16:00 to Mon 08:00 Europe/Berlin spanning the October fall-back -> 65 h absolute; spanning the March spring-forward -> 63 h.
- [ ] T11. One-off 2026-12-24T00:00Z to 2027-01-02T00:00Z covers 2026-12-31T23:59Z and 2027-01-01T00:00Z; ends at 2027-01-02T00:00Z exclusive.
- [ ] T12. Overlapping recurring deny windows in different zones -> union, deterministic result regardless of window order.
- [ ] T13. Expansion horizon: an occurrence that started more than `max_window` before `t` is never considered; a model change that drops the bound fails a mutation test.

Point of effect (task 7)
- [ ] T20. Check T-60m `ALLOW`, freeze at T, merge T+5m, sync T+6m: without an Argo window the change applies (label `not-covered`); with a deny window it does not start until window end.
- [ ] T21. PR held in the merge queue across T: the record shows the check verdict predates T, so the path cannot be labelled `enforced`.
- [ ] T22. Merge T-2m, sync start T+1m: applies without a window; held with a window.
- [ ] T23. Multi-wave sync started T-1m, wave 2 due T+1m: record v3.3.8 behaviour (expected: operation stays Running, "Sync operation blocked by sync window", resumes after window end).
- [ ] T24. Direct-push writer: check at T-30s, push lands T+10s -> the pre-push re-check refuses.
- [ ] T25. selfHeal during a deny window: drift introduced at T+1m is not reverted until the window ends.

Exception protocol (task 8)
- [ ] T30. Two concurrent writers present the same approved exception -> exactly one CAS succeeds.
- [ ] T31. Replay of a consumed exception -> refused.
- [ ] T32. Expired, stale (`fresh_until` passed) or intent-mismatched exception -> refused with the specific reason.
- [ ] T33. Crash after consume, before push -> exception spent, no commit; reconciler reports "spent without effect"; a new decision is required.
- [ ] T34. Push rejected (non-fast-forward), rebase keeps the diff equal to the intent -> second push accepted under the same claim; rebase changes the diff -> abort, claim stays spent.
- [ ] T35. Reconciler: a covered-path commit in a deny window without a trailer, with a non-consumed id, or two commits with one id -> violation.
- [ ] T36. Exception valid for the calendar but a version hold refuses the digest -> still refused (R-X8).
- [ ] T37. An agent identity tries to approve or consume an exception it requested -> refused; only a pending request is created.

Argo layer (task 8, harness)
- [ ] T40. Approved hotfix with an E1 carve-out -> the target Application syncs to Healthy; other Applications in the window stay denied.
- [ ] T41. Unapproved `argocd app sync` of a frozen Application by a tenant-role user -> refused (no `manualSync` on the window).
- [ ] T42. Approved rollback to a `dep_` previously observed healthy -> succeeds through the same carve-out path.
- [ ] T43. Carve-out not restored past `not_after` -> detector reports it.
- [ ] T44. E2 variant: `manualSync: true` with tenant `sync` removed -> tenant sync refused, exception account sync allowed, `role:admin` sync allowed (recorded as residual).

Translation (task 9)
- [ ] T50. Weekly UTC window -> exact cron + duration; Argo `argocd app get` on the harness shows the window active at the same instants as the model.
- [ ] T51. Recurring Europe/Berlin window in a DST transition week -> widened (deny) / narrowed (allow) projection, or `not-translatable`; never an unwidened `timeZone` projection.
- [ ] T52. One-off within a year -> projected with lifecycle metadata; the drift check fails when the projection is still present after `end`.
- [ ] T53. Cross-year one-off -> `0 0 24 12 *` + `216h` with lifecycle; harness agrees on 2026-12-31 and 2027-01-02.
- [ ] T54. Ordinal weekday / `COUNT` / `UNTIL` -> `not-translatable`; generator exits non-zero; the Application is reported `incomplete`.
- [ ] T55. Invalid zone in a hand-written AppProject on the harness -> record v3.3.8 behaviour (rejected at write; falls back to UTC if present).
- [ ] T56. Model vs Argo agreement on the truth table: for rows 1-5, the model and `CanSync(false)` on the harness give the same result at sampled instants.

Scope mapping (task 4)
- [ ] T60. Every directory under `platform-gitops/services/*/*` maps to exactly one `<team>-<svc>` Application in project `apps`.
- [ ] T61. Adding, renaming or removing a service directory in a fixture copy fails the mapping test until the map is regenerated.
- [ ] T62. A change under `helm-charts/base-service/` maps to every `apps` Application.
- [ ] T63. Generated windows use only exact `applications` names; a projection containing a wildcard, `namespaces` or `clusters` fails.
- [ ] T64. Tenant isolation: a window for `labs-mctl-telegram` does not match any `admins-*`, `karabu-*`, `namax66-*` or `redloop-*` Application on the harness, with and without `andOperator`.

Trust boundary (task 10, local throwaway repo)
- [ ] T70. A candidate PR changes the evaluator to always allow -> the base-pinned run still returns `DENY`.
- [ ] T71. A candidate PR deletes the active window -> judged by the base policy -> `DENY`.
- [ ] T72. A candidate PR changes the model's fixtures or selftest -> the base-pinned verdict is unchanged.
- [ ] T73. The runner directory contains no candidate files (a planted `yaml.py` in the candidate tree is not imported).
- [ ] T74. A candidate workflow defines a job named `validate` -> recorded as `unknown` unless reproduced in an owner-provided sandbox repository.

## Rollback

- S0 changes nothing live. Rejecting or withdrawing the proposal is the rollback.
- S0 artifacts are documentation and inert test assets. Reverting the PR that
  adds them removes them completely, because no workflow, chart or CWFT
  references them.
- Inert harness clusters are deleted with `kind delete cluster` / `k3d cluster
  delete`; they hold no production data or credentials.
- Never roll back by weakening `version_holds`, the ledger mode,
  `protected_re`, rulesets or Argo CD settings, none of which S0 touches.
