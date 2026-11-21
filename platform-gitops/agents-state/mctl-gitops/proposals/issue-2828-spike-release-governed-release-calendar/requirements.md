# Governed release calendar: S0 research for an image-bump window policy (partial coverage), with Argo CD Sync Windows as an observed secondary safeguard and an MCTL Governed Sync Broker evaluated against a falsifiable effect-time guarantee

## Context

Issue mctlhq/mctl-gitops#2828 asks for a research spike: what is the smallest
safe architecture for an operator-visible release/change calendar that
*enforces* deployment freezes across MCTL's GitOps and governed release paths?
It must reuse the existing release governance (`platform-gitops/release-gates.yaml`,
`scripts/release-gate.py`, `scripts/release-preflight.py`,
`scripts/release-ledger-shadow.py`, the MFA-backed mctl-api action-approval
store and the `release.grant` kind). It must add no second approval
authority, no new deployment engine and no live change.

This is **revision 4**. Revision 2 answered the first review
([comment 7037225218](https://github.com/mctlhq/mctl-gitops/issues/2828#issuecomment-7037225218),
4 P1 / 5 P2 / 2 P3). Revision 3 made the **MCTL Governed Sync Broker** a
first-class alternative to E1 (GitOps carve-out), E2 (RBAC-restricted
`manualSync`), D (break-glass only) and native or plugin mechanisms.
Revision 4 answers the independent re-review of revision 3 (#2828,
2026-11-21, REQUEST_CHANGES 4 P1 / 3 P2 / 1 P3). In summary:

- A content check after `Sync` is **not** pre-effect enforcement. Revision 4
  defines guarantee classes G0/G1/G2. A broker that syncs an Application
  tracking `main` is only G2: partial unauthorized apply is possible.
- The only G0 candidate found in v3.3.8 source is a broker sync to the exact
  **SHA-pinned** `targetRevision` of every source. Argo itself refuses any
  other revision on an auto-synced Application. No MCTL `apps` Application
  is fully pinned today.
- A merged window is desired state. It is not an active freeze. Revision 4
  adds an observed activation lifecycle for windows.
- A stolen broker token bypasses the MFA ledger. This is labelled an
  unenforced boundary, and the detector is described as post-effect.
- Phase rollback is reordered so that tenant `sync` never coexists with an
  active `manualSync: true` deny.
- Design-only MCP tools that author a GitOps PR to propose or remove a
  window are added, with a status contract and a crash-safe journal/claim
  protocol.

The scope is still **S0 only**:

| Stage | What | Authorized by this proposal? |
|---|---|---|
| S0 | Read-only inventory, offline policy model, a local inert Argo CD v3.3.8 harness, an inert broker prototype and an inert MCP-PR-authoring model against that harness, a decision memo | Only after a **separate explicit owner GO to run S0**. Accepting this proposal is not that GO. |
| S1 | Shadow evaluator wired into CI (reports only) | **No.** Its own proposal and owner GO. |
| S2 | Enforcement at write points; a dedicated mctl-api `release.freeze_exception` kind; MCP tools | **No.** A separate owner security GO. |
| S3 | Argo `syncWindows`, Argo RBAC/account/project role, `argocd-cm` flags, source pinning of a pilot Application, broker deployment, secrets, pilot | **No.** A separate owner security GO and a narrowly scoped pilot. |

Target architecture under investigation: **HYBRID**. A canonical MCTL window
policy is judged at the GitOps write points. Argo CD `AppProject.syncWindows`
are a secondary point-of-sync safeguard, and they count only when observed as
`effective`. The broker is the candidate exception path, but only if S0 shows
G0 on a pinned pilot. Nothing is claimed as universal enforcement. The only
defensible calendar MVP name is **"image-bump window policy (partial
coverage)"**. Until the owner decides after S0, the effective outcome is
`REUSE_EXISTING_ONLY`.

### Finding index

Earlier reviews (revisions 2 and 3, carried forward):

| Finding | Resolved in |
|---|---|
| R1 P1-1 merge queue / point of effect | design section 3; R-Q1..R-Q5; T20-T25 |
| R1 P1-2 atomic single-use exception | design sections 5, 6.5; R-X1..R-X8, R-J1..R-J7; T30-T37, T80-T89, T120-T129 |
| R1 P1-3 exception vs Argo deny | design sections 6-7; R-A6..R-A9, R-G1..R-G3; T40-T44, T90-T99 |
| R1 P1-4 truthful scope | design tables A/B; R-S1..R-S5 |
| R1 P2-5 cron / one-off translation | design section 10; R-A1..R-A4; T50-T56 |
| R1 P2-6 allow semantics | design section 2; R-P3; T1, T5, T6 |
| R1 P2-7 scope mapping | design table C; R-M1..R-M4; T60-T64 |
| R1 P2-8 stale P7 | design "Application shape"; R-S5 |
| R1 P2-9 base-trust evaluator | design section 4; R-T1..R-T4, R-G10; T70-T74 |
| R1 P3-10 DST | design section 2; R-P5..R-P8; T2-T4, T10-T13 |
| R1 P3-11 syncOverrun / vendors | design "Argo CD v3.3.8 facts", section 10; R-A5 |
| Sync-broker request / Revision 3 items 1-8 | design sections 5-9; R-G1..R-G14; tasks 0, 8-12, 17 |

