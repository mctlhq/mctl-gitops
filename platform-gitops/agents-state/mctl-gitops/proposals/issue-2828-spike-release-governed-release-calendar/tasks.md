# Tasks: issue-2828-spike-release-governed-release-calendar

Revision 5 covers **S0 only**. It adds tasks 17-19 and tests T160-T186 for
the revision 4 review (self-lockout, single-pilot pin migration, deny-only
MVP). S0 is research, a read-only inventory, an
offline model, a local inert Argo CD v3.3.8 harness, an inert Governed Sync
Broker prototype and an inert MCP-PR-authoring model.

**None of these tasks may start until the owner records on #2828 an explicit
GO to run S0** (R-B5). Accepting this proposal is not that GO. The Tier 2
implementer, the shepherd and automatic workflows never run these tasks. A
human-directed research run carries them out.

Artifacts go only under:

- `docs/spikes/2828-release-calendar/`
- `tests/fixtures/release-calendar-s0/`
- `tests/research/release_calendar_s0/` (`argo-inert/`, `broker-model/`,
  `mcp-model/`)

No workflow, CWFT, chart, Dockerfile or service references them.

These are never touched: the production cluster, production Argo CD,
mctl-api, MCP, Vault, rulesets, AppProjects, Application pins, RBAC,
`argocd-cm`, release gates and the ledger. Any Argo permission, secret,
AppProject, flag, pin, MCP tool or production action needs a separate owner
**security** GO. These tasks never request one on their own.

S1, S2 and S3 tasks are deliberately **absent**.

## S0 tasks

- [ ] 0. Owner GO to run S0 recorded on #2828 — DoD: an owner comment explicitly authorizes S0 execution. Without it, stop here.
- [ ] 1. Re-verify design tables A/B read-only (depends on 0). Read: ruleset 18465404 `bypass_actors` and the org rulesets (an owner admin read, else `unknown`); the deploy keys; the live Argo CD version, `argocd-cm`, `argocd-rbac-cm` and AppProjects; `syncWindows`; project roles. — DoD: `docs/spikes/2828-release-calendar/inventory.md` labels P1-P17 (P8a-P8d separately), each with a citation and a date. Failed reads are `unknown`.
- [ ] 2. Re-read P7 per source, and flag `docs/runbooks/mctl-api-release-hold.md:66` as stale (depends on 0) — DoD: P7a, P7b and P7c are listed separately. `admins-mctl-api` is recorded as partially pinned, so it is not a G0 pilot. The runbook fix is mapped as a follow-up to the #2528 lineage and is not filed without an owner GO.
- [ ] 3. Measure commit-to-sync-start latency and root-app reconcile latency from existing read-only data (depends on 0) — DoD: p50/p95/max with sample size and date range, or `unknown` with the reason. This sets proposed values for `activation.lead` and `max_read_age`. #970's figure is not reused unmeasured.
- [ ] 4. Generate the scope map from a render at a pinned SHA (depends on 1) — DoD: `tests/fixtures/release-calendar-s0/app-map.json` lists `path -> Application -> AppProject -> namespace`, the per-Application sources with their `targetRevision` and a pinned flag, and `manifest-generate-paths`. It includes `argocd-self-managed` from the argocd chart render and the offline expansion of both ApplicationSet generators. Each entry carries a `recovery_chain` flag: `root-app` and `argocd-self-managed` are `required`; other candidates (`zitadel`, `vault`, `external-secrets`, ingress) are `required`, `not-required` or `unknown` with a reason. T60-T64 pass.
- [ ] 5. Offline model `tests/research/release_calendar_s0/model.py`: the policy function and the activation-state function (stdlib, PyYAML and `zoneinfo`; injected clock; `python3 -I`) (depends on 0) — DoD: T1-T13 and T110-T117 (the model parts) pass. Nothing else imports it.
- [ ] 6. Inert harness `argo-inert/` (depends on 4). Contents:
  - kind/k3d with Argo CD v3.3.8 (chart 9.5.9) and a local git server;
  - an AppSet generating multi-source, auto-sync, main-tracking Applications;
  - **one fully SHA-pinned multi-source pilot Application**;
  - a root-app-like parent rendering AppProjects and Application specs, in its own `default`-like AppProject;
  - a self-managed RBAC Application in the same project;
  - a copy of `applicationset-apps.yaml` with `missingkey=error` and `preserveResourcesOnDeletion: false` kept;
  - two tenants with RBAC copied from `rbac/tenants/labs.csv`;
  - `role:admin` as in `argocd/values.yaml:178-184`.

  The `controller/sync.go` behaviour (apply after the operation is created) is re-verified from source. The scripts refuse any kube context but their own. — DoD: reproducible from the spike directory, and no mctl or production credential is used.
