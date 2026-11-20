# Governed release calendar: S0 research for an image-bump window policy (partial coverage), with Argo CD Sync Windows as a secondary safeguard and an MCTL Governed Sync Broker as the candidate exception path

## Context

Issue mctlhq/mctl-gitops#2828 asks for a research spike: what is the smallest
safe architecture for an operator-visible release/change calendar that
*enforces* deployment freezes across MCTL's GitOps and governed release paths?
It must reuse the existing release governance (`platform-gitops/release-gates.yaml`,
`scripts/release-gate.py`, `scripts/release-preflight.py`,
`scripts/release-ledger-shadow.py`, the MFA-backed mctl-api action-approval
and `release.grant` ledger), with no second approval authority, no new
deployment engine and no live change.

This is **revision 3**. Revision 2 answered the independent review
([#2828 comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218),
4 P1 / 5 P2 / 2 P3). Revision 3 answers the owner's "Sync-broker integration
design request" and "Revision 3 instruction" (2026-11-20). It makes the
**MCTL Governed Sync Broker** a first-class alternative. The broker spends one
human MFA grant from the existing mctl-api ledger and lets Argo CD apply
exactly one approved release to one frozen Application without opening
manual sync to tenants, CI or agents. Revision 3 compares the broker with E1
(GitOps carve-out), E2 (RBAC-restricted `manualSync`), D (no runtime
exception, break-glass only) and native or plugin mechanisms. **E1 is no
longer the default.** The scope is still **S0 only**:

| Stage | What | Authorized by this proposal? |
|---|---|---|
| S0 | Read-only inventory, offline policy model, a local inert Argo CD v3.3.8 harness, an inert broker prototype against that harness, a decision memo | Only after a **separate explicit owner GO to run S0**. Accepting this proposal is not that GO. |
| S1 | Shadow evaluator wired into CI (reports only) | **No.** Own proposal and owner GO. |
| S2 | Enforcement at write points; dedicated mctl-api `release.freeze_exception` kind | **No.** Separate owner security GO. |
| S3 | Argo `syncWindows`, Argo RBAC/account/project role, `argocd-cm` flags, broker deployment, secrets, pilot | **No.** Separate owner security GO and a narrowly scoped pilot. |

Target architecture under investigation: **HYBRID**. A canonical MCTL window
policy is judged at GitOps write points. Argo CD `AppProject.syncWindows`
are a secondary point-of-sync safeguard. The broker is the candidate path for
an MFA-approved exception at the point of sync. Nothing is claimed as
universal enforcement. The only defensible MVP name is **"image-bump window
policy (partial coverage)"**. Until the owner decides after S0, the effective
outcome is `REUSE_EXISTING_ONLY`.

### Finding index

| Finding | Resolved in |
|---|---|
| P1-1 merge queue / point of effect | design section 3; R-Q1..R-Q5; T20-T25 |
| P1-2 atomic single-use exception | design section 5, 6.2; R-X1..R-X8, R-G4..R-G7; T30-T37, T80-T89 |
| P1-3 exception vs Argo deny | design sections 6-7; R-A6..R-A9, R-G1..R-G3; T40-T44, T90-T97 |
| P1-4 truthful scope | design tables A/B; R-S1..R-S5 |
| P2-5 cron / one-off translation | design section 9; R-A1..R-A4; T50-T56 |
| P2-6 allow semantics | design section 2; R-P3; T1, T5, T6 |
| P2-7 scope mapping | design table C; R-M1..R-M4; T60-T64 |
| P2-8 stale P7 | design "Application shape"; R-S5 |
| P2-9 base-trust evaluator | design section 4; R-T1..R-T4, R-G10; T70-T74 |
| P3-10 DST | design section 2; R-P5..R-P8; T2-T4, T10-T13 |
| P3-11 syncOverrun / vendors | design "Argo CD v3.3.8 facts", section 9; R-A5 |
| Sync-broker request / Revision 3 items 1-8 | design sections 5-8; R-G1..R-G14; tasks 0, 8-11, 14; T80-T99 |

## User stories

- AS the platform owner I WANT S0 to tell me, from evidence, whether a Governed Sync Broker, E2, E1 or break-glass-only can let exactly one MFA-approved release through a freeze SO THAT I can decide on S1-S3 without anyone opening manual sync for every tenant or agent.
- AS a security reviewer I WANT the broker's Argo permissions, token scope, claim protocol and residual bypasses (admin, `kubectl`) stated exactly and tested on a local v3.3.8 harness SO THAT "Argo knows MFA" is never assumed.
- AS the mctl-api owner I WANT the exception to reuse the action-approval store and the dedicated-kind namespace, and to state precisely which new spend semantics it needs SO THAT the ledger stays the only approval authority.
- AS an on-call engineer I WANT an approved hotfix or a previously healthy rollback to pass a freeze through one bounded path while every other Application stays frozen SO THAT a freeze neither traps a needed fix nor is bypassed globally.
- AS an operator or AI agent I WANT every path labelled `enforced`, `detected-after-write`, `not-covered` or `unknown` SO THAT a freeze is never presented as stronger than it is.

## Acceptance criteria (EARS)

### Stage boundary

- R-B1. WHILE this proposal is in S0 THE SYSTEM SHALL NOT add or change any file under `.github/workflows/`, `platform-gitops/` (except this proposal directory), workflow-used `scripts/`, any AppProject, Argo CD RBAC, account, `argocd-cm` key, ruleset, release-gates entry, ledger mode, mctl-api action kind, Vault path, secret or live calendar event.
- R-B2. WHEN an S0 artifact is produced THE SYSTEM SHALL place it only under `docs/spikes/2828-release-calendar/`, `tests/fixtures/release-calendar-s0/` or `tests/research/release_calendar_s0/` (including `argo-inert/` and `broker-model/`), and SHALL NOT reference it from any workflow, CWFT, Helm chart, Dockerfile or service.
- R-B3. WHEN S0 finishes THE SYSTEM SHALL stop at an exit gate: a decision memo with one calendar outcome (`REUSE_EXISTING_ONLY`, `BOUNDED_CALENDAR_MVP`, `ADOPT_ARGO_SYNC_WINDOWS`, `HYBRID`, `DEFER_UNTIL_GATES_CLOSED`) and one exception-path outcome (`BROKER_PILOT_CANDIDATE`, `E2_HUMAN_ROLE_ONLY`, `D_BREAKGLASS_ONLY`, `NEITHER_SAFE_YET`), then an independent review and an owner decision on #2828.
- R-B4. THE SYSTEM SHALL NOT have any agent, DevLoop step, implementer or shepherd run an S0 task or any S1/S2/S3 change on the strength of this proposal's acceptance.
- R-B5. IF the owner has not recorded an explicit GO to *run* S0 on #2828 THEN THE SYSTEM SHALL NOT start S0 tasks 1-15 in tasks.md. Any Argo permission, secret, AppProject, flag or production action SHALL additionally require a separate owner security GO, which this proposal never grants.

### Scope and truthful coverage

- R-S1. WHEN S0 inventories production effect paths THE SYSTEM SHALL cover at least design tables A and B. This includes non-image values, shared charts, `bootstrap/templates/**`, `argocd/**`, cluster templates, non-image CWFTs (including the tenant RBAC lines that `wft-create-tenant` generates), `cloudflare-apply.yml`, Vault values, the deploy-key bypass (#2543), tenant manual sync (P8a), admin Argo actions (P8b), `kubectl`/`argocd --core` (P8c), tenant resource actions (P8d) and status-context trust (P12).
- R-S2. WHEN a path is labelled THE SYSTEM SHALL use exactly one of `enforced`, `detected-after-write`, `not-covered`, `unknown`, with a citation. A failed or unauthorized read SHALL be `unknown`.
- R-S3. WHILE any production-changing path is not `enforced` THE SYSTEM SHALL NOT call the result a "production deployment freeze".
- R-S4. WHEN a later stage reports a verdict THE SYSTEM SHALL include the coverage label of the evaluated path.
- R-S5. WHEN S0 classifies `admins-mctl-api` THE SYSTEM SHALL treat source 1 (mctl-api `helm/` pinned `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361`) and source 2 (`infra-components/mctl-platform/mctl-api` at `main`) separately, and SHALL treat `docs/runbooks/mctl-api-release-hold.md:66` ("`targetRevision: main`") as a stale claim, not as evidence.

### Policy semantics (offline model)

- R-P1. WHEN the model evaluates a change THE SYSTEM SHALL take only (policy, affected Application names, interval, exception record or none) and return `ALLOW`, `DENY` or `UNKNOWN` with the deciding rule.
- R-P2. IF the policy is absent, unparseable, has a duplicate key or unknown field, an invalid IANA zone, an unsupported recurrence part, a window longer than `max_window`, or no `default` THEN THE SYSTEM SHALL return `UNKNOWN`, and `UNKNOWN` SHALL never be read as `ALLOW`.
- R-P3. WHEN windows are evaluated THE SYSTEM SHALL apply the design section 2 truth table, which equals Argo CD v3.3.8 `CanSync(false)` except that `UNKNOWN` replaces the error branch. `default` SHALL be `allow` in version 1.
- R-P4. WHILE a change touches several Applications THE SYSTEM SHALL return `DENY` if any is `DENY`, else `UNKNOWN` if any is `UNKNOWN`, else `ALLOW`.
- R-P5. WHEN a recurring window is defined THE SYSTEM SHALL define start and end as wall-clock times in its IANA zone per occurrence, and SHALL accept an absolute `duration` only for `UTC` windows and UTC one-offs.
- R-P6. WHEN a local time is in a spring-forward gap THE SYSTEM SHALL use the first instant after the gap. WHEN it is ambiguous THE SYSTEM SHALL choose the reading that lengthens deny windows and shortens allow windows.
- R-P7. THE SYSTEM SHALL treat windows as half-open `[start, end)` in UTC and judge the interval `[t_check, t_effect_max]`.
- R-P8. THE SYSTEM SHALL bound recurrence expansion by the required field `max_window`.

### Merge queue and point of effect

- R-Q1. WHEN S0 models a queued PR THE SYSTEM SHALL treat a check at `T_check` as evidence only for `[T_check, T_check + margin]` and SHALL NOT label any PR or queue path `enforced` at the point of effect.
- R-Q2. THE SYSTEM SHALL distinguish check, merge, sync start and sync end, and SHALL separate "sync not started when the window opens" from "sync in flight".
- R-Q3. WHEN S0 runs fixtures THE SYSTEM SHALL cover: check T-60m / freeze T / merge T+5m / sync T+6m; a PR held in the queue across T; a merge at T-2m with sync start at T+1m; a multi-wave sync in flight at T.
- R-Q4. IF an Application has no Argo deny window THEN THE SYSTEM SHALL label every PR, queue and "commit before, reconcile during" path for it `not-covered` at the point of effect.
- R-Q5. WHEN S0 reports in-flight behaviour THE SYSTEM SHALL report v3.3.8 behaviour (operation paused, "Sync operation blocked by sync window") and SHALL NOT assume `syncOverrun`.

### Grant lifecycle (design only in S0)

- R-X1. THE SYSTEM SHALL design every freeze exception as a grant in the existing mctl-api action-approval store under a dedicated `release.*` kind (proposed `release.freeze_exception`), decided only by a human with fresh MFA on the existing decide page. No calendar view, ICS feed, MCP tool, chat message, broker or agent SHALL be able to grant or decide one.
- R-X2. WHEN a grant is spent THE SYSTEM SHALL use one atomic compare-and-set guarded by state, intent hash, expiry and `fresh_until` before any side effect. A ledger read SHALL never count as a claim.
- R-X3. THE SYSTEM SHALL build the intent server-side, from trusted reads, binding: kind, AppProject, Application, tenant/environment, approved GitOps SHA, every source's resolved revision, rendered-manifest SHA-256, live Application spec digest, image repository and `sha256` digest(s), diff, reason class (hotfix, or rollback with `dep_` id), requester and `not_after`.
- R-X4. IF the claim fails for any reason THEN THE SYSTEM SHALL refuse and SHALL NOT fall back to another grant.
- R-X5. WHEN a write-path consumer (S2, not the broker) consumes a grant and its push fails or its diff changes on rebase THE SYSTEM SHALL leave the grant spent.
- R-X6. WHEN a write-path exception lands THE SYSTEM SHALL record the effect as the `main` commit that carries `Release-Exception: <aar_id>` and the intent hash.
- R-X7. WHEN reconciling THE SYSTEM SHALL require a 1:1 mapping between spent grants and effects (commits or Argo operations), and SHALL report "spent without effect" separately from a violation.
- R-X8. WHILE a version hold, gate group, ledger requirement, `release.grant` requirement or `min_tag` refuses a change THE SYSTEM SHALL keep refusing it whatever the calendar or the exception says.

### Governed Sync Broker (inert prototype in S0 only)

- R-G1. THE SYSTEM SHALL evaluate the broker as a process separate from agent pods and worktrees, holding the only non-break-glass Argo identity with `applications, sync` (and `get`) on exactly the pilot Application names, with no `override`, `update`, `projects`, `exec` or wildcard.
- R-G2. WHILE a deny window with `manualSync: true` matches a frozen Application THE SYSTEM SHALL require that no tenant role, CI account or agent identity holds `applications, sync` on it (explicit RBAC deny, or a tenant pattern that excludes it). S0 SHALL confirm that `wft-create-tenant.yaml:1093-1097` generates the broad `sync` line today, and SHALL test a tenant bypass attempt.
- R-G3. THE SYSTEM SHALL record `role:admin` (`applications, *`, `projects, *`), `kubectl` and `argocd --core` as explicit break-glass residuals that the broker does not control.
- R-G4. WHEN the broker spends a grant THE SYSTEM SHALL first write a durable journal row keyed uniquely by `aar_id` with a request id, then run one CAS `approved -> claimed(request_id)`, so that two concurrent brokers or requests cannot both reach Argo.
- R-G5. WHEN the broker syncs THE SYSTEM SHALL call Argo `Sync` exactly once per grant, with no `manifests`, no `resources` subset, the Application's own prune and sync options, and an operation `info` carrying `aar_id` and request id.
- R-G6. IF an Argo operation may have been created (sync call sent, outcome unknown, crash, timeout) THEN THE SYSTEM SHALL NOT return the grant to a spendable state. It SHALL only observe the existing operation by `info`, and SHALL end in `executed`, `spent_failed` or `spent_unknown`. The generic `SettleActionApproval(succeeded=false)` return-to-`consumed` SHALL NOT be reused.
- R-G7. WHEN Argo resolves the sync revisions THE SYSTEM SHALL compare the rendered-manifest hash at the resolved revisions with the approved one. IF they differ THEN it SHALL terminate the operation, mark the grant `spent_failed` and record any partial apply as residual.
- R-G8. THE SYSTEM SHALL record that Argo CD v3.3.8 refuses a manual sync to a non-`targetRevision` revision on an auto-synced Application (`resolveSourceRevisions`). The broker therefore binds content (manifest hash and source paths), not `main` HEAD, and SHALL NOT mutate the Application spec, the AppProject or RBAC to obtain a pin.
- R-G9. IF there is no grant, mctl-api or Argo is unreachable, the policy is unreadable, the manifest or spec changed, the image digest differs, the Application is wrong or ambiguous, a source is unsupported, the grant is expired or rejected, or an operation is already running THEN THE SYSTEM SHALL refuse with no new sync and SHALL leave the window unchanged.
- R-G10. THE SYSTEM SHALL have the broker read policy, Application map and intent only from mctl-api and a base-pinned revision, never from a request payload, a PR head or an agent worktree.
- R-G11. WHEN a rollback is approved THE SYSTEM SHALL treat it as a forward GitOps commit restoring a `dep_` recorded healthy, followed by a broker sync under its own grant. Argo's history `Rollback` API is refused under auto-sync and SHALL NOT be used.
- R-G12. WHEN S0 evaluates the token THE SYSTEM SHALL state the blast radius of a stolen broker token (sync current `main` of pilot Applications only) and SHALL test a detector for pilot-Application syncs without a journaled `aar_id`.
- R-G13. WHEN S0 compares paths THE SYSTEM SHALL produce the decision/coverage/threat/cost matrix in design section 8, including E1 fail-open versus E2/broker fail-closed measured on the harness.
- R-G14. THE SYSTEM SHALL record, with source links and read dates, that no v3.3.8 hook authorizes a single sync by request id and that argoproj/argo-cd#29558 is open. Any other mechanism SHALL be labelled `unknown`, not assumed.

### Argo CD layer (inert evaluation only)

- R-A1. WHEN S0 evaluates projection THE SYSTEM SHALL classify constructs as `translatable`, `translatable-with-lifecycle` or `not-translatable`.
- R-A2. IF a matching window is `not-translatable` THEN THE SYSTEM SHALL mark the Argo layer `incomplete` for that Application and SHALL NOT emit a partial projection.
- R-A3. WHEN a one-off is projected as a yearly cron THE SYSTEM SHALL require an emit/remove lifecycle and a drift check.
- R-A4. THE SYSTEM SHALL project in UTC only, widening deny windows (narrowing allow windows) across DST, or marking them `not-translatable`.
- R-A5. WHEN S0 records Argo facts THE SYSTEM SHALL pin them to v3.3.8 (chart 9.5.9) and verify `manualSync`, `andOperator`, `timeZone`, in-flight behaviour and the revision-sync refusal on the harness.
- R-A6. THE SYSTEM SHALL NOT propose `manualSync: true` on any window that matches an Application on which a tenant, CI or agent role holds `applications, sync`.
- R-A7. WHEN an exception is approved THE SYSTEM SHALL let the change reach the cluster only through the path S0 selects (candidate: broker), for exactly the bound Application, while every other Application stays denied and the window is not edited.
- R-A8. WHEN S0 tests the Argo layer THE SYSTEM SHALL show on the harness: approved hotfix syncs; unapproved tenant sync fails; approved healthy rollback syncs; other Applications stay frozen; auto-sync and selfHeal remain blocked during the window.
- R-A9. THE SYSTEM SHALL record that AppProjects are rendered by `root-app` (project `default`), so a window never blocks its own removal. Only write guards and review control that path.

### Scope mapping

- R-M1. THE SYSTEM SHALL generate `GitOps path -> Application -> AppProject -> namespace` from a render at a pinned commit.
- R-M2. THE SYSTEM SHALL scope policy, broker RBAC and projected windows by exact Application names, with no wildcards, `namespaces` or `clusters`.
- R-M3. WHEN an Application is added, renamed or removed THE SYSTEM SHALL fail the mapping test until the map is regenerated.
- R-M4. WHEN a path feeds several Applications THE SYSTEM SHALL map it to all of them, and the broker SHALL treat a change to it as a manifest change for each.

### Trust boundary

- R-T1. WHEN a PR or queue check evaluates the policy THE SYSTEM SHALL run evaluator code and policy from the base commit.
- R-T2. IF a candidate PR modifies the evaluator, fixtures, workflow or policy THEN THE SYSTEM SHALL still return the base verdict.
- R-T3. THE SYSTEM SHALL NOT count integration-15368 contexts as trusted enforcement (P12).
- R-T4. THE SYSTEM SHALL NOT rely on `auto-merge.yml` `protected_re` as a trust boundary.

### Agent and operator interface (design only)

- R-I1. THE SYSTEM SHALL limit any future agent interface to read-only `list_release_windows`, `check_release_window` and `explain_release_block`, plus an optional `request_exception` that only creates a pending human decision. No agent interface SHALL invoke the broker or hold its token.

## Out of scope

- Running S0 without its own owner GO. Any S1, S2 or S3 change: CI wiring, enforcement, the mctl-api `release.freeze_exception` kind, a broker deployment, Argo accounts or project roles, RBAC lines, `argocd-cm` flags, AppProject `syncWindows`, Vault paths, MCP tools, calendar UI or ICS.
- Any live action: calendar events, freezes, grants, approvals, syncs, and experiments against the production cluster, repo settings, mctl-api or Argo CD.
- Closing #2543, adding an App-bound status context (P12), cluster admission policy, or controlling `role:admin`/`kubectl` (all recorded as dependencies or residuals).
- Forking Argo CD, adopting Octopus, Harness or GitLab, or rewriting DevLoop, the merge queue or ADR-006.
- Inventing weekends or holidays. Preview namespaces.

## Open questions

- Owner: which calendar outcome and which exception-path outcome after S0? This proposal hypothesizes `HYBRID` + `BROKER_PILOT_CANDIDATE`. `DEFER_UNTIL_GATES_CLOSED` / `NEITHER_SAFE_YET` is the conservative alternative while #2543 (OPEN, updated 2026-11-13) and P12 are open.
- mctl-api owner: is a dedicated `release.freeze_exception` kind with terminal `claimed -> executed | spent_failed | spent_unknown` states acceptable? The generic reserve/settle returns a failed call to `consumed` (mctl-api#772), which is wrong for a sync whose outcome may be unknown. Where would the broker journal live (mctl-api DB or broker-owned)? Mapped to mctl-api#1022.
- Broker placement: separate Deployment (default candidate) or inside mctl-api. Argo identity: local account or project-scoped JWT role. Both are unresolved until the harness comparison (task 10).
- TOCTOU: Argo v3.3.8 resolves `main` at sync time and refuses an explicit SHA on auto-synced Applications. Is the residual window between preflight and resolution, plus terminate-on-mismatch, acceptable? Or must the pilot Application's paths also be write-frozen (only image bumps are guardable today)?
- Tenant UX: removing the owning tenant's manual sync on a pilot Application is permanent, not window-bound, unless a further RBAC lifecycle is added. Who is the pilot Application and tenant?
- Live state is `unknown`: the running Argo CD version, live `argocd-cm` (including `requireOverridePrivilegeForRevisionSync`), live RBAC, any live `syncWindows` and project roles. `mctl_whoami` is non-admin with no teams, and `mctl_get_service_status admins/mctl-api` returned "not found" (no access).
- Do tenant resource actions (`Deployment/restart`) bypass sync windows? Not verified; the harness tests it (T93).
- Ruleset 18465404 `bypass_actors` is unreadable (`null`); the DeployKey bypass is `unknown`. CLAUDE.md lists `agy-formal-review` as a queue check that the repository ruleset read does not show (possibly an org ruleset): `unknown`.
- Propagation latency (#970 about 7 min) is stale until measured.
- Should an open critical incident create a deny window automatically? Recommended no.
- Vendor prices are `unknown` (not stated on the primary pages read).
