# Governed release calendar: S0 research for an image-bump window policy (partial coverage), with Argo CD Sync Windows as a secondary safeguard

## Context

Issue mctlhq/mctl-gitops#2828 asks for a research spike: what is the smallest
safe architecture for an operator-visible release/change calendar that
*enforces* (not merely displays) deployment freezes across MCTL's GitOps and
governed release paths, reusing the existing release governance
(`platform-gitops/release-gates.yaml`, `scripts/release-gate.py`,
`scripts/release-preflight.py`, `scripts/release-ledger-shadow.py`, the
MFA-backed mctl-api release ledger) without a second approval authority, a new
deployment engine, or any live change.

This is **revision 2**. The first version was reviewed independently
([#2828 comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218),
REQUEST_CHANGES, 4 P1 / 5 P2 / 2 P3), and the owner directed "return to
research / rewrite proposal only". This revision therefore narrows the
proposal to **stage S0: research and inert offline experiments only**. It
authorizes nothing that runs in CI, in a workflow, in a cluster, or in
production. The later stages are named only to bound S0's exit gate:

| Stage | What | Authorized by this proposal? |
|---|---|---|
| S0 | Read-only inventory, inert local fixtures, an offline policy model, a decision memo | Yes, after owner GO on this proposal. Nothing is wired into any workflow. |
| S1 | Shadow evaluator wired into CI (reports only) | **No.** Needs its own reviewed proposal and owner GO. |
| S2 | Enforcement, MFA exceptions, exception consume protocol | **No.** Needs a separate owner security GO after the S0 P1 findings are closed. |
| S3 | Generated Argo CD `AppProject.syncWindows` (secondary point-of-sync safeguard) | **No.** Needs a separate owner security GO and a narrowly scoped pilot. |

Target architecture under investigation: **HYBRID**. A canonical MCTL window
policy is judged at the GitOps write points, which are the primary release
authorizer. Argo CD `AppProject.syncWindows` act as a secondary safeguard at
the point of sync, are generated from the same policy, and never authorize
anything. This revision does **not** reject Argo CD Sync Windows. It also does
not claim universal enforcement. The current evidence (design.md, Current
state) supports one MVP name only: **"image-bump window policy (partial
coverage)"**. It must not be called a "production deployment freeze". Until
the owner decides after S0, the effective outcome is `REUSE_EXISTING_ONLY`
plus S0 research.

### Review finding index (where each one is resolved)

| Finding | Resolution in this revision |
|---|---|
| P1-1 merge queue / point of effect | design.md section 3; R-Q1..R-Q5 below; tests T20-T25 |
| P1-2 atomic single-use exception | design.md section 5; R-X1..R-X8; tests T30-T37 |
| P1-3 exception vs Argo deny | design.md section 6; R-A6..R-A9; tests T40-T44 |
| P1-4 truthful scope | design.md Current state tables A and B; R-S1..R-S4; MVP renamed |
| P2-5 cron / one-off translation | design.md section 7 translation matrix; R-A1..R-A4; tests T50-T56 |
| P2-6 allow semantics | design.md section 2 truth table; R-P3; tests T1, T5, T6 aligned |
| P2-7 scope mapping | design.md Current state table C; R-M1..R-M4; tests T60-T64 |
| P2-8 stale P7 | design.md Current state "P7 re-read"; R-S5 |
| P2-9 base-trust evaluator | design.md section 4; R-T1..R-T4; tests T70-T74 |
| P3-10 DST arithmetic | design.md section 2 time semantics; R-P5..R-P8; tests T2-T4, T10-T13 |
| P3-11 syncOverrun / vendor evidence | design.md Current state "Argo CD 3.3.8 facts" and section 8; R-A5; task 9 |

## User stories

- AS the platform owner I WANT an S0 research result that says exactly which production write paths a window policy could refuse before effect, which it could only detect afterwards, and which it cannot see SO THAT I decide on S1/S2/S3 from evidence, not from a claim of universal enforcement.
- AS a security reviewer I WANT an offline policy model with a single truth table and deterministic fixtures SO THAT the semantics of allow, deny, default, DST and recurrence can be checked before anything is wired into CI.
- AS an on-call engineer I WANT S0 to show, on an inert cluster, that an approved hotfix or healthy rollback can pass an Argo CD deny window while an arbitrary manual sync stays denied SO THAT a later freeze cannot trap a needed fix and cannot be bypassed globally.
- AS the mctl-api owner I WANT the exception design to reuse the existing atomic consume of action approvals SO THAT single use is a database compare-and-set, not a read followed by a hope.
- AS an operator or AI agent I WANT every future view to label each path `enforced`, `detected-after-write`, `not-covered` or `unknown` SO THAT a freeze is never shown as stronger than it is.

