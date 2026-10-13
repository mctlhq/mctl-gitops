# Design: issue-571 — DevLoop approvals through a bound `aar_`

Narrows `issue-376-…/design.md` §5 to `main` at `548a541`. Everything is
additive except the two tightenings in §5.

## 0. Issue → work item → `we_` (R0a-R0d, D6)

- No new mctl-api route. The issue's work item is the open work item whose
  `external_key` is the canonical issue URL
  `https://github.com/<owner>/<repo>/issues/<number>` — the shape
  `internal/evidence/derive.go` and mctl-agents' `work_context/contract.py`
  already read as "the issue". `Store.Create` dedupes open work on
  `(tenant, external_key)` (partial unique index
  `work_items_tenant_external_key_open`), so creating is also resolving.
- Worker (mctl-agents#636), at DevLoop start, before anything else:
  0. a DevLoop dispatched from an execution request (mctl-agents#461:
     `IssueRef` carries `work_item_id` + `execution_request_id`) already has
     its `we_`: the execution the dispatcher fulfilled the request with,
     `engine_ref = <workflow_id>#<request_id>` (`request_engine_ref`). It
     uses that `we_` (after a resume delivery, the one of the request being
     served) and skips steps 1-2: creating or attaching another would hit
     the one-open-execution-per-item index or split the run in two;
  1. otherwise (issue trigger, cron): `POST /api/v1/work-items` with
     `external_key` = the canonical issue URL, idempotency key
     `devloop:github:<owner>/<repo>#<number>` and the tenant that owns the
     target service (an explicit service→tenant mapping in the worker; an
     unmapped service is a hard failure, never a default tenant). `201` =
     created, `200` = the existing open item (replay or `external_key`
     dedupe); `409 external_key_in_use` (open work the worker cannot see)
     or any other error is a hard failure, never a retry with a different
     key;
  2. attach the execution `(temporal, <workflow_id>)` → `we_`.
  The same issue always lands on the same open work item, and the same
  workflow id on the same `we_`. Both steps are retry-safe because both
  routes are idempotent. An issue whose earlier work item is already
  terminal gets a new one: a closed item is history, not open work.
- Canonical issue URL: `https://github.com/<owner>/<repo>/issues/<number>`
  with `<owner>/<repo>` lowercased and `<number>` in decimal without
  leading zeros, built from the same parse that names the workflow
  (`dev-loop-<owner>-<repo>-<number>`). mctl-api compares `external_key`
  byte for byte, so `Mctlhq/…` or `/issues/0571` would otherwise open a
  second work item for the same issue. A URL that does not parse stops the
  run.

## 1. DevLoop `aar_` keyed by `we_` (R1-R3, D3)

- Worker (mctl-agents#636): at the approval gate it already knows its `we_`
  (`orchestrator/work_context/executions.py`, idempotent attach). It
  creates the `aar_` with that `we_` through the existing
  `POST /api/v1/action-approvals` (static service token, D4) and mints its
  run token for the same `we_`.
- `CreateActionApproval`: for `action_kind == "mctl-agents-approve"` the
  `execution_id` must parse as `we_` and load as a non-terminal execution
  (R2). Other kinds are unchanged.
- `ApproveDevLoopWorkflow` (`handlers_dev_loop.go:309-360`): new store
  lookup of the run's open `we_`: the non-terminal `temporal` executions
  whose `engine_ref` is the workflow id or starts with `<workflow_id>#`
  (the dispatched form, §0 step 0). Exactly one → that `we_`; none → no
  grant; more than one → 409 `execution_ambiguous`, never a pick. Then read
  the newest `aar_` with that `execution_id` and kind, in any state, once,
  and branch on its state: pending → decide it with the existing store
  `DecideActionApproval` (same self-decision and human-admin rules) and
  signal `{approval_ref}`; approved, unconsumed → re-signal it; denied,
  consumed or expired → that state's 409, never the legacy payload. An
  older live `aar_` never outranks a newer recorded decision. No `we_`, or a `we_` that never
  had an `aar_` of this kind → legacy payload `{approver}` while the flag
  is on, 409 when off. Any store read error → 503 (R3).
  The approve route additionally requires `isHumanAdmin` (R4);
  `requireTemporalAdmin` stays as it is for the other dev-loop routes.
- No new column: the workflow id lives on the execution row as
  `engine_ref`; the `aar_` keeps only the `we_`.

## 2. Grant-authorized `mctl-agents-approve` (R5-R8, D1, D2)

- `delegationRoutes` gains `{POST, ^/api/v1/operations/mctl-agents-approve/execute$}`
  and nothing else.
- In `ExecuteOperation` (`handlers_write.go`), before the admin/tenant-role
  checks: if `opName == "mctl-agents-approve"` and the context carries a
  delegation grant of kind `action_approval` (`delegationGrantFrom`, Slice
  D), take the grant path:
  1. refuse a body `approver` (R8); load the `aar_` and set
     `input["approver"]` to its decider's name without the `github:`/
     `oidc:` prefix (the bare name every other path records), before the
     input is defaulted and validated, so it passes the approver's pattern;
  2. on the validated input, bind the target to the execution (R6): the
     request's `<service>/<slug>` must map, through
     `WorkflowIDForProposalRef` (the shepherd's mapping), to the workflow id
     the `we_`'s `engine_ref` names (before any `#<request_id>`), else
     409 `approval_intent_mismatch`. The requester names the target at
     create time, but the human approves a DevLoop, so the target must be
     that DevLoop's proposal;
  3. compute `IntentHash` from the validated input and, after every other
     check, call the store `ConsumeActionApproval` (CAS: approved, intent
     match, not expired, single use);
  4. submit, audit `operation.execute` with `actor_kind=agent`,
     `actor_name`, `agent_run_id`, `subject_principal_id`, `grant_ref`.
     The decision and consume audits carry `target`.
  Any other caller falls through to today's checks unchanged (R7). The
  admin gate is not weakened: the only authority is a human-admin decision
  made under `isHumanAdmin`, bound to this run and this intent, spent once.
- Binding is the gate's existing `we_`/work-item check; the handler adds the
  intent check. Both are server-side; nothing comes from the caller.

## 3. Subject from `prn_` (R9, D5)

`agentPrincipalGate` replaces the `github:` cut
(`handlers_agent_identity.go:190-195`): for an `xr_`/`aar_`/`wi_` grant the
delegated user IS `grant.SubjectPrincipalID`, checked active through the
principal store (`PrincipalChecker`, the check a local token's principal
gets) and never re-resolved from the name, for a human of any IdP. The
subject string must be `github:<login>` or `oidc:<name>` (what
`principalOf` records for a human); its name is kept only so the subject's
`principalOf` reproduces it. Empty id, a non-human namespace, or a
disabled or missing principal → `grant_subject_unresolved`; store error →
503. A `sil_` grant stores no principal and keeps resolving through its
mirrored GitHub identity. In legacy tenant mode a
non-GitHub subject gets no login-derived groups; that is correct, and
grant-authorized approval (§2) needs none.

## 4. Legacy flag (R11-R13)

`MCTL_AGENTS_APPROVE_LEGACY_APPROVER` (default `true`) wraps the existing
service relay block (`handlers_write.go:225-252`): on → relay plus one
`approver.legacy_relay` audit entry; off → 400 `legacy_approver_disabled`,
audited. Helm and README gain the variable.

## 5. Tightenings

- Approve requires `isHumanAdmin`: verify before release that no
  automation calls the dev-loop approve route with the service token
  (audit query over 14 days). Narrowed from all of `requireTemporalAdmin`
  on 2026-10-13: `run_shepherd.py` reads the dev-loop status route with the
  service token, so a global change would break the shepherd sweep.
  Abandon is deliberately left out: it stops a run and grants no
  authority, so it is not part of the approval chain this issue binds; no
  automation calls it today (mctl-agents `main`), and making it human-only
  is its own change if wanted.
- DevLoop `aar_` creation refuses a non-`we_` `execution_id`.

## Rollout

1. mctl-api release, flag on (behaviour-neutral for the current worker).
2. mctl-agents#636 release: run token, `aar_` with `we_`, `approval_ref`,
   `X-MCTL-On-Behalf-Of`, hard failure on typed refusals.
3. Natural DevLoop E2E (A7) with audit evidence.
4. mctl-gitops flips the flag to `false`; one release later the flag is
   removed. Owner-gated.

## Risks

- Grant confusion: bound by `we_` (gate) and intent (CAS); heaviest tests.
- A DevLoop that cannot obtain a `we_`: stops before the approval gate (R0d); a create error (including `external_key_in_use`) is a failed start, not a second work item.
- Principal-store outage: delegated approvals fail closed (503) while the
  legacy relay, while on, still works.
