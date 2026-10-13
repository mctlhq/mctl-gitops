# Design: issue-571 — DevLoop approvals through a bound `aar_`

Narrows `issue-376-…/design.md` §5 to `main` at `548a541`. Everything is
additive except the two tightenings in §5.

## 0. Issue → work item → `we_` (R0a-R0d, D6)

- mctl-api: `ListWorkItems` gains the `surface` + `external_id` filter,
  joined on `work_item_surface_refs`, under the existing tenant scoping. A
  store error is a 503, never an empty list.
- Worker (mctl-agents#636), at DevLoop start, before anything else:
  1. lookup by `github` surface ref; exactly one hit → reuse; more than one
     → hard failure (ambiguous, needs a human);
  2. none → `POST /api/v1/work-items` with idempotency key
     `devloop:github:<owner>/<repo>#<number>` and the tenant that owns the
     target service (an explicit service→tenant mapping in the worker; an
     unmapped service is a hard failure, never a default tenant), then link
     the `github` surface ref;
  3. attach the execution `(temporal, <workflow_id>)` → `we_`.
  The same issue always lands on the same work item, and the same
  workflow id on the same `we_`. Steps 2-3 are retry-safe because both
  routes are idempotent.

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
  lookup `ExecutionByEngineRef(ctx, "temporal", workflowID)`; then the
  newest pending `aar_` with that `execution_id` and kind; decide it with
  the existing store `DecideActionApproval` (same self-decision and
  human-admin rules); signal `{approval_ref}`. No `we_` or no pending `aar_`
  → legacy payload `{approver}` while the flag is on, 409 when off (R3).
  `requireTemporalAdmin` becomes `isHumanAdmin` (R4).
- No new column: the workflow id lives on the execution row as
  `engine_ref`; the `aar_` keeps only the `we_`.

## 2. Grant-authorized `mctl-agents-approve` (R5-R8, D1, D2)

- `delegationRoutes` gains `{POST, ^/api/v1/operations/mctl-agents-approve/execute$}`
  and nothing else.
- In `ExecuteOperation` (`handlers_write.go`), before the admin/tenant-role
  checks: if `opName == "mctl-agents-approve"` and the context carries a
  delegation grant of kind `action_approval` (`delegationGrantFrom`, Slice
  D), take the grant path:
  1. load the `aar_`; require `action_kind` and `target ==
     service+"/"+slug`;
  2. refuse a body `approver` (R8);
  3. compute `IntentHash` from the actual input and call the store
     `ConsumeActionApproval` (CAS: approved, intent match, not expired,
     single use);
  4. set `input["approver"]` and the approver principal from the consumed
     row, submit, audit `operation.execute` with `actor_kind=agent`,
     `actor_name`, `agent_run_id`, `subject_principal_id`, `grant_ref`.
  Any other caller falls through to today's checks unchanged (R7). The
  admin gate is not weakened: the only authority is a human-admin decision
  made under `isHumanAdmin`, bound to this run and this intent, spent once.
- Binding is the gate's existing `we_`/work-item check; the handler adds the
  intent check. Both are server-side; nothing comes from the caller.

## 3. Subject from `prn_` (R9, D5)

`agentPrincipalGate` replaces the `github:` cut
(`handlers_agent_identity.go:190-195`) with a principal lookup by
`grant.SubjectPrincipalID`: the delegated user is built from the principal's
canonical identity (any IdP), then `AttachPrincipal` and the existing
`PrincipalID() == grant.SubjectPrincipalID` check. Empty id →
`grant_subject_unresolved`; store error → 503. In legacy tenant mode a
non-GitHub subject gets no login-derived groups; that is correct, and
grant-authorized approval (§2) needs none.

## 4. Legacy flag (R11-R13)

`MCTL_AGENTS_APPROVE_LEGACY_APPROVER` (default `true`) wraps the existing
service relay block (`handlers_write.go:225-252`): on → relay plus one
`approver.legacy_relay` audit entry; off → 400 `legacy_approver_disabled`,
audited. Helm and README gain the variable.

## 5. Tightenings

- `requireTemporalAdmin` → `isHumanAdmin`: verify before release that no
  automation calls the dev-loop approve/abandon routes with the service
  token (audit query over 14 days).
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
- A DevLoop that cannot obtain a `we_`: stops before the approval gate (R0d); a lookup outage is a failed start, not a duplicate work item.
- Principal-store outage: delegated approvals fail closed (503) while the
  legacy relay, while on, still works.