## Acceptance criteria (EARS)

### Stage boundary (S0 only)

- R-B1. WHILE this proposal is in S0 THE SYSTEM SHALL NOT add or change any file under `.github/workflows/`, `platform-gitops/` (except this proposal directory), `scripts/` used by any workflow, any AppProject, ruleset, release-gates entry, ledger mode, Argo CD setting or live calendar event.
- R-B2. WHEN an S0 artifact is produced THE SYSTEM SHALL place it only under `docs/spikes/2828-release-calendar/` (memo, inventory, evidence) or `tests/fixtures/release-calendar-s0/` and `tests/research/release_calendar_s0/` (inert model and fixtures), and SHALL NOT reference those files from any workflow, CWFT or Helm chart.
- R-B3. WHEN S0 finishes THE SYSTEM SHALL stop at an exit gate: a decision memo with the S0 decision matrix and a recommended outcome (`REUSE_EXISTING_ONLY`, `BOUNDED_CALENDAR_MVP`, `ADOPT_ARGO_SYNC_WINDOWS`, `HYBRID` or `DEFER_UNTIL_GATES_CLOSED`), followed by an independent review and an owner decision recorded on #2828. No S1/S2/S3 task SHALL start from this proposal.
- R-B4. THE SYSTEM SHALL NOT have any agent, DevLoop step, implementer or shepherd run an S1/S2/S3 change on the strength of this proposal's acceptance.

### Scope and truthful coverage