- [ ] 7. Point-of-effect, in-flight and activation experiments (depends on 5, 6) — DoD: T20-T25 and T110-T117 recorded. The memo states which paths can be labelled at the point of effect, and the measured activation gap.
- [ ] 8. Grant-lifecycle and journal model (depends on 6). Use a local Postgres with `action_approval_requests` and the CAS statements copied from mctl-api `internal/workitems/action_approvals.go` at `2a8de33`. Add a *model* of the dedicated states (`approved -> claimed -> sync_requested -> executed | spent_failed | spent_unknown`) with `release_exception_ops` in the same transaction, plus lease/epoch fencing. — DoD: T30-T37 and T120-T129 recorded. The gap against the generic `SettleActionApproval` is written up for the mctl-api owner under mctl-api#1022.
- [ ] 9. Inert broker prototype `broker-model/` (depends on 6, 8). It covers preflight (including activation `effective`), claim, `sync_requested`, a single `Sync` (pinned revisions for G0, none for G2), the post-resolution check with terminate, observation and crash recovery. It runs against the harness only, with no Dockerfile, chart or deploy manifest. — DoD: T80-T92, T94-T96 and T100-T106 recorded with pass/fail and evidence. The guarantee class of each run is stated.
- [ ] 10. Argo identity and RBAC isolation comparison on the harness (depends on 6). Compare: a project-role JWT with TTL against a local `apiKey` account; tenant `sync` removal by a `deny` line against a narrowed pattern; `requireOverridePrivilegeForRevisionSync` on and off; and a copy of the `wft-create-tenant.yaml:1093-1099` block, shown to regenerate the broad line. — DoD: T90, T93, T98 and T99 recorded. The exact minimal permission set and the minting dependency (`projects, update`) are written up.
- [ ] 11. Phase-transition model and harness walk (depends on 6, 10) — DoD: all 12 (W, T, B) states classified; T96 and T130-T133 recorded. The documented rollout and rollback orders never enter the unsafe cell.
- [ ] 12. E1, E2 and D baselines on the harness (depends on 6, 9) — DoD: T40-T44 and T97 recorded, with E1 fail-open and E2/broker fail-closed shown side by side.
- [ ] 13. Offline MCP-PR-authoring model `mcp-model/` against a throwaway local git repo (depends on 4, 5) — DoD: T140-T149 pass. No GitHub call, MCP registration or tool implementation.
- [ ] 14. Status-contract fixtures (depends on 5, 7) — DoD: T150-T156 pass against the design 8.3 schema.
- [ ] 15. Translation prototype (stdout only) and a vendor evidence refresh (depends on 5, 6) — DoD: T50-T56 pass. The vendor table carries URLs, the access date and `unknown` prices.
- [ ] 16. Base-trust fixtures in a local throwaway git repo (depends on 5) — DoD: T70-T73 pass. T74 stays `unknown` unless it is reproduced in an owner-provided sandbox repo.
- [ ] 17. Recovery-chain guard model and self-lockout walk (depends on 4, 5, 6). Build the offline rendered-match checker of design 3.2 (`model.py lockout-check`: render, expand generators, v3.3.8 match semantics with OR and `andOperator`, base and candidate) and run the harness positive control, the injected self-lockout and the break-glass walk. — DoD: T160-T169 recorded. The memo states whether admin manual sync of a self-locked root-app is refused on v3.3.8, and the exact break-glass order. The `project-default.yaml:46-48` comment correction is listed as a follow-up and is not filed without an owner GO.
- [ ] 18. Single-pilot pin migration feasibility on the harness (depends on 4, 6). Render and apply M1, M2 and M3 (design 6.3.1) in turn to the harness copy of the `apps` ApplicationSet, then their reverse migrations. Nothing is changed in the repository. — DoD: T170-T177 recorded for each mechanism with pass/fail. The memo names the mechanism that passed, or records "no safe per-Application pin" (R-PM7), and states the deploy-flow cost for the pilot.
- [ ] 19. Allow-window impact on the harness and the effective-policy simulator (depends on 5, 6). — DoD: T180-T186 recorded. `model.py effective-diff` exists offline for any later allow proposal. The deny-only rule is shown to hold on every modelled write path.
- [ ] 20. Decision memo `docs/spikes/2828-release-calendar/decision.md` (depends on 1-19). DoD, all of:
  - the refreshed design section 9 matrix;
  - exactly one calendar outcome;
  - exactly one exception-path outcome (`BROKER_PINNED_PILOT_CANDIDATE` / `BROKER_DETECT_ONLY_REQUIRES_OWNER_RISK_ACCEPTANCE` / `E2_HUMAN_ROLE_ONLY` / `D_BREAKGLASS_ONLY` / `NEITHER_SAFE_YET`), defaulting to `NEITHER_SAFE_YET` when evidence is incomplete;
  - a reuse statement: what comes from mctl-api as-is, and what would be new (broker, Argo role and minter, `release_exception_ops`, dedicated kind, pilot pin);
  - residual risks: admin, `kubectl`, the spec-field race (T103), token compromise (T105), the activation gap;
  - follow-ups mapped to existing issues (#2543, #2668, #2528, mctl-api#1022, .github#181, .github#254, mctl-agents#217, argoproj/argo-cd#29558);
  - a "resolved by / still open" line for every finding of all three reviews (R1 P1-1..P3-11; re-review of revision 3 P1-1..P1-4, P2-5..P2-7, P3-8; review of revision 4 P1-1, P2-2, P2-3) and for every Revision 3 item 1-8;
  - the recovery-chain result (T160-T169), the pin mechanism result (T170-T177) and the allow result (T180-T186).
- [ ] 21. Independent re-review and owner decision (depends on 20) — DoD: a reviewer other than the investigator comments on #2828, and the owner records the outcome. `.status.yaml` stays `proposed` until that human process changes it.

## Tests

All tests are offline or run on the local inert harness. None run in
mctl-gitops CI.

Policy model (task 5)
- [ ] T1. No window matches -> `default` `ALLOW`. `default` missing or not `allow` -> `UNKNOWN`.
- [ ] T2. Half-open: an instant equal to start -> `DENY`; equal to end -> `ALLOW`.
- [ ] T3. A start in a spring-forward gap moves to the first instant after the gap.
- [ ] T4. Fall-back ambiguity: deny takes the longer span, allow the shorter.
- [ ] T5. An active allow plus an active deny -> `DENY`.
- [ ] T6. Allows match but the interval is outside them -> `DENY`. Only inactive denies match -> `ALLOW`.
- [ ] T7. A deny on X does not refuse Y. A change touching X and Y -> `DENY`.
- [ ] T8. `t_check` outside the window and `t_effect_max` inside -> `DENY`.
- [ ] T9. Unknown field, duplicate key, invalid zone, unsupported recurrence or a window over `max_window` -> `UNKNOWN`.
- [ ] T10. Fri 16:00 to Mon 08:00 Europe/Berlin: 65 h across fall-back, 63 h across spring-forward.
- [ ] T11. The one-off 2026-12-24T00:00Z to 2027-01-02T00:00Z covers the year boundary, with the end exclusive.
- [ ] T12. Overlapping denies in different zones -> their union, independent of order.
- [ ] T13. The expansion horizon is bounded. A mutation that drops the bound fails.

Point of effect (task 7)
- [ ] T20. Check T-60m, freeze T, merge T+5m, sync T+6m: applied without a window (`not-covered`), held until window end with an `effective` deny.
- [ ] T21. A PR in the merge queue across T -> cannot be labelled `enforced`.
- [ ] T22. Merge T-2m, sync start T+1m: applied without a window, held with one.
- [ ] T23. A multi-wave sync in flight at T -> the v3.3.8 pause behaviour is recorded.
- [ ] T24. A direct-push re-check at push time refuses a push landing at T+10s.
- [ ] T25. selfHeal during a deny: drift at T+1m is not reverted until window end, and auto-sync resumes at window end with the current `main`.

Window activation (tasks 5, 7; re-review P1-2)
- [ ] T110. Window merged at T-1m, root-app syncs at T+4m -> `reconciling` until T+4m, then `effective`. `[T, T+4m)` is reported `not-covered`, and the activation-SLA alert fired at T-lead.
- [ ] T111. Pre-scheduled window, root-app degraded across start -> it never reports `effective`; the alert fires; the operator text says "not in force".
- [ ] T112. A selector edit drops an intended Application -> `drifted` for that Application. A selector that matches an unintended Application -> `drifted`.
- [ ] T113. A one-off removed after end -> `expired`. A missing removal of its yearly-cron projection -> `drifted` before next year's recurrence.
- [ ] T114. An application-controller restart during an active window -> the window is still enforced after restart (recorded); the activation state stays `effective` only once fresh reads confirm it.
- [ ] T115. A 403, a timeout or a read older than `max_read_age` -> `unknown`, never `effective`.
- [ ] T116. `GetApplicationSyncWindows` with a deny that has `manualSync: true` -> `canSync: true` while `activeWindows` holds the deny. The model reports auto-sync blocked and manual sync open, and never "not frozen".
- [ ] T117. A live AppProject edited by an admin (window removed) while git still holds it -> `drifted`, and root-app selfHeal restoration is observed.

Grant lifecycle (task 8)
- [ ] T30. Two concurrent consumers of one approved grant -> exactly one CAS succeeds.
- [ ] T31. Replay of a spent grant -> refused.
- [ ] T32. An expired, stale (`fresh_until`) or intent-mismatched grant -> refused with the specific reason.
- [ ] T33. Crash after the claim and before the effect -> the grant is spent; "spent without effect" is reported; a new decision is required.
- [ ] T34. Write-path consumer: a rebase that keeps the diff equal to the intent -> retry under the same claim; a changed diff -> abort, grant spent.
- [ ] T35. The reconciler flags an un-granted effect, an effect citing a non-spent grant, and two effects for one grant.
- [ ] T36. A valid grant, but a version hold or a missing `release.grant` refuses -> still refused.
- [ ] T37. The requester (an agent identity) tries to decide or self-approve -> refused; only a pending request exists.

Journal and claim crash matrix (task 8; re-review P2-7)
- [ ] T120. Crash before TX1 commits -> the grant stays `approved`, with no `release_exception_ops` row.
- [ ] T121. Two writers run TX1 concurrently -> one row and one `claimed`; the loser is refused and never calls Argo.
- [ ] T122. Crash after TX1, before TX2 -> takeover under a new epoch continues with the same `op_id`. The grant never returns to `approved`.
- [ ] T123. Crash after TX2, before `Sync` is sent -> the new instance only observes, finds no operation by the deadline, and the grant becomes `spent_unknown` with the R-J7 evidence. No second `Sync`.
- [ ] T124. `Sync` sent and the response lost -> observe by `initiatedBy` and `info`, then `executed` or `spent_failed`. No second `Sync`.
- [ ] T125. Argo refuses `Sync` (`FailedPrecondition`, window, RBAC) -> `spent_failed`, no effect.
- [ ] T126. A stale instance (lease lost) attempts a transition -> the conditional write fails. If it had committed TX2, at most its one call exists; it is not made after the deadline.
- [ ] T127. Two operations carrying the same `info`, or a foreign operation with a copied `info` -> `spent_unknown` plus an alert. `info` is never treated as authorization.
- [ ] T128. mctl-api DB unavailable -> no step starts, no sync.
- [ ] T129. The mutation "settle failure returns to `consumed`" applied to the model -> the test suite fails, proving the property is checked.

Governed Sync Broker (task 9, harness only)
- [ ] T80. Two brokers or two requests race on one grant -> one claim, the loser never calls Argo, and exactly one Argo operation exists.
- [ ] T81. The same grant presented after `executed`, `spent_failed` or `spent_unknown` -> refused, with no Argo call.
- [ ] T82. An image digest in the rendered manifests that differs from the grant -> refused at preflight.
- [ ] T83. Misleading identity: a grant for `labs-a` with a request for `labs-a-x`, or a same-named Application in another project or namespace -> refused.
- [ ] T84. `main` changed the Application's render after approval -> refused at preflight; the grant stays `approved` and unclaimed.
- [ ] T85. G2 drift between preflight and effect -> the post-resolution mismatch triggers terminate, the grant becomes `spent_failed`, and the partial apply is recorded. **The result is labelled G2 detection, not prevention.**
- [ ] T86. A client-supplied field (revision, manifests, resources, prune, app name) -> refused; only a grant id is accepted.
- [ ] T87. An unrelated commit (G2 only) -> the resolved SHA differs and the manifest hash is equal -> accepted, with both SHAs journaled.
- [ ] T88. Argo outage during the sync call -> no second sync (see T124).
- [ ] T89. Orphan operation, or a row with no operation after the deadline -> the detector reports it, and the grant does not become spendable.
- [ ] T90. A tenant holding `applications, sync, apps/<tenant>-*` attempts `argocd app sync` on a pilot under a deny with `manualSync: true`: (a) with tenant sync left in place -> **succeeds**; (b) with the RBAC deny line -> refused. The same check is run for a `ci-freshness`-style account and an agent-like account.
- [ ] T91. The broker token used outside the broker: `override`, a non-pinned revision, a spec update, a project edit and non-pilot Applications are all refused.
- [ ] T92. An approved previously-healthy rollback (a pin move or a forward restore) under its own grant -> the broker sync succeeds. The history `Rollback` under auto-sync is refused (recorded).
- [ ] T94. During and after a broker sync, auto-sync and selfHeal of every frozen Application stay blocked, and the window is unchanged.
- [ ] T95. Broker down, mctl-api down, policy unreadable or the window not `effective` -> no sync, and the window is unchanged.
- [ ] T96. Phase rollback in the 6.7 order: the window is set to `manualSync: false` and verified, then the broker is removed, then tenant `sync` is restored. Each intermediate state is observed safe. The revision 3 order (tenant RBAC restored first) is run as a **negative** case, and it shows a tenant sync succeeding during the freeze.

Effect-time guarantee (task 9; re-review P1-1)
- [ ] T100. G0: approval binds pins X; preflight passes; root-app moves the pilot's pin to Y before the broker's `Sync(revisions=X)` -> Argo refuses with `FailedPrecondition`. Zero resources change (resource versions and the live image digest are compared before and after). The grant becomes `spent_failed`.
- [ ] T101. G0: a normal broker sync -> `operation.sync.revisions` equal X exactly. A mismatch is treated as a protocol violation that fails the test.
- [ ] T102. G0: commits to the pilot's chart and values paths on `main` during the window -> the broker sync applies only X (the rendered hash of X is verified on live objects).
- [ ] T103. G0 residual: a concurrent root-app change to non-revision spec fields (path, helm parameters, `syncOptions`) between `Sync` and the controller pick-up, with the race forced by injected delays. Record whether the changed fields are applied. If they are, the memo downgrades G0 to G1 for spec fields.
- [ ] T104. G2 adversarial schedule: approved hash A → preflight A → `main` moves to B → `Sync` resolves B → the controller applies B before the broker terminates. The expected result is that B is (partially) applied, recorded as **unapproved production effect**. This test, if reproduced, forbids any "exactly one" claim for main-tracking Applications.

Token compromise (task 9; re-review P1-3)
- [ ] T105. A direct `Sync` with the broker token and **no grant**, while a deny with `manualSync: true` is active -> expected to **succeed**: the pinned revisions (G0) or current `main` (G2) are applied. The result is labelled `not enforced`.
- [ ] T106. The detector flags T105 (an `initiatedBy` broker operation with no `sync_requested` row) and labels the alert post-effect. Token TTL expiry is shown to stop further use.

Phase transitions (task 11; re-review P1-4)
- [ ] T130. All 12 (W, T, B) states are enumerated in the model; exactly the deny-`manualSync:true` + tenant-present cells are unsafe.
- [ ] T131. Rollout order on the harness: revoke T, then add B, then arm W. Each step is observed before the next. Merging the window first is run as a negative case, and it shows the unsafe cell.
- [ ] T132. Rollback when verifying `manualSync: false` fails (an injected root-app failure) -> the procedure stops with tenant `sync` still revoked, and an alert fires.
- [ ] T133. RBAC and AppProject commits merged together -> the two Applications reconcile independently. The observed order is recorded, and the test shows that commit order is no proof of effect order.

Argo layer and baselines (tasks 10, 12)
- [ ] T40. E1 carve-out: the approved hotfix syncs, and other Applications stay denied.
- [ ] T41. An unapproved tenant sync of a frozen Application (no `manualSync`) -> refused.
- [ ] T42. An approved rollback through the E1 path -> succeeds.
- [ ] T43. An E1 carve-out not restored past `not_after` -> the Application stays open (fail-open recorded).
- [ ] T44. E2: `manualSync: true` with tenant sync removed -> the tenant is refused, the dedicated role is allowed, and `role:admin` is allowed (residual).
- [ ] T93. A tenant resource action (`Deployment/restart`) during a deny window -> record whether it is blocked, and label P8d accordingly.
- [ ] T97. Injected failures side by side: E1's restore fails, the broker crashes mid-claim, the E2 role token is unavailable -> E1 is left open; the broker and E2 are left closed.
- [ ] T98. `requireOverridePrivilegeForRevisionSync` `"true"` against unset: a `sync`-only principal passing a non-`targetRevision` SHA is refused, by `override` when the flag is true and by auto-sync in both cases.
- [ ] T99. Admin bypass evidence: `role:admin` attempts a manual sync during a deny (with and without `manualSync`), edits the window and uses `override`; `kubectl apply` changes a frozen resource. Each result is recorded, and each successful path is labelled break-glass with its audit trail.

MCP PR authoring (task 13; re-review P2-5, P3-8)
- [ ] T140. A valid proposal -> exactly one branch `release-window/<window_id>`, one PR, and a diff limited to one `windows[]` entry.
- [ ] T141. The same request repeated (same key) -> the same PR returned, with no new branch or commit.
- [ ] T142. An equivalent request with a different key -> the same `window_id`, and the existing PR is returned.
- [ ] T143. A request overlapping an existing same-scope, same-kind window -> refused, with a pointer to the existing window.
- [ ] T144. A diff touching another path, another window, a wildcard or a widened scope -> refused by the base-pinned validator.
- [ ] T145. A "proposal" that shortens or removes an existing deny -> refused unless it is `propose_window_removal`, which is marked as needing an owner reviewer.
- [ ] T146. The base changes and a rebase alters the semantic diff -> the PR is closed with a reason, and nothing is force-pushed.
- [ ] T147. Invalid IANA zone, unsupported recurrence, over `max_window`, an unknown field, or an Application not in the map -> refused before any branch exists.
- [ ] T148. The requester approving its own PR -> counted as no approval (modelled).
- [ ] T149. The tool identity has no Argo credential and no broker token: the model asserts its configuration surface contains neither.

Status contract (task 14; re-review P2-6)
- [ ] T150. An Application in an unrelated project -> the policy says `DENY`, the activation is `drifted` (unmatched), and it is never `effective`.
- [ ] T151. A selector that changed after merge -> `drifted`, with both window hashes shown.
- [ ] T152. A missing live AppProject, or a 403 -> `unknown`.
- [ ] T153. Every response lists the admin and `kubectl` residuals.
- [ ] T154. An in-flight sync at the start -> reported as in flight and paused, not as "blocked before effect".
- [ ] T155. A tenant restart action -> reported under P8d with the T93 result or `unknown`.
- [ ] T156. `manual_can_sync: true` under a deny with `manualSync: true` is never rendered as "not frozen".

Translation (task 15)
- [ ] T50. A weekly UTC window -> exact cron plus duration, and the harness agrees with the model.
- [ ] T51. A Europe/Berlin window in a DST week -> widened or narrowed, or `not-translatable`.
- [ ] T52. A one-off within a year -> lifecycle metadata, and the drift check fails if it is present after `end`.
- [ ] T53. A cross-year one-off -> `0 0 24 12 *` + `216h` with a lifecycle.
- [ ] T54. Ordinal weekday, `COUNT` or `UNTIL` -> `not-translatable`, non-zero exit, `incomplete`.
- [ ] T55. An invalid zone in a hand-written AppProject -> the v3.3.8 behaviour is recorded.
- [ ] T56. The model and the harness `CanSync(false)` agree on truth-table rows 1-5.

Scope mapping (task 4)
- [ ] T60. Each `services/*/*` maps to exactly one `<team>-<svc>` in project `apps`.
- [ ] T61. Adding, renaming or removing a service in a fixture copy fails until the map is regenerated.
- [ ] T62. `helm-charts/base-service/` maps to every `apps` Application.
- [ ] T63. Projections and broker RBAC that use wildcards, `namespaces` or `clusters` fail.
- [ ] T64. A window for `labs-mctl-telegram` matches no other tenant's Application, with and without `andOperator`.

Trust boundary (task 16)
- [ ] T70. A candidate PR changes the evaluator to always allow -> the base-pinned run still returns `DENY`.
- [ ] T71. A candidate PR deletes the active window -> the base policy still returns `DENY`.
- [ ] T72. A candidate PR changes fixtures or a selftest -> the verdict is unchanged.
- [ ] T73. A `yaml.py` planted in the candidate tree is not imported.
- [ ] T74. A same-named `validate` job -> `unknown` unless reproduced in an owner sandbox repo.

Bootstrap self-lockout and recoverability (task 17; revision 4 review P1-1)
- [ ] T160. (a) A proposed deny in AppProject `default`, with any selector (`applications: ["root-app"]`, `["*"]`, `namespaces: ["argocd"]`, `clusters: ["*"]`, or a selector matching only a non-chain `default` Application) -> refused by the policy validator and by the `mctl_propose_release_window` model before any branch exists.
- [ ] T161. A hand-written `syncWindows` deny added to `project-default.yaml` in a human PR (no policy-file change) -> refused by the rendered-AppProject scan run from the base. The same for `kind: allow`.
- [ ] T162. (b) Positive control on the harness: an `effective` deny in the `apps`-like project matches a pilot; a reviewed revert of that window is merged; root-app applies it and the window disappears from the live AppProject. A reviewed RBAC change is applied by the self-managed RBAC Application during the same window.
- [ ] T163. (c) Project migration: a candidate commit changes root-app's `spec.project` from `default` to `apps` while `apps` holds a deny with `applications: ["*"]` -> refused, although no window text changed. The same for moving `argocd-self-managed`, and for renaming an AppProject so that a window lands on the chain.
- [ ] T164. (c) Selector expansion: a deny in `apps` widened from an exact name to `["*"]` or to a `namespaces` glob -> the rendered match set is recomputed; refused only if it reaches the chain. With `andOperator: true` and with OR, the checker agrees with the harness `assignedWindows`.
- [ ] T165. (d) Injected existing self-lockout: an admin `kubectl edit` adds a deny matching root-app to the live `default`-like AppProject -> the status is `self-locked`, "not recoverable via GitOps", never `drifted` or `reconciling`, and the alert fires.
- [ ] T166. Break-glass walk (harness only, recorded as an audited incident): the revert is merged; an admin `argocd app sync root-app` is attempted and the result recorded; the live window is removed by `kubectl edit`; root-app applies `main`; the state leaves `self-locked`. The audit trail (Kubernetes audit entry, admin identity, PR, root-app sync revision) is attached.
- [ ] T167. Negative order: the live window is removed **before** the revert is merged -> root-app's selfHeal re-applies the window from `main` and the state returns to `self-locked`. This proves the order in design 3.2.
- [ ] T168. A deny in `default` that matches only a non-chain Application (for example a `monitoring`-like one) -> still refused by the MVP rule (R-L2). A mutation that relaxes R-L2 to "chain-only" makes this test fail.
- [ ] T169. A mutation of the checker that reads the policy's intended scope instead of the render -> T163 and T164 fail, proving the render is what is checked.

Single-pilot pin migration (task 18; revision 4 review P2-2)
- [ ] T170. For M1, M2 and M3: every non-pilot generated Application spec is byte-equal after normalization before and after the migration (name, project, sources, paths, `helm.valueFiles`, annotations including `manifest-generate-paths`, `syncPolicy`, `ignoreDifferences`).
- [ ] T171. For each mechanism: no Application `metadata.uid` changes, and no resource uid of the pilot or of any other Application changes. Nothing is pruned or recreated.
- [ ] T172. For each mechanism: the pilot differs only in its two `targetRevision` values, both set to commit SHAs, and the generator `revision` is still `main`.
- [ ] T173. M3 handoff under `preserveResourcesOnDeletion: false`: excluding the pilot directory, with each handoff variant (standalone Application first under the same name; a temporary `applicationsSync: create-update`) -> record whether the ApplicationSet deletes the Application or its resources. A variant that deletes anything fails.
- [ ] T174. For each mechanism, a pin key missing for a non-pilot under `missingkey=error` -> the template renders the shared value, and no generator error stops the ApplicationSet.
- [ ] T175. The reverse migration for each mechanism -> pre-migration output byte-equal, no deletion (T170/T171 re-run).
- [ ] T176. Mutation: pinning by editing the shared `.Values.spec.source.targetRevision` -> T170 fails for every Application and T172 fails for the generator, proving the checks detect it.
- [ ] T177. After a passing mechanism, an image bump to the pilot's `values.yaml` on `main` -> no change to the pilot until a reviewed pin move lands, which is recorded as the deploy-flow cost.

Allow windows and deny-only MVP (task 19; revision 4 review P2-3)
- [ ] T180. Harness: an allow window that is **inactive** now, added alone to the target AppProject -> matched Applications are blocked for auto-sync now (`CanSync(false)` false); the model's row 4 agrees.
- [ ] T181. Harness: an active allow plus an active deny on the same Application -> deny; the model's row 2 agrees (consistent with T5).
- [ ] T182. Harness: an allow whose selector drifts to an extra Application -> the extra Application is frozen outside the allow interval; the effective-policy diff lists it.
- [ ] T183. The policy validator and the `mctl_propose_release_window` model refuse `kind: allow`, whatever the scope.
- [ ] T184. A hand-written `kind: allow` in a rendered AppProject (human PR) -> refused by the rendered-AppProject scan.
- [ ] T185. `model.py effective-diff` over 35 days for a candidate allow lists every boundary instant at which the decision changes, inside and outside the allow interval; a cross-midnight allow and a DST week are included.
- [ ] T186. Mutation: the deny-only check disabled -> T183 and T184 fail.

## Rollback

- S0 changes nothing live. Withdrawing or rejecting the proposal is the rollback.
- The pin-migration experiments (task 18) run only against the harness copy of the ApplicationSet. Each has a tested reverse migration (T175). Nothing in `bootstrap/` is changed.
- The self-lockout injection and the break-glass walk (task 17) run only on the harness. The production recovery order, if one is ever needed, is the one T166 proves: merge the revert first, then remove the live window, then let root-app apply `main`.
- S0 artifacts are documentation and inert test assets. Workflows, charts, CWFTs, services and MCP do not reference them. Reverting the PR that adds them removes them completely.
- The harness clusters and the local Postgres are deleted with `kind delete cluster` / `k3d cluster delete` and by removing the container. They hold no production data or credentials.
- The phase order for an eventual pilot is recorded for the security GO only (design 6.7). It replaces the revision 3 order, which passed through the unsafe state.
  - Rollout: revoke tenant `sync` on the pilot, then add the broker identity, then arm the deny with `manualSync: true`. Each step is observed effective before the next.
  - Rollback: first set the window to `manualSync: false` and verify it `effective`, or end the freeze under its own approved procedure and verify the window is gone. Then remove the broker identity. Only then restore tenant `sync`.
  - If any verification fails, stay at the last verified, restricted state and alert.
  - Never roll back by weakening `version_holds`, the ledger mode, `protected_re`, rulesets or Argo CD settings. S0 touches none of them.