Re-review of revision 3 (2026-11-21). Each row gives the affected
requirements, design sections, S0 fixtures and the exit criterion:

| Finding | Requirements | Design | S0 fixtures | Exit criterion |
|---|---|---|---|---|
| P1-1 post-Sync hash check is not pre-effect | R-E1..R-E5, R-G7, R-G8 | 6.0, 6.3, 6.4, 9 | T85, T100-T104 | No `BROKER_PINNED_PILOT_CANDIDATE` unless T100-T103 show zero unapproved apply; T104 schedule recorded for main-tracking apps |
| P1-2 activation / acknowledgement | R-W1..R-W8 | 3.1 | T110-T117 | Memo states the activation SLA measured on the harness; no "freeze effective" from a merge alone |
| P1-3 stolen broker token | R-G12, R-K1..R-K4 | 6.6, 9 | T91, T105, T106 | Matrix row "token compromise" = `not enforced`; no unconditional "exactly one" claim |
| P1-4 phase rollback opens bypass | R-R1..R-R4 | 6.7 | T96, T130-T133 | Every transition of (window, tenant RBAC, broker identity) classified; the unsafe set is never reachable in the documented order |
| P2-5 MCP write contract | R-I1..R-I8 | 8 | T140-T149 | Offline fixtures pass; no tool implemented |
| P2-6 status contract | R-V1..R-V5 | 8.3 | T150-T156 | Response schema fixed; `canSync` never shown as coverage |
| P2-7 journal / claim crash gaps | R-J1..R-J7 | 6.5 | T80, T88, T89, T120-T129 | Crash matrix complete; every row has an expected end state |
| P3-8 idempotent, diff-restricted MCP ops | R-I3..R-I6 | 8.2 | T141-T146 | Duplicate requests produce one PR and one window; weakening refused |

## User stories

- AS the platform owner I WANT S0 to tell me, from evidence, which effect-time guarantee (G0, G1, G2 or none) each exception path can give on Argo CD v3.3.8 SO THAT I never accept a "single approved release" claim that is really post-effect detection.
- AS a security reviewer I WANT the broker's Argo permissions, its token-compromise boundary, its claim protocol and the residual bypasses (admin, `kubectl`) stated exactly and tested on a local harness SO THAT "Argo knows MFA" is never assumed.
- AS an operator I WANT to see whether a freeze is `desired`, `armed`, `effective`, `drifted` or `unknown` per Application, with evidence and read time, SO THAT a merged policy is never mistaken for an active freeze.
- AS the mctl-api owner I WANT the exception to reuse the action-approval store and the dedicated-kind namespace, with the claim and journal in one transaction, SO THAT the ledger stays the only approval authority and a crash never leaves a grant spendable.
- AS an on-call engineer I WANT an approved hotfix or a previously healthy rollback to pass a freeze through one bounded path while every other Application stays frozen SO THAT a freeze neither traps a needed fix nor is bypassed globally.
- AS an operator or AI agent I WANT to propose or remove a window only by opening a reviewed GitOps PR SO THAT no caller can edit an AppProject or sync an Application directly.

## Acceptance criteria (EARS)

### Stage boundary

- R-B1. WHILE this proposal is in S0 THE SYSTEM SHALL NOT add or change any file under `.github/workflows/`, `platform-gitops/` (except this proposal directory) or workflow-used `scripts/`. It SHALL NOT change any AppProject, Argo CD RBAC, account, `argocd-cm` key, Application `targetRevision`, ruleset, release-gates entry, ledger mode, mctl-api action kind, MCP tool, Vault path, secret or live calendar event.
- R-B2. WHEN an S0 artifact is produced THE SYSTEM SHALL place it only under `docs/spikes/2828-release-calendar/`, `tests/fixtures/release-calendar-s0/` or `tests/research/release_calendar_s0/` (including `argo-inert/`, `broker-model/` and `mcp-model/`). It SHALL NOT reference the artifact from any workflow, CWFT, Helm chart, Dockerfile or service.
- R-B3. WHEN S0 finishes THE SYSTEM SHALL stop at an exit gate: a decision memo that records exactly one calendar outcome (`REUSE_EXISTING_ONLY`, `BOUNDED_CALENDAR_MVP` limited to image bumps, `ADOPT_ARGO_SYNC_WINDOWS`, `HYBRID`, `DEFER_UNTIL_GATES_CLOSED`) and exactly one exception-path outcome (`BROKER_PINNED_PILOT_CANDIDATE`, `BROKER_DETECT_ONLY_REQUIRES_OWNER_RISK_ACCEPTANCE`, `E2_HUMAN_ROLE_ONLY`, `D_BREAKGLASS_ONLY`, `NEITHER_SAFE_YET`). An independent review and an owner decision on #2828 SHALL follow.
- R-B4. THE SYSTEM SHALL NOT have any agent, DevLoop step, implementer or shepherd run an S0 task, or any S1/S2/S3 change, because this proposal was accepted.
- R-B5. IF the owner has not recorded on #2828 an explicit GO to *run* S0 THEN THE SYSTEM SHALL NOT start tasks 1-17. Any Argo permission, secret, AppProject, flag, source pin, MCP tool or production action SHALL also require a separate owner security GO, which this proposal never grants.