- R-S1. WHEN S0 inventories production effect paths THE SYSTEM SHALL cover at least the paths in design.md tables A and B, including non-image changes: values fields other than `image.*`, the shared `base-service` and `tenant` charts, `bootstrap/templates/**` (Applications, AppProjects), `argocd/**` (RBAC, settings), Argo cluster templates, CWFT deploy-key pushes (`wft-create-tenant`, `wft-add/remove-custom-domain`, `wft-provision-database`, `wft-retire-service`, `wft-delete-tenant-safe`), `cloudflare-apply.yml`, Vault value changes, the ruleset `DeployKey` bypass (#2543), Argo CD UI/CLI/`kubectl`/`argocd --core` admin paths, and required status context trust (P12).
- R-S2. WHEN a path is labelled THE SYSTEM SHALL use exactly one of `enforced` (refused before effect by trusted code), `detected-after-write`, `not-covered`, `unknown`, and SHALL cite a file and line, an API response or an inert test result for it. A failed or unauthorized read SHALL be labelled `unknown`, never `not-covered` or `enforced`.
- R-S3. WHILE any path that can change production state is labelled other than `enforced` THE SYSTEM SHALL NOT call the result a "production deployment freeze". The MVP name SHALL be "image-bump window policy (partial coverage)" unless S0 shows otherwise.
- R-S4. WHEN a later stage reports a verdict THE SYSTEM SHALL include the coverage label of the path that was evaluated (requirement carried forward to S1+, recorded here so S0 designs the label set).
- R-S5. WHEN S0 re-reads P7 THE SYSTEM SHALL classify each source of `admins-mctl-api` separately: the mctl-api `helm/` chart pinned to `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361` and the mctl-gitops `infra-components/mctl-platform/mctl-api` source tracking `main`. It SHALL treat runbook text as a claim to verify, not as live evidence.

### Policy semantics (offline model)

- R-P1. WHEN the model evaluates a change THE SYSTEM SHALL take as input only (policy document, set of affected Argo Application names, evaluation interval, exception record or none) and SHALL return one of `ALLOW`, `DENY`, `UNKNOWN` with the deciding rule.
- R-P2. IF the policy is absent, unparseable, has a duplicate key, an unknown field, an invalid IANA zone, an unsupported recurrence part, a window longer than `max_window`, or no `default` THEN THE SYSTEM SHALL return `UNKNOWN`. `UNKNOWN` SHALL never be read as `ALLOW`.
- R-P3. WHEN windows are evaluated THE SYSTEM SHALL apply the single truth table in design.md section 2. This table is identical to Argo CD 3.3.8 `SyncWindows.CanSync` with `isManual=false`, except that `UNKNOWN` replaces Argo's error branch. `default` SHALL be `allow` in policy version 1 (a deny-by-default calendar is expressed with allow windows).
- R-P4. WHILE a change touches several Applications THE SYSTEM SHALL evaluate each Application and return `DENY` if any is `DENY`, else `UNKNOWN` if any is `UNKNOWN`, else `ALLOW`.
- R-P5. WHEN a recurring window is defined THE SYSTEM SHALL define its start and end as local wall-clock times in its declared IANA zone, per occurrence. An absolute `duration` SHALL be allowed only for windows whose zone is `UTC` and for one-off windows given as UTC instants.
- R-P6. WHEN a local time does not exist (spring-forward gap) THE SYSTEM SHALL map it to the first instant after the gap. WHEN a local time is ambiguous (fall-back) THE SYSTEM SHALL choose the occurrence that makes a deny window longer and an allow window shorter.
- R-P7. THE SYSTEM SHALL treat every window as half-open `[start, end)` in UTC, and SHALL judge a change over an interval `[t_check, t_effect_max]`, returning `DENY` if any part of it intersects an active deny (or lies outside all allows when allows match).
- R-P8. THE SYSTEM SHALL bound recurrence expansion to the horizon `[t - max_window, t_effect_max]`, with `max_window` (proposed 21 days) a required policy field.

### Merge queue and point of effect

- R-Q1. WHEN S0 models the queued-PR path THE SYSTEM SHALL treat a check passed at time `T_check` as evidence only for `[T_check, T_check + margin]`, and SHALL NOT claim `enforced` for any PR or queue path where merge or sync can happen after that interval.
- R-Q2. WHEN S0 models effect timing THE SYSTEM SHALL distinguish four instants: check, merge to `main`, Argo sync start, Argo sync end. It SHALL also separate "sync not started when the window opens" from "sync in flight when the window opens".
- R-Q3. WHEN S0 runs the inert fixtures THE SYSTEM SHALL cover at least: check T-60m, freeze T, merge T+5m, sync T+6m; a PR held in the queue that merges after the freeze starts; a commit merged T-2m whose sync starts at T+1m; a multi-wave sync started at T-1m and still running at T.
- R-Q4. IF Argo CD Sync Windows are absent for an Application THEN THE SYSTEM SHALL label every PR, queue and "commit before freeze, reconcile during freeze" path for that Application as `not-covered` at the point of effect.
- R-Q5. WHEN S0 reports in-flight behaviour THE SYSTEM SHALL report what Argo CD 3.3.8 does (operation paused with "Sync operation blocked by sync window", per `controller/sync.go` at tag v3.3.8). It SHALL NOT assume `syncOverrun`, which v3.3.8 does not have.

### Single-use exceptions (design only in S0)

- R-X1. THE SYSTEM SHALL design exceptions as a decision kind in the existing mctl-api action-approval store, decided only by a human with fresh MFA on the existing decide page. No calendar view, ICS feed, MCP read tool, chat message or agent SHALL be able to grant one.
- R-X2. WHEN an exception is used THE SYSTEM SHALL spend it by one atomic compare-and-set (`approved` to `consumed`, matching `intent_hash`, unexpired, `fresh_until` not passed), as `ConsumeActionApproval` in mctl-api `internal/workitems/action_approvals.go` already does, **before** any GitOps push. A read of the ledger SHALL never count as a claim.
- R-X3. THE SYSTEM SHALL bind the exception's intent hash to: exception kind, environment, exact Argo Application name(s), exact GitOps path(s), image repository and digest (or, for a rollback, the target `dep_` deployment id and its recorded gitops commit and digest), reason class (`hotfix` or `rollback`) and `not_after`.
- R-X4. IF the consume CAS fails for any reason (already consumed, expired, intent mismatch, stale, unreadable) THEN THE SYSTEM SHALL refuse the write and SHALL NOT retry with a different exception.
- R-X5. WHEN a consumed exception's push fails, the run crashes, or a rebase changes the outgoing diff away from the bound intent THE SYSTEM SHALL leave the exception spent and require a new human decision (same rule as `deploy.apply`: "A grant is single use: after a failed submit, request a new one"). Push retries inside the same run SHALL be allowed only while the outgoing diff still equals the bound path and digest.
- R-X6. WHEN an exception's change lands THE SYSTEM SHALL record the authoritative effect as the `main` commit carrying a `Release-Exception: <aar_id>` trailer and the intent hash. The audit record SHALL be the pair (consumed ledger row, that commit).
- R-X7. WHEN reconciling THE SYSTEM SHALL require a 1:1 mapping: every freeze-window commit on a covered path carries exactly one consumed exception, and every exception id appears in at most one commit. A consumed exception with no commit after `not_after` SHALL be reported as "spent without effect", not as a violation.
- R-X8. WHILE a version hold, gate group, ledger requirement or `min_tag` refuses a change THE SYSTEM SHALL keep refusing it whatever the calendar or the exception says (logical AND; the exception lifts only the calendar refusal).

### Argo CD layer (inert evaluation only in S0)

- R-A1. WHEN S0 evaluates projection THE SYSTEM SHALL classify every policy construct in the translation matrix (design.md section 7) as `translatable`, `translatable-with-lifecycle` or `not-translatable`.
- R-A2. IF any window that matches an Application is `not-translatable` THEN THE SYSTEM SHALL mark the Argo layer for that Application `incomplete`, SHALL NOT generate a partial projection that silently drops it, and SHALL NOT count Argo as coverage for that Application.
- R-A3. WHEN a one-off window is projected as a yearly-repeating cron THE SYSTEM SHALL require a lifecycle: emitted no earlier than its start minus a lead time, removed after its end, and a drift check that fails if an expired one-off is still present.
- R-A4. THE SYSTEM SHALL project only in UTC (`timeZone` unset or `UTC`). Argo CD 3.3.8 computes the zone offset from `time.Now()` (`scheduleOffsetByTimeZone`), not from the occurrence. Any window whose local occurrence crosses a DST transition SHALL therefore be widened outward by the offset change for deny (and narrowed for allow), or else marked `not-translatable`.
- R-A5. WHEN S0 records Argo facts THE SYSTEM SHALL pin them to the deployed version (Argo CD v3.3.8, chart `argo-cd` 9.5.9 per `platform-gitops/argocd/Chart.yaml`) and verify `manualSync`, `timeZone`, `andOperator` and in-flight behaviour on an inert v3.3.8 cluster.
- R-A6. THE SYSTEM SHALL NOT propose `manualSync: true` on any deny window that matches an Application whose tenant role has `applications, sync` (e.g. `platform-gitops/argocd/rbac/tenants/labs.csv`), because that turns every tenant sync into a freeze bypass.
- R-A7. WHEN an exception has been consumed THE SYSTEM SHALL let the approved change reach the cluster through a carve-out bound to the exact Application name(s) and `not_after`, while every other Application in the window stays denied.
- R-A8. WHEN S0 tests the Argo layer THE SYSTEM SHALL show on an inert cluster: an approved hotfix syncs; an unapproved manual sync of a frozen Application fails; an approved healthy rollback syncs; a carve-out left open past `not_after` is detected; restoring the deny never needs the freeze to be disabled globally.
- R-A9. THE SYSTEM SHALL record that AppProjects are rendered by `root-app` (project `default`). A deny window in project `apps` or `platform` therefore does not stop a commit that removes the window itself from syncing. GitOps write guards and review are the only control on that path.

### Scope mapping

- R-M1. WHEN S0 maps scope THE SYSTEM SHALL produce a deterministic table `GitOps path -> Argo Application name -> AppProject -> destination namespace`, generated from a render of the ApplicationSets and bootstrap templates at a pinned commit, not by hand.
- R-M2. THE SYSTEM SHALL express policy scope as exact Argo Application names (and, for path-based write guards, the derived path set). Any projected Sync Window SHALL use only the `applications` selector with exact names, with no wildcards, `namespaces` or `clusters`, so OR vs AND (`andOperator`) cannot widen or narrow it.
- R-M3. WHEN an Application is added, renamed or removed in the render THE SYSTEM SHALL fail the mapping test until the mapping is updated.
- R-M4. WHEN a path feeds several Applications (`platform-gitops/helm-charts/base-service/**` feeds every `apps` Application, `helm-charts/tenant/**` every `tenant-*`) THE SYSTEM SHALL map it to all of them.

### Trust boundary

- R-T1. WHEN a PR or merge-queue check evaluates the window policy THE SYSTEM SHALL run evaluator code and policy taken from the base commit, never from the candidate tree (today `validate-manifests.yml` runs `scripts/release-gate.py` from the PR merge-ref checkout; only the policy is read from `HEAD^1`).
- R-T2. IF a candidate PR modifies the evaluator, its fixtures, its workflow or the policy THEN THE SYSTEM SHALL still return the base evaluator's verdict on the base policy.
- R-T3. WHEN S0 assesses required checks THE SYSTEM SHALL record that ruleset 18465404 binds `validate`, `reserved-hosts` and `cloudflare-plan` to integration 15368 (GitHub Actions). Any workflow job of that name can report it (P12), so no Actions-reported context counts as trusted enforcement until an App-bound context exists.
- R-T4. THE SYSTEM SHALL NOT rely on `auto-merge.yml` `protected_re` as a trust guarantee; it controls only the bot auto-merge route.

### Agent and operator interface (design only)

- R-I1. THE SYSTEM SHALL limit any future agent interface to read-only `list_release_windows`, `check_release_window`, `explain_release_block`, and an optional `request_exception` that can only create a pending human decision.

## Out of scope

- Any S1, S2 or S3 change: wiring an evaluator into CI or CWFTs, enforcement, exception decision kinds in mctl-api, AppProject `syncWindows`, MCP tools, calendar UI or ICS publication.
- Any live action: creating calendar events, freezes, grants or approvals; changing release-gates, the ledger mode, AppProjects, Argo CD RBAC, rulesets or deploy keys; any experiment on the production cluster or production repository settings.
- Closing #2543 (deploy-key bypass), the App-bound `release-hold` context (P12), or cluster admission policy (P8). This proposal depends on them and does not do them.
- Adopting Octopus Deploy, Harness or GitLab as a release engine; rewriting DevLoop, the merge queue or ADR-006.
- Inventing weekends or holidays; windows are owner-provided data.
- Preview namespaces.

## Open questions

- Owner: after S0, which outcome? This revision recommends evaluating `HYBRID`, with `DEFER_UNTIL_GATES_CLOSED` as the conservative alternative while #2543 (open, updated 2026-11-13) and P12 remain open.
- Can mctl-api's generic `ConsumeActionApproval` path (it excludes "dedicated" kinds) host a calendar-exception kind, and can a GitHub Actions or CWFT writer authenticate to consume it? The read path admits only `refs/heads/main` workflows per `validate-manifests.yml` comments. mctl-api owner input needed (#1022 lineage).
- Argo exception carve-out: E1 (GitOps carve-out commit to the generated AppProject) is the candidate. It needs an AppProject edit during a freeze, and a failed restore leaves the carve-out open (fail-open until detected). S0 must compare it with E2 (narrow sync RBAC plus `manualSync`) on an inert cluster before any recommendation.
- Ruleset 18465404 `bypass_actors` could not be read (the API returned `null` to this non-admin token). The DeployKey bypass described in `docs/runbooks/mctl-api-release-hold.md` P5b is therefore **unknown** as of 2026-11-20, not confirmed and not refuted.
- CLAUDE.md says `agy-formal-review` is a required queue check, but the repository ruleset read shows only `cloudflare-plan`, `reserved-hosts`, `validate`. The extra check may come from an org-level ruleset that was not read. Unknown.
- Live Argo CD state (version actually running, live AppProjects, whether any `syncWindows` exist live, tenant/service list) was not observable: `mctl_whoami` reports a non-admin identity with no teams, and `mctl_get_service_status admins/mctl-api` returned "Application not found" (no access, not absence).
- Propagation margin: #970 (closed 2026-09-02) reported up to ~7 min. The push webhook and `--revision-cache-expiration=30s` (`platform-gitops/argocd/values.yaml:313-322`) have since been added, so that figure is likely stale. No measured distribution exists; `argocd-freshness.yml` reports pass/fail only. S0 task 3 must measure or leave it unknown.
- Should an open critical incident create an automatic deny window? Recommended no (a non-human policy writer); left for the owner.
- Harness deployment freeze is documented as beta behind a feature flag, with account admins always able to bypass; licensing terms were not stated on the page read. Octopus restricts multi-project freezes to enterprise from 2025.2.7631. GitLab freezes need deploy jobs to honour `$CI_DEPLOY_FREEZE`. Prices were not found in the primary docs read; S0 task 9 records them or marks them unknown.
