# Tasks: issue-2828-spike-release-governed-release-calendar

Revision 3 covers **S0 only**: research, read-only inventory, an offline
model, a local inert Argo CD v3.3.8 harness and an inert Governed Sync Broker
prototype. **None of these tasks may start until the owner records an
explicit GO to run S0 on #2828** (R-B5). Accepting this proposal is not that
GO. The Tier 2 implementer, the shepherd and automatic workflows never run
them. They are carried out by a human-directed research run.

Artifacts go only under `docs/spikes/2828-release-calendar/`,
`tests/fixtures/release-calendar-s0/` and `tests/research/release_calendar_s0/`
(`argo-inert/`, `broker-model/`). No workflow, CWFT, chart, Dockerfile or
service references them. The following are never touched: the production
cluster, production Argo CD, mctl-api, Vault, rulesets, AppProjects, RBAC,
`argocd-cm`, release gates and the ledger. Any Argo permission, secret,
AppProject, flag or production action needs a separate owner **security** GO,
which these tasks never request on their own.

S1, S2 and S3 tasks are deliberately **absent**.

## S0 tasks

- [ ] 0. Owner GO to run S0 recorded on #2828 — DoD: a comment by the owner explicitly authorizing S0 execution. Without it, stop here.
- [ ] 1. Re-verify design tables A/B read-only (depends on 0): ruleset 18465404 `bypass_actors` and org rulesets (owner admin read, else `unknown`), deploy keys, the live Argo CD version, live `argocd-cm` (`requireOverridePrivilegeForRevisionSync`, accounts), live `argocd-rbac-cm`, live AppProjects, `syncWindows` and project roles — DoD: `docs/spikes/2828-release-calendar/inventory.md` labels P1-P15 (P8a-P8d separately) with a citation and date; failed reads are `unknown`.
- [ ] 2. Re-read P7 per source and flag `docs/runbooks/mctl-api-release-hold.md:66` as stale (depends on 0) — DoD: P7a (pin `c5e5d6f9...`), P7b and P7c are listed separately; the runbook fix is mapped as a follow-up to the #2528 lineage and is not filed without owner GO.
- [ ] 3. Measure commit-to-sync-start latency from existing read-only data (depends on 0) — DoD: p50/p95/max with sample size and date range, or `unknown` with the reason; #970's 7 min figure is not reused unmeasured.
- [ ] 4. Generate the scope map from a render at a pinned SHA (depends on 1) — DoD: `tests/fixtures/release-calendar-s0/app-map.json` with `path -> Application -> AppProject -> namespace`, per-Application source list and `manifest-generate-paths`, including shared-chart fan-out; T60-T64 pass.
- [ ] 5. Offline policy model `tests/research/release_calendar_s0/model.py` (stdlib + PyYAML + `zoneinfo`, injected clock, `python3 -I`) (depends on 0) — DoD: T1-T13 pass; imported by nothing else.
- [ ] 6. Inert harness `argo-inert/`: kind/k3d, Argo CD v3.3.8 (chart `argo-cd` 9.5.9), local git server, an AppSet generating multi-source auto-sync Applications shaped like `applicationset-apps.yaml`, two tenants with RBAC copied from `rbac/tenants/labs.csv`, `role:admin` as in `argocd/values.yaml:167-172`; the script refuses any kube context other than its own (depends on 4) — DoD: reproducible from the spike directory; no mctl or production credential used.
- [ ] 7. Point-of-effect and in-flight experiments (depends on 5, 6) — DoD: T20-T25 recorded; the memo states which paths can be labelled at the point of effect.
- [ ] 8. Grant-lifecycle model (depends on 6): local Postgres with `action_approval_requests` and the CAS statements copied from mctl-api `internal/workitems/action_approvals.go` at `2a8de33`, plus a *model* of the proposed dedicated `release.freeze_exception` states (`approved -> claimed -> executed | spent_failed | spent_unknown`) — DoD: T30-T37 recorded; the gap against the generic `SettleActionApproval` return-to-`consumed` is written up for the mctl-api owner under mctl-api#1022.
- [ ] 9. Inert Governed Sync Broker prototype `broker-model/` (depends on 6, 8): preflight, journal, claim, single `Sync` with `infos`, post-resolution manifest-hash check with terminate, observation and crash recovery, all against the harness only; no Dockerfile, chart or deploy manifest — DoD: T80-T92 and T94-T96 recorded with pass/fail and evidence.
- [ ] 10. Argo identity and RBAC isolation comparison on the harness (depends on 6): local `apiKey` account vs project-scoped JWT role for the broker; tenant `sync` removal by explicit `deny` line vs narrowed pattern; `requireOverridePrivilegeForRevisionSync: "true"` on and off; a copy of `wft-create-tenant`'s RBAC block shown to regenerate the broad line — DoD: T90, T93, T98 and T99 recorded; the exact minimal permission set is written in the memo.
- [ ] 11. E1, E2 and D baselines on the harness (depends on 6, 9) — DoD: T40-T44 and T97 recorded; E1 fail-open vs E2/broker fail-closed shown side by side.
- [ ] 12. Translation prototype (stdout only) and vendor evidence refresh (depends on 5, 6) — DoD: T50-T56 pass; vendor table carries URLs, access date and `unknown` prices.
- [ ] 13. Base-trust fixtures in a local throwaway git repo (depends on 5) — DoD: T70-T73 pass; T74 is `unknown` unless reproduced in an owner-provided sandbox repo.
- [ ] 14. Decision memo `docs/spikes/2828-release-calendar/decision.md` (depends on 1-13) — DoD: refreshed design section 8 matrix; exactly one calendar outcome and one exception-path outcome (`BROKER_PILOT_CANDIDATE` / `E2_HUMAN_ROLE_ONLY` / `D_BREAKGLASS_ONLY` / `NEITHER_SAFE_YET`); a reuse statement (what comes from mctl-api as-is, what would be new: broker process, Argo identity, journal, dedicated kind); residual risks (admin, `kubectl`, TOCTOU, token blast radius); follow-ups mapped to existing issues (#2543, #2668, #2528, mctl-api#1022, .github#181, .github#254, mctl-agents#217, argoproj/argo-cd#29558); every review finding P1-1..P3-11 and every Revision 3 item 1-8 has a "resolved by / still open" line.
- [ ] 15. Independent re-review and owner decision (depends on 14) — DoD: a reviewer other than the investigator comments on #2828; the owner records the outcome; `.status.yaml` stays `proposed` until that human process changes it.

## Tests

All tests are offline or run on the local inert harness. None run in mctl-gitops CI.

Policy model (task 5)
- [ ] T1. No window matches -> `default` `ALLOW`; `default` missing or not `allow` -> `UNKNOWN`.
- [ ] T2. Half-open: instant == start -> `DENY`; == end -> `ALLOW`.
- [ ] T3. Spring-forward gap start moves to the first instant after the gap.
- [ ] T4. Fall-back ambiguity: deny takes the longer span, allow the shorter.
- [ ] T5. Active allow + active deny -> `DENY`.
- [ ] T6. Allows match, interval outside -> `DENY`; only inactive denies match -> `ALLOW`.
- [ ] T7. Deny on X does not refuse Y; a change touching X and Y -> `DENY`.
- [ ] T8. `t_check` outside, `t_effect_max` inside -> `DENY`.
- [ ] T9. Unknown field, duplicate key, invalid zone, unsupported recurrence, over-`max_window` -> `UNKNOWN`.
- [ ] T10. Fri 16:00 to Mon 08:00 Europe/Berlin: 65 h across fall-back, 63 h across spring-forward.
- [ ] T11. One-off 2026-12-24T00:00Z to 2027-01-02T00:00Z covers the year boundary; end exclusive.
- [ ] T12. Overlapping denies in different zones -> union, order-independent.
- [ ] T13. Expansion horizon bounded; a mutation dropping the bound fails.

Point of effect (task 7)
- [ ] T20. Check T-60m, freeze T, merge T+5m, sync T+6m: applies without a window (`not-covered`); held until window end with a deny window.
- [ ] T21. PR in the merge queue across T -> cannot be labelled `enforced`.
- [ ] T22. Merge T-2m, sync start T+1m: applies without a window, held with one.
- [ ] T23. Multi-wave sync in flight at T -> v3.3.8 pause behaviour recorded.
- [ ] T24. Direct-push re-check at push time refuses a push landing at T+10s.
- [ ] T25. selfHeal during deny: drift at T+1m not reverted until window end; auto-sync resumes at window end with current `main`.

Grant lifecycle (task 8)
- [ ] T30. Two concurrent consumers of one approved grant -> exactly one CAS succeeds.
- [ ] T31. Replay of a spent grant -> refused.
- [ ] T32. Expired, stale (`fresh_until`) or intent-mismatched grant -> refused with the specific reason.
- [ ] T33. Crash after claim, before effect -> grant spent; "spent without effect" reported; new decision required.
- [ ] T34. Write-path consumer: rebase keeps diff == intent -> retry under the same claim; diff changes -> abort, spent.
- [ ] T35. Reconciler flags an un-granted effect, an effect citing a non-spent grant, and two effects for one grant.
- [ ] T36. Grant valid but a version hold or missing `release.grant` refuses -> still refused.
- [ ] T37. Requester (agent identity) tries to decide or self-approve -> refused; only a pending request exists.

Governed Sync Broker (task 9, harness only)
- [ ] T80. Two brokers (or two requests) race on one grant -> one claim; the loser never calls Argo; exactly one Argo operation exists.
- [ ] T81. Replay: the same grant presented after `executed`, `spent_failed` or `spent_unknown` -> refused, no Argo call.
- [ ] T82. Wrong image digest in the rendered manifests vs the grant -> refused at preflight.
- [ ] T83. Misleading identity: grant for `labs-a`, request for `labs-a-x` or a same-named Application in another project or namespace -> refused (exact name + project + namespace match).
- [ ] T84. Stale source: `main` changed the Application's render after approval -> refused at preflight; the grant stays `approved` (unclaimed) and cannot be applied to the new content.
- [ ] T85. Drift between preflight and effect: a commit to the service path lands between preflight and `Sync` -> the post-resolution hash mismatch triggers terminate; grant `spent_failed`; any partial apply recorded.
- [ ] T86. A client-supplied field (revision, manifests, resources, prune, app name) differing from the server-built intent -> refused; the broker API accepts only a grant id.
- [ ] T87. Unrelated commit (e.g. `agents-state/`) between approval and sync -> resolved SHA differs, manifest hash equal -> accepted; both SHAs journaled.
- [ ] T88. Argo outage during the sync call (timeout, no response) -> grant `claimed`; after restart the broker finds the operation by `info` or marks `spent_unknown`; it never issues a second sync.
- [ ] T89. Orphan operation: an operation with the broker's `info` but no journal row, or a journal row with no operation after the bound -> detector reports it; the grant does not become spendable.
- [ ] T90. A tenant holding today's `applications, sync, apps/<tenant>-*` attempts `argocd app sync` on a frozen pilot Application with `deny` + `manualSync: true`: (a) with tenant sync left in place -> **succeeds** (proves R-A6 risk); (b) with the RBAC deny line -> refused. The same check for the `ci-freshness`-style account and an agent-like account.
- [ ] T91. Broker token used outside the broker (exfiltration): it can sync current `main` of pilot Applications only; `override`, revision pin, spec update, project edit and non-pilot Applications are all refused; the detector flags a sync without a journaled `aar_id`.
- [ ] T92. Approved previously-healthy rollback: a forward commit restoring a `dep_`-recorded state plus its own grant -> broker sync succeeds; Argo history `Rollback` under auto-sync is refused (recorded).
- [ ] T94. During and after a broker sync, auto-sync and selfHeal of the pilot Application and every other frozen Application stay blocked; the AppProject window is unchanged.
- [ ] T95. Broker down, mctl-api down or policy unreadable -> no sync; window unchanged; break-glass is the only path (recorded).
- [ ] T96. Phase rollback of the prototype: removing the broker account or role and restoring tenant RBAC leaves the Application frozen (fail-closed removal); removing the window restores normal auto-sync.

Argo layer and baselines (tasks 10-11)
- [ ] T40. E1 carve-out: the approved hotfix syncs; other Applications stay denied.
- [ ] T41. Unapproved tenant sync of a frozen Application (no `manualSync`) -> refused.
- [ ] T42. Approved rollback through the E1 path -> succeeds (baseline for T92).
- [ ] T43. E1 carve-out not restored past `not_after` -> the Application stays open (fail-open recorded); the detector reports it.
- [ ] T44. E2: `manualSync: true` with tenant sync removed -> tenant refused; dedicated role allowed; `role:admin` allowed (residual).
- [ ] T93. Tenant resource action (`Deployment/restart`) during a deny window -> record whether it is blocked (expected: not a sync, so not blocked; label P8d accordingly).
- [ ] T97. Side by side: an injected failure of each mechanism (E1 restore commit fails; broker crashes mid-claim; E2 role token unavailable) -> E1 left open, broker and E2 left closed.
- [ ] T98. `requireOverridePrivilegeForRevisionSync` `"true"` vs unset: a `sync`-only principal passing a non-`targetRevision` SHA -> refused (override) when the flag is true; refused (auto-sync) in both cases on auto-sync Applications; on a harness Application without auto-sync the flag alone decides.
- [ ] T99. Admin bypass evidence: `role:admin` syncs during deny, edits the window and uses `override`; `kubectl apply` changes a frozen resource. Each recorded as break-glass with its audit trail (Argo events, `initiatedBy`), not as covered.

Translation (task 12)
- [ ] T50. Weekly UTC window -> exact cron + duration; the harness agrees with the model.
- [ ] T51. Europe/Berlin window in a DST week -> widened/narrowed or `not-translatable`, never an unwidened `timeZone`.
- [ ] T52. One-off within a year -> lifecycle metadata; drift check fails if present after `end`.
- [ ] T53. Cross-year one-off -> `0 0 24 12 *` + `216h` with lifecycle; agreement on 2026-12-31 and 2027-01-02.
- [ ] T54. Ordinal weekday, `COUNT`, `UNTIL` -> `not-translatable`, non-zero exit, `incomplete`.
- [ ] T55. Invalid zone in a hand-written AppProject -> v3.3.8 behaviour recorded.
- [ ] T56. Model vs harness `CanSync(false)` agree on truth-table rows 1-5.

Scope mapping (task 4)
- [ ] T60. Each `services/*/*` maps to exactly one `<team>-<svc>` in project `apps`.
- [ ] T61. Adding, renaming or removing a service in a fixture copy fails until regenerated.
- [ ] T62. `helm-charts/base-service/` maps to every `apps` Application.
- [ ] T63. Projections and broker RBAC with wildcards, `namespaces` or `clusters` fail.
- [ ] T64. A window for `labs-mctl-telegram` matches no other tenant's Application, with and without `andOperator`.

Trust boundary (task 13)
- [ ] T70. A candidate PR changes the evaluator to always allow -> base-pinned run still `DENY`.
- [ ] T71. A candidate PR deletes the active window -> base policy -> `DENY`.
- [ ] T72. A candidate PR changes fixtures or selftest -> verdict unchanged.
- [ ] T73. A planted `yaml.py` in the candidate tree is not imported.
- [ ] T74. A same-named `validate` job -> `unknown` unless reproduced in an owner sandbox repo.

## Rollback

- S0 changes nothing live. Withdrawing or rejecting the proposal is the rollback.
- S0 artifacts are documentation and inert test assets with no references from
  workflows, charts, CWFTs or services. Reverting the PR that adds them
  removes them completely.
- Harness clusters and the local Postgres are deleted with
  `kind delete cluster` / `k3d cluster delete` and by removing the container.
  They hold no production data or credentials.
- Phase rollback of an eventual pilot is recorded for the security GO only
  (design "Platform impact"). Remove the broker identity first (fail-closed),
  then restore tenant RBAC, then remove the window. Never roll back by
  weakening `version_holds`, the ledger mode, `protected_re`, rulesets or Argo
  CD settings, none of which S0 touches.