### Effect-time guarantee (re-review P1-1)

- R-E1. THE SYSTEM SHALL classify every exception path by the guarantee it gives at the point of effect:
  - **G0**: before any resource is applied, Argo itself refuses any revision other than the approved one, and the approved revisions are immutable commit SHAs.
  - **G1**: the revision is checked before the request, but Argo may resolve different content between that check and the effect.
  - **G2**: divergence is only detected after the operation has been created, and is followed by terminate.
  - **none**.
- R-E2. THE SYSTEM SHALL NOT describe a G1 or G2 path as "exactly one approved release", "pre-effect enforcement" or "single-use at effect".
- R-E3. WHEN S0 evaluates the broker on an Application whose sources track `main` THE SYSTEM SHALL run the adversarial schedule "approved hash A → preflight A → `main` changes to B → `Sync` resolves B → controller applies B before terminate" (T104), and SHALL record that path as G2.
- R-E4. IF exact approved content cannot be pinned at effect on v3.3.8 for a candidate pilot Application THEN THE SYSTEM SHALL conclude `NEITHER_SAFE_YET`, or `BROKER_DETECT_ONLY_REQUIRES_OWNER_RISK_ACCEPTANCE`. The second outcome names a weaker guarantee that only a separate, explicit owner decision may accept. S0 SHALL NOT conclude `BROKER_PINNED_PILOT_CANDIDATE` from detection.
- R-E5. WHEN S0 evaluates the G0 candidate THE SYSTEM SHALL test, on the harness, a broker `Sync` whose `revisions`/`sourcePositions` equal every source's SHA-pinned `targetRevision`. It SHALL show that a concurrent pin change makes Argo refuse with `FailedPrecondition` before any apply (T100-T102). It SHALL record the residual race on non-revision spec fields as `unknown` until T103 measures it.

### Window activation lifecycle (re-review P1-2)

- R-W1. THE SYSTEM SHALL model each window, per intended Application, through observed states: `proposed → merged → reconciling → armed → effective → expired`, plus the side states `drifted` and `unknown`.
- R-W2. THE SYSTEM SHALL report `armed` only when four checks agree: the window is in the merged policy at SHA S; root-app's synced revision contains S; the live `AppProject.spec.syncWindows` equals the projection rendered from S; and every intended Application lists the window in `assignedWindows` while no unintended Application does.
- R-W3. THE SYSTEM SHALL report `effective` only WHILE the window is `armed`, it is in its time span, and the Application's `activeWindows` (from `GetApplicationSyncWindows`) contains the deny. For an exception design it SHALL also check that `canSync` matches the intended `manualSync` value.
- R-W4. IF any read is older than `max_read_age`, returns 403, times out or errors THEN THE SYSTEM SHALL report `unknown` and never `effective`.
- R-W5. IF a window is not `armed` at `start - activation_lead` THEN THE SYSTEM SHALL raise an "activation SLA missed" alert. It SHALL NOT state that the freeze is in force, and it SHALL give the operator instructions (design 3.1).
- R-W6. WHEN a merge lands after a window's start THE SYSTEM SHALL report the gap between the start and `effective` as `not-covered` for the affected Applications.
- R-W7. WHEN a one-off window has passed, or its yearly-cron projection is still present after `end`, THE SYSTEM SHALL report `expired` or `drifted` respectively, and SHALL alert on `drifted`.
- R-W8. THE SYSTEM SHALL NOT present a Git merge as a successful emergency freeze.

### Scope and truthful coverage

- R-S1. WHEN S0 inventories production effect paths THE SYSTEM SHALL cover at least design tables A and B: non-image values, shared charts, `bootstrap/templates/**`, `argocd/**`, cluster templates, non-image CWFTs (including the tenant RBAC lines that `wft-create-tenant` generates), `cloudflare-apply.yml`, Vault values, the deploy-key bypass (#2543), tenant manual sync (P8a), admin Argo actions (P8b), `kubectl` and `argocd --core` (P8c), tenant resource actions (P8d) and status-context trust (P12).
- R-S2. WHEN a path is labelled THE SYSTEM SHALL use exactly one of `enforced`, `detected-after-write`, `not-covered`, `unknown`, with a citation. A failed or unauthorized read SHALL be labelled `unknown`.
- R-S3. WHILE any production-changing path is not `enforced` THE SYSTEM SHALL NOT call the result a "production deployment freeze".
- R-S4. WHEN a later stage reports a verdict THE SYSTEM SHALL include the coverage label of the evaluated path, the activation state of the window, and the guarantee class of any exception.
- R-S5. WHEN S0 classifies `admins-mctl-api` THE SYSTEM SHALL treat its two sources separately: source 1 (the mctl-api `helm/` chart, pinned to `c5e5d6f9ae9d0cf84fdf9a60527396d8574a8361`) and source 2 (`infra-components/mctl-platform/mctl-api` at `main`). It SHALL treat `docs/runbooks/mctl-api-release-hold.md:66` ("`targetRevision: main`") as a stale claim, not as evidence. Because source 2 tracks `main`, `admins-mctl-api` is not a G0 pilot as deployed.

### Policy semantics (offline model)

- R-P1. WHEN the model evaluates a change THE SYSTEM SHALL take only the policy, the affected Application names, the interval and the exception record (or none). It SHALL return `ALLOW`, `DENY` or `UNKNOWN` together with the deciding rule.
- R-P2. IF the policy is absent, unparseable, has a duplicate key or unknown field, an invalid IANA zone, an unsupported recurrence part, a window longer than `max_window`, or no `default` THEN THE SYSTEM SHALL return `UNKNOWN`. `UNKNOWN` SHALL never be read as `ALLOW`.
- R-P3. WHEN windows are evaluated THE SYSTEM SHALL apply the truth table in design section 2. It equals Argo CD v3.3.8 `CanSync(false)`, except that `UNKNOWN` replaces the error branch. In version 1, `default` SHALL be `allow`.
- R-P4. WHILE a change touches several Applications THE SYSTEM SHALL return `DENY` if any Application is `DENY`, else `UNKNOWN` if any is `UNKNOWN`, else `ALLOW`.
- R-P5. WHEN a recurring window is defined THE SYSTEM SHALL define its start and end as wall-clock times in its IANA zone for each occurrence. It SHALL accept an absolute `duration` only for `UTC` windows and UTC one-offs.
- R-P6. WHEN a local time falls in a spring-forward gap THE SYSTEM SHALL use the first instant after the gap. WHEN a local time is ambiguous THE SYSTEM SHALL choose the reading that lengthens deny windows and shortens allow windows.
- R-P7. THE SYSTEM SHALL treat windows as half-open `[start, end)` in UTC, and SHALL judge the interval `[t_check, t_effect_max]`.
- R-P8. THE SYSTEM SHALL bound recurrence expansion by the required field `max_window`.

### Merge queue and point of effect

- R-Q1. WHEN S0 models a queued PR THE SYSTEM SHALL treat a check at `T_check` as evidence only for `[T_check, T_check + margin]`. It SHALL NOT label any PR or queue path `enforced` at the point of effect.
- R-Q2. THE SYSTEM SHALL distinguish check, merge, sync start and sync end. It SHALL keep "sync not started when the window opens" separate from "sync in flight".
- R-Q3. WHEN S0 runs fixtures THE SYSTEM SHALL cover four schedules:
  - check at T-60m, freeze at T, merge at T+5m, sync at T+6m;
  - a PR held in the queue across T;
  - a merge at T-2m with sync start at T+1m;
  - a multi-wave sync in flight at T.
- R-Q4. IF an Application has no `effective` Argo deny window THEN THE SYSTEM SHALL label every PR path, queue path and "commit before, reconcile during" path for it `not-covered` at the point of effect.
- R-Q5. WHEN S0 reports in-flight behaviour THE SYSTEM SHALL report the v3.3.8 behaviour (the operation is paused with "Sync operation blocked by sync window"). It SHALL NOT assume `syncOverrun`.

### Grant lifecycle (design only in S0)

- R-X1. THE SYSTEM SHALL design every freeze exception as a grant in the existing mctl-api action-approval store, under a dedicated `release.*` kind (proposed name: `release.freeze_exception`). Only a human with fresh MFA on the existing decide page SHALL decide it. No calendar view, ICS feed, MCP tool, chat message, broker or agent SHALL be able to grant or decide one.
- R-X2. WHEN a grant is spent THE SYSTEM SHALL use one atomic compare-and-set, guarded by state, intent hash, expiry and `fresh_until`, before any side effect. A ledger read SHALL never count as a claim.
- R-X3. THE SYSTEM SHALL build the intent server-side, from trusted reads. The intent SHALL bind: the kind; the AppProject; the Application; the tenant/environment; the approved GitOps SHA; every source's revision (for G0, the pinned SHAs themselves); the rendered-manifest SHA-256; the live Application spec digest; the image repository and `sha256` digest(s); the diff; the reason class (hotfix, or rollback with a `dep_` id); the requester; and `not_after`.
- R-X4. IF the claim fails for any reason THEN THE SYSTEM SHALL refuse, and SHALL NOT fall back to another grant.
- R-X5. WHEN a write-path consumer (S2, not the broker) consumes a grant and its push then fails, or its diff changes on rebase, THE SYSTEM SHALL leave the grant spent.
- R-X6. WHEN a write-path exception lands THE SYSTEM SHALL record the effect as the `main` commit that carries `Release-Exception: <aar_id>` and the intent hash.
- R-X7. WHEN reconciling THE SYSTEM SHALL require a 1:1 mapping between spent grants and effects (commits or Argo operations). It SHALL report "spent without effect" separately from a violation.
- R-X8. WHILE a version hold, gate group, ledger requirement, `release.grant` requirement or `min_tag` refuses a change THE SYSTEM SHALL keep refusing it, whatever the calendar or the exception says.

### Journal and claim protocol (re-review P2-7)

- R-J1. THE SYSTEM SHALL design the grant CAS (`approved → claimed`) and the insert of the broker operation row (`release_exception_ops`, unique on `aar_id`, holding `op_id`, `fence_epoch`, expected revisions and manifest hash) as **one transaction in the mctl-api database**, which is the single authoritative store. A broker-local journal SHALL be a cache only.
- R-J2. THE SYSTEM SHALL give each broker instance a lease with a monotonically increasing `fence_epoch`. Every state transition SHALL be conditional on the caller's epoch.
- R-J3. WHEN the broker is about to call Argo `Sync` THE SYSTEM SHALL first durably commit `claimed → sync_requested(op_id, epoch, deadline)`. Only the writer of that row SHALL ever call `Sync` for the grant. It SHALL do so at most once, and not after `deadline`. No other instance SHALL call `Sync` for that grant.
- R-J4. IF a crash, timeout or lease loss occurs after `sync_requested` THEN THE SYSTEM SHALL only observe the Application, and SHALL end in `executed`, `spent_failed` or `spent_unknown`. An uncertain `Sync` call SHALL never be retried.
- R-J5. IF a crash happens while the state is `claimed` and before `sync_requested` THEN THE SYSTEM SHALL let only the same `op_id`, re-fenced under a new epoch, proceed. The grant SHALL NOT return to `approved` or `consumed`.
- R-J6. THE SYSTEM SHALL treat the Argo operation `info` (`mctl-release-exception=<aar_id>/<op_id>`) as correlation metadata, never as authorization. Duplicate or contradictory `info` values, an operation with `info` but no row, or a row with no operation SHALL yield `spent_unknown` and an alert.
- R-J7. WHEN a grant is marked `spent_unknown` THE SYSTEM SHALL record the evidence: the deadline has elapsed; fresh reads of `operationState` and `status.history` show no operation initiated by the broker account after `sync_requested_at`, or an ambiguous one; and a human acknowledgement. A `spent_unknown` grant SHALL never become spendable again.

### Governed Sync Broker (inert prototype in S0 only)

- R-G1. THE SYSTEM SHALL evaluate the broker as a process separate from agent pods and worktrees. The broker SHALL hold the only non-break-glass Argo identity with `applications, sync` and `get` on exactly the pilot Application names, with no `override`, `update`, `projects`, `exec` or wildcard.
- R-G2. WHILE a deny window with `manualSync: true` matches a frozen Application THE SYSTEM SHALL require that no tenant role, CI account or agent identity holds `applications, sync` on it, either through an explicit RBAC deny or a tenant pattern that excludes it. S0 SHALL confirm that `wft-create-tenant.yaml:1095` generates the broad `sync` line today, and SHALL test a tenant bypass attempt.
- R-G3. THE SYSTEM SHALL record `role:admin` (`applications, *` and `projects, *`), `kubectl` and `argocd --core` as explicit break-glass residuals that the broker does not control.
- R-G4. WHEN the broker spends a grant THE SYSTEM SHALL follow R-J1..R-J5, so that two concurrent brokers or requests cannot both reach Argo.
- R-G5. WHEN the broker syncs THE SYSTEM SHALL call Argo `Sync` exactly once per grant. The call SHALL have no `manifests` and no `resources` subset, and SHALL use the Application's own prune and sync options and an operation `info` carrying `aar_id` and `op_id`. For a G0 pilot it SHALL pass `revisions` and `sourcePositions` equal to the approved pinned SHAs.
- R-G6. IF an Argo operation may have been created THEN THE SYSTEM SHALL NOT return the grant to a spendable state (R-J4). The generic `SettleActionApproval(succeeded=false)` return to `consumed` SHALL NOT be reused.
- R-G7. WHEN Argo has resolved the sync revisions THE SYSTEM SHALL compare them, and the rendered-manifest hash at them, with the approved values. IF they differ THEN the broker SHALL terminate the operation, mark the grant `spent_failed` and record any partial apply. THE SYSTEM SHALL label this step G2 detection, never pre-effect enforcement.
- R-G8. THE SYSTEM SHALL record the following v3.3.8 behaviour (`resolveSourceRevisions`). A revision that differs from a source's `targetRevision` is refused on an auto-synced Application. A revision equal to `targetRevision` is accepted. Exact pinning at effect therefore exists only for sources whose `targetRevision` is a commit SHA. The broker SHALL NOT mutate the Application spec, the AppProject or RBAC itself to obtain a pin.
- R-G9. IF any of the following holds THEN THE SYSTEM SHALL refuse, start no new sync and leave the window unchanged: there is no grant; mctl-api or Argo is unreachable; the policy is unreadable; the window is not `effective`; the manifest or spec changed; the image digest differs; the Application is wrong or ambiguous; a source is unsupported; the grant is expired or rejected; or an operation is already running.
- R-G10. THE SYSTEM SHALL have the broker read the policy, the Application map and the intent only from mctl-api and from a base-pinned revision, never from a request payload, a PR head or an agent worktree.
- R-G11. WHEN a rollback is approved THE SYSTEM SHALL treat it as a forward GitOps commit that restores a `dep_` deployment recorded as healthy (for a G0 pilot: a pin move to that commit), followed by a broker sync under its own grant. THE SYSTEM SHALL NOT use Argo's history `Rollback` API, which is refused under auto-sync.
- R-G12. WHEN S0 evaluates the broker token THE SYSTEM SHALL state the blast radius of a stolen token. With the token, an attacker can sync the current spec of the pilot Applications during a freeze **without any grant**. THE SYSTEM SHALL label that boundary `not enforced` (R-K1..R-K4).
- R-G13. WHEN S0 compares paths THE SYSTEM SHALL produce the decision/coverage/threat/cost matrix in design section 9, including E1's fail-open behaviour versus the fail-closed behaviour of E2 and the broker, as measured on the harness.
- R-G14. THE SYSTEM SHALL record, with source links and read dates, that no v3.3.8 hook authorizes a single sync by request id, and that argoproj/argo-cd#29558 is open. Argo resource hooks (PreSync) SHALL be evaluated only as a hypothesis, labelled `unknown` (design 6.8). Any other mechanism SHALL be labelled `unknown`, not assumed.

### Broker token compromise (re-review P1-3)

- R-K1. THE SYSTEM SHALL list "direct `Sync` with an exfiltrated broker token, without a grant" as an unenforced token-compromise boundary in requirements, design and the matrix.
- R-K2. THE SYSTEM SHALL constrain the evaluated token: exact pilot Application names only, `sync` and `get` only, a project-role JWT with the shortest TTL S0 can operate, no long-lived `apiKey` if avoidable, a Vault path that no agent role reads, and no use outside the broker's ServiceAccount. A NetworkPolicy SHALL NOT be counted as proof that the token cannot be used elsewhere.
- R-K3. WHEN S0 runs T105 (a direct `Sync` with the broker token and no grant) THE SYSTEM SHALL record the result exactly. The expected result is that the sync **succeeds** while a `manualSync: true` deny is active. The detector alert SHALL be labelled post-effect.
- R-K4. THE SYSTEM SHALL NOT claim that the broker path yields "exactly one MFA-authorized release" without stating that the claim excludes token compromise and admin or `kubectl` paths, and holds only for G0.

### Phase transitions and rollback (re-review P1-4)

- R-R1. THE SYSTEM SHALL classify every combination of window state (`none`, `deny/manualSync:false`, `deny/manualSync:true`), tenant `sync` on the pilot Application (`present`, `revoked`) and broker identity (`present`, `absent`) as safe or unsafe. `deny/manualSync:true` with tenant `sync` present is unsafe.
- R-R2. THE SYSTEM SHALL order any eventual rollout as follows, each step observed effective before the next: revoke tenant `sync`; add the broker identity; set the deny window with `manualSync: true`.
- R-R3. THE SYSTEM SHALL order any rollback as follows, each step observed effective before the next: set the window to `manualSync: false`, or end the freeze under its own approved procedure; remove the broker identity; then restore tenant `sync`. IF step 1 cannot be verified THEN THE SYSTEM SHALL stay restricted and alert.
- R-R4. THE SYSTEM SHALL treat commit order as no proof of effect order. RBAC (`argocd-self-managed`) and AppProjects (`root-app`) reconcile independently, so each step SHALL be verified by observation.

### Argo CD layer (inert evaluation only)

- R-A1. WHEN S0 evaluates projection THE SYSTEM SHALL classify each construct as `translatable`, `translatable-with-lifecycle` or `not-translatable`.
- R-A2. IF a matching window is `not-translatable` THEN THE SYSTEM SHALL mark the Argo layer `incomplete` for that Application, and SHALL NOT emit a partial projection.
- R-A3. WHEN a one-off is projected as a yearly cron THE SYSTEM SHALL require an emit/remove lifecycle and a drift check (R-W7).
- R-A4. THE SYSTEM SHALL project in UTC only. Across DST it SHALL widen deny windows and narrow allow windows, or mark them `not-translatable`.
- R-A5. WHEN S0 records Argo facts THE SYSTEM SHALL pin them to v3.3.8 (chart 9.5.9). It SHALL verify `manualSync`, `andOperator`, `timeZone`, the in-flight behaviour and the revision-sync rule on the harness.
- R-A6. THE SYSTEM SHALL NOT propose `manualSync: true` on any window that matches an Application on which a tenant, CI or agent role holds `applications, sync`.
- R-A7. WHEN an exception is approved THE SYSTEM SHALL let the change reach the cluster only through the path S0 selects, for exactly the bound Application. Every other Application SHALL stay denied, and the window SHALL NOT be edited.
- R-A8. WHEN S0 tests the Argo layer THE SYSTEM SHALL show on the harness that: an approved hotfix syncs; an unapproved tenant sync fails; an approved healthy rollback syncs; other Applications stay frozen; auto-sync and selfHeal stay blocked during the window.
- R-A9. THE SYSTEM SHALL record that AppProjects are rendered by `root-app` (project `default`), so a window never blocks its own removal. Only write guards and review control that path.

### Scope mapping

- R-M1. THE SYSTEM SHALL generate the map `GitOps path -> Application -> AppProject -> namespace` from a render at a pinned commit.
- R-M2. THE SYSTEM SHALL scope the policy, the broker RBAC and the projected windows by exact Application names, with no wildcards, `namespaces` or `clusters`.
- R-M3. WHEN an Application is added, renamed or removed THE SYSTEM SHALL fail the mapping test until the map is regenerated.
- R-M4. WHEN a path feeds several Applications THE SYSTEM SHALL map it to all of them. The broker SHALL treat a change to it as a manifest change for each.

### Trust boundary

- R-T1. WHEN a PR or queue check evaluates the policy THE SYSTEM SHALL run the evaluator code and the policy from the base commit.
- R-T2. IF a candidate PR modifies the evaluator, fixtures, a workflow or the policy THEN THE SYSTEM SHALL still return the base verdict.
- R-T3. THE SYSTEM SHALL NOT count integration-15368 contexts as trusted enforcement (P12).
- R-T4. THE SYSTEM SHALL NOT rely on `auto-merge.yml` `protected_re` as a trust boundary.

### Agent and operator interface (design only; re-review P2-5, P3-8)

- R-I1. THE SYSTEM SHALL limit any future agent or operator interface to:
  - read-only `list_release_windows`, `check_release_window` and `explain_release_block`;
  - an optional `request_exception`, which only creates a pending human decision;
  - `mctl_propose_release_window` and `mctl_propose_window_removal`, which only author a GitOps PR against the policy file.
- R-I2. THE SYSTEM SHALL NOT give any MCP caller Argo `projects, update`, `applications, sync`, the broker token or direct write access to an AppProject. No MCP tool SHALL call the broker.
- R-I3. WHEN a window is proposed THE SYSTEM SHALL validate, from the base, the exact-scope input schema: exact Application names, IANA zone, recurrence subset, duration not above `max_window`, owner, and `decided_in`. It SHALL derive the window id deterministically and show the derived blast radius (the exact Applications matched).
- R-I4. WHEN the same request is repeated THE SYSTEM SHALL return the existing PR. The request is identified by the idempotency key and the window id, and deduplicated on branch `release-window/<window_id>`. THE SYSTEM SHALL NOT create a second PR or an overlapping duplicate window.
- R-I5. THE SYSTEM SHALL restrict the PR diff to the allowlisted YAML paths of the policy file. IF the diff touches any other path, deletes a deny the caller does not own, broadens a selector, or shortens or weakens an existing deny THEN THE SYSTEM SHALL refuse it, unless the request is an explicit `propose_window_removal` that needs owner review.
- R-I6. WHEN a rebase or retry happens THE SYSTEM SHALL recompute the diff against the new base and refuse if it is no longer the same semantic change.
- R-I7. THE SYSTEM SHALL require normal PR review, with no self-approval. Removal or weakening of a deny SHALL need an owner reviewer.
- R-I8. THE SYSTEM SHALL record a stable audit trail: request id, caller identity, window id, PR number, reviewed head SHA and merge SHA.

### Calendar status contract (design only; re-review P2-6)

- R-V1. THE SYSTEM SHALL return, per Application, four values separately: the policy decision (`ALLOW`/`DENY`/`UNKNOWN` with the rule), the activation state (R-W1), the coverage label of the asked-about path (R-S2), and the guarantee class of any exception (R-E1).
- R-V2. THE SYSTEM SHALL include evidence with each answer: policy source SHA, root-app synced revision, live AppProject window hash, `assignedWindows`/`activeWindows`, read timestamps and age.
- R-V3. THE SYSTEM SHALL NOT present Argo `canSync=true` or `false` as proof that every deployment path is covered. In v3.3.8, `canSync` is the **manual**-sync answer (`CanSync(true)`).
- R-V4. IF the live AppProject is missing, the Application is in an unrelated project, a selector changed, or the evidence is stale THEN THE SYSTEM SHALL report `unknown` or `drifted`, not `effective`.
- R-V5. THE SYSTEM SHALL list residuals in every answer: admin, `kubectl`, in-flight syncs and tenant restart actions (P8d).

## Out of scope

- Running S0 without its own owner GO.
- Any S1, S2 or S3 change: CI wiring, enforcement, the mctl-api `release.freeze_exception` kind, the `release_exception_ops` table, a broker deployment, Argo accounts or project roles, RBAC lines, `argocd-cm` flags, AppProject `syncWindows`, pinning any Application's `targetRevision`, Vault paths, MCP tools, calendar UI or ICS.
- Any live action: calendar events, freezes, grants, approvals and syncs, and any experiment against the production cluster, repo settings, mctl-api or Argo CD.
- Closing #2543, adding an App-bound status context (P12), cluster admission policy, and controlling `role:admin` or `kubectl`. All are recorded as dependencies or residuals.
- Forking Argo CD; adopting Octopus, Harness or GitLab; rewriting DevLoop, the merge queue or ADR-006.
- Accepting any G1 or G2 guarantee on the owner's behalf.
- Inventing weekends or holidays. Preview namespaces.

## Open questions

- Owner: which calendar outcome and which exception-path outcome after S0? Revision 4's working hypothesis is `HYBRID` with either `BROKER_PINNED_PILOT_CANDIDATE` (only if T100-T103 hold) or `NEITHER_SAFE_YET`. `DEFER_UNTIL_GATES_CLOSED` remains the conservative calendar alternative while #2543 (OPEN, updated 2026-11-13) and P12 stay open.
- G0 requires a pilot Application whose sources are **all** SHA-pinned. No `apps` Application is pinned today: both of its sources track `main` (`applicationset-apps.yaml:38,50`). `admins-mctl-api` pins only source 1. Is the owner willing, in a later S3, to pin a pilot's sources, and therefore change that Application's normal deployment flow to "move the pin by PR"? Without that, the broker is G2 at best.
- G0 residual: v3.3.8 `Sync` reads the Application, builds the operation, then calls `SetAppOperation`. Do non-revision spec fields (path, helm parameters) changed by a concurrent root-app sync reach the controller with the old revisions? This is `unknown` until T103.
- mctl-api owner: is a dedicated `release.freeze_exception` kind acceptable, with terminal states `executed | spent_failed | spent_unknown` and the `release_exception_ops` row in the same transaction as the CAS? The generic reserve/settle returns a failed call to `consumed` (mctl-api#772). Mapped to mctl-api#1022.
- Broker placement (separate Deployment as the default candidate, or inside mctl-api) and Argo identity (project-role JWT with TTL, or local account). Who mints and rotates a short-lived project-role token, given that minting needs `projects, update` on the pilot project?
- Activation observability: mctl-api's Argo account has `applications, get` only (`argocd/values.yaml:53` and the RBAC block), so it can call `GetApplicationSyncWindows`. Whether reading the live `AppProject.spec` needs `projects, get` (which no non-admin account has) is `unknown`. `activation_lead` and `max_read_age` are placeholders until task 3 measures reconcile latency.
- Tenant UX: removing the owning tenant's manual sync on a pilot Application is permanent, not window-bound, unless a further RBAC lifecycle is added. Who is the pilot Application and tenant?
- Live state is `unknown`: the running Argo CD version, the live `argocd-cm` (including `requireOverridePrivilegeForRevisionSync`), live RBAC, any live `syncWindows` and project roles. `mctl_whoami` is non-admin with no teams. `mctl_get_service_status admins/mctl-api` returned "not found", which means no access, not absence.
- Do tenant resource actions (`Deployment/restart`) bypass sync windows? Not verified; the harness tests it (T93).
- Ruleset 18465404 `bypass_actors` is unreadable (`null`), so the DeployKey bypass is `unknown`. CLAUDE.md lists `agy-formal-review` as a queue check that the repository ruleset read does not show (possibly an org ruleset): `unknown`.
- Propagation latency (#970 reported about 7 min) stays stale until measured.
- Should an open critical incident create a deny window automatically? Recommended no: a window is created only through a reviewed PR (R-I1).
- Vendor prices are `unknown`: they are not stated on the primary pages read.
