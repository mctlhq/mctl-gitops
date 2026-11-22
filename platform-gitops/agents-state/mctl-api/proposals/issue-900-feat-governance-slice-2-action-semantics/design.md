# Design: issue-900-feat-governance-slice-2-action-semantics

## Refreshed 2026-11-22

Re-baselined against mctl-api `main` at `80f7a011c975422a6bb632022f5538d59772928f`
(release 4.173.0 merge) and mctl-gitops `main` at
`b63db307c6106e520ab94d70fe1b7420adc6fdca`, both read from git after a fetch.

What changed, and nothing else:

- Current state, `/approve`: rewritten from "decides with `DecideActionApproval`
  from an admin bearer call" to the decide-page-only model in force since
  mctl-api 4.170.0 (PRs #1127 and #1130, 2026-11-18). A bearer or operations
  call no longer decides a DevLoop approval; only the decide page, after a
  fresh sign-in that reports a second factor, does. `DEVLOOP_BEARER_APPROVE_ENABLED`
  is a break-glass and is OFF.
- New section "Relation to the decide page" (cancel, request-changes and defer
  are never `aar_` decisions and must not become a bearer-callable decision
  path).
- Tasks T3-T5 (`tasks.md`) and tests T3-T5 updated to match; section 5 and the
  Platform impact risks gained the matching constraints. Scope, route shape,
  store schema and cancel semantics are unchanged.
- Superseded: any earlier approval of this proposal was bound to the digest of
  the text before this edit. The digest of the three documents changes with this
  refresh, so that earlier digest/grant binding no longer matches and does not
  carry over; a new decision on the new digest is the owner's, through its own
  PR. `.status.yaml` is deliberately untouched here.
- Not re-verified in this refresh: the deployed env values in "Deployed state"
  (`MCTL_AGENTS_APPROVE_LEGACY_APPROVER`, `MCTL_APPROVAL_BINDING`) are carried
  over from the earlier baseline.

## Current state

Routes (`internal/api/router.go`, write group around lines 742-750):

- `POST /api/v1/agents/dev-loop/{workflow_id}/approve` -> `ApproveDevLoopWorkflow`
  (`internal/api/handlers_dev_loop.go`). Gated by `requireTemporalAdmin`, then
  `isHumanAdmin` (refusal `approval_decider_forbidden`). Since 4.170.0 this
  route no longer decides for a bearer caller: `mayDecideDevLoop` is true only
  under `withDecidePage` (the decide page calls the handler in-process) or when
  the break-glass `DEVLOOP_BEARER_APPROVE_ENABLED` is on (OFF in production).
  Any other call that would decide a pending grant, or record a legacy approval
  with no grant, is refused 403 `decide_page_required`, audited as denied
  (`refuseDevLoopBearerDecision`), carrying the grant's `decide_url` when the
  page is enabled. A grant already approved on the page is still re-sent as its
  `approval_ref`: that call decides nothing and only re-delivers a lost signal.
  When it does decide (page or break-glass), `decideDevLoopApproval` resolves
  the workflow to its one open `we_` execution via
  `WorkItems.OpenExecutionsOfEngineRun(EngineTemporal, workflowID)`, reads the
  newest `mctl-agents-approve` grant via `WorkItems.ActionApprovals`, applies
  the Slice 1 binding (`bindingGate`, `bindingMatches`, 409
  `approval_context_changed` with `current_approval_ref`) and decides a pending
  grant with `DecideActionApproval`. Closed states map through
  `closedApprovalCodes`.
- The generic `POST /api/v1/action-approvals/{id}/decision`
  (`DecideActionApproval`, `handlers_action_approvals.go`) refuses an
  `approve` of a pending `mctl-agents-approve` grant the same way (403
  `decide_page_required`) unless `mayDecideDevLoop`. A `deny` stays open: the
  decide page's Reject is a `deny` through this handler, and refusing a DevLoop
  needs no proof of a person. A direct `mctl-agents-approve` operation is
  likewise refused without the page (`mayDirectApproveProposal`, #1130).
- The decide page (`internal/api/handlers_devloop_decide.go`, mctl-api#964,
  `/devloop/decide/{workflow_id}`): public routes; the person signs in to the
  identity provider fresh (`prompt=login`, `max_age=0`), the ID token's `amr`
  must contain `mfa`, only a human admin is offered a decision, and the link's
  binding must match the grant's current context. Its only two decisions are
  Approve (in-process `ApproveDevLoopWorkflow`) and Reject (`deny`). It offers
  no cancel, request-changes or defer. Covered by
  `handlers_devloop_decide_test.go`, `handlers_approval_grant_decide_page_test.go`
  and the bearer-refusal cases in `handlers_dev_loop_test.go`.
- `POST /api/v1/agents/dev-loop/{workflow_id}/abandon` -> `AbandonDevLoopWorkflow`.
  Gated by `requireTemporalAdmin` only (any admin, including the service
  principal). Body `{"reason": <free text, required>}` with
  `DisallowUnknownFields` and `refuseIdentityFields`. Describes the execution
  (`DescribeDevLoopExecution`), answers `already_finished` for a non-running
  run, otherwise `SignalAbandon(workflowID, runID, payload)` pinned to the
  described run; a NotFound is re-described and a new run is a 409. Outcomes
  `signalled` / `already_finished`. No idempotency key, no durable record
  other than the audit entry, and the free-text reason goes into the audit
  parameters and the signal payload.
- `POST /api/v1/human-input/{request_id}/response` -> `RespondHumanInput`
  (`handlers_human_input_response.go`), backed by the `humaninput.Ledger`;
  only `SignalHumanInputResponse` is called. The separation from `aar_` is
  proven by `internal/api/human_input_vs_action_approval_test.go`, which
  wraps the ledger in `recordingLedger`.

Supporting pieces:

- `isHumanAdmin` / `isDirectService` in `internal/api/handlers_action_approvals.go`;
  typed codes `aarCode*` and `actionApprovalRefusals` there.
- `internal/api/approval_binding.go`: `decisionBinding`, `missingFields`,
  `bindingGate(route, id, b)` with routes `action_approval` and `dev_loop`,
  `MCTL_APPROVAL_BINDING` off/observe/enforce.
- `internal/temporalclient/client.go`: `AbandonedEndedPrefix = "abandoned: "`,
  `DevLoopEnded` -> `DevLoopRunEnd{Ended, Implemented}`; `restartIfAbandoned`
  in `handlers_dev_loop.go` already uses these to tell a pre-implement abandon
  from a post-implement one.
- `internal/workitems`: Postgres store with `CREATE TABLE IF NOT EXISTS`
  schemas per file (`action_approvals.go`, `execution_requests.go`), idempotency
  per `(requested_by, idempotency_key)`, advisory-lock transactions via
  `withTx`. `Options.WorkItems` is the concrete `*workitems.Store`.
- `internal/decisions` is the policy-decision record for `aar_`-authorized
  actions; it is not a fit for non-decisions (see Alternatives).
- `docs/decision-context-contract.md` documents Slice 1 binding and the
  privacy rule (references, digests, enums and reason codes only).
- `internal/openapi/openapi.yaml` and `embed_test.go` list every route.

Nothing in the repo models request-changes, defer or owner cancel today
(searched for `request_changes`, `cancellation_`, owner actions).

Deployed state (observed in mctl-gitops main,
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`, the ArgoCD
Application that carries mctl-api's env; mctl-api is not a tenant service, so
`services/*/` and `mctl_get_service_config` do not show it):

- `MCTL_AGENTS_APPROVE_LEGACY_APPROVER: "false"` is set.
- `MCTL_APPROVAL_BINDING` is absent. `ParseApprovalBindingMode` reads empty
  as `observe`, so production runs in observe mode today.
- That is evidence of the current mode, not a reason to relax enforce: every
  rule below is specified and tested for both observe and enforce.

## Proposed solution

### 1. Route and body

`POST /api/v1/agents/dev-loop/{workflow_id}/owner-actions` in the same write
group as `/abandon` (same rate-limit bucket), plus reads
`GET /api/v1/agents/dev-loop/{workflow_id}/owner-actions` and
`GET /api/v1/agents/dev-loop/{workflow_id}/owner-actions/{id}` beside
`GetDevLoopWorkflow`.

```json
{
  "action": "request_changes | defer | request_cancel",
  "idempotency_key": "<= 128 bytes, required",
  "binding": {"approval_ref": "aar_...", "context_digest": "...", "content_digest": "..."},
  "expected_run_id": "optional, request_cancel only: the Temporal run the card was rendered for",
  "reason_code": "optional, ^[a-z0-9._:-]{1,64}$"
}
```

`expected_run_id` on `request_changes` or `defer` is refused with 400, like
any other key that does not belong to the action.

Decoded with `refuseIdentityFields` and `DisallowUnknownFields`; no free text.

### 1a. Relation to the decide page

Approving a DevLoop is decided on the decide page only; this slice must not
reopen a bearer path to that decision.

- `request_changes`, `defer` and `request_cancel` are never `aar_` decisions.
  None of them calls `DecideActionApproval`, `ApproveDevLoopWorkflow` or the
  decide page's approve, and none sets `approved_by`/`decided_by` or moves a
  grant to a decided state. They are owner-triage records and one abandon
  signal, nothing more.
- They must not become a bearer-callable owner decision path. A bearer token is
  also held by AI clients, so a call that carries only a token cannot prove a
  person acted. The owner-action route therefore never approves, and its
  `request_cancel` is the only action that has an effect on the run: it ends a
  run (never implements one) through the one abandon signal path, is
  idempotent, and is refused for relayed, surface and service callers. A
  cancel can only stop work, never start or authorize it, which is why it does
  not need the decide page's second factor; a future action that would
  authorize work (approve, or anything that spends a grant) belongs on the
  decide page and in no case on this route.
- The route never returns `decide_url` as a way to act, and its refusals never
  suggest approving by bearer. When a card needs the person to approve, it
  hands them `decide_url` from `GET /api/v1/agents/dev-loop/{workflow_id}/approval`
  and does not open it on their behalf.
- Reject on the decide page stays a `deny` of the grant and is not an owner
  action. `request_changes` is deliberately not a deny: the grant stays
  `pending`.
- The observe-mode `bindingGate` audit and the `decide_page_required` refusal
  are independent: setting `DEVLOOP_BEARER_APPROVE_ENABLED` changes nothing on
  this route, and a test pins that.

### 2. Authority

New file `internal/api/handlers_dev_loop_owner_actions.go`. The handler calls
`requireTemporalAdmin`, then `isHumanAdmin(user)`; a failure is 403
`owner_action_forbidden` with an audit entry `dev-loop-owner-action`
status `denied`. No auth helper is modified. The existing `/abandon` route
keeps its current authorization unchanged.

### 3. Grant resolution and stale-card binding

Extract from `decideDevLoopApproval` a read-only helper
`resolveDevLoopGrant(ctx, workflowID) (exec *workitems.Execution, newest *workitems.ActionApprovalRequest, err)`
(the `OpenExecutionsOfEngineRun` + `ActionApprovals(Limit:1)` part, including
`execution_ambiguous` and 503 `wiCodeUnavailable` handling).
`decideDevLoopApproval` is rewritten to call it, behaviour unchanged.

Add `bindingRouteDevLoopOwnerAction = "dev_loop_owner_action"` and call
`bindingGate` with it. If a binding is present: newest grant missing -> 409
`approval_grant_missing`; `binding.ApprovalRef != newest.ID` -> 409
`approval_context_changed` with `current_approval_ref`; digests compared with
`bindingMatches` against the grant's current context digest (the same digest
`guardDecision` computes for pending grants, `DecidedContextDigest` for
decided ones) -> 409 `approval_context_changed`. All refusals happen before
any write or signal.

When `bindingGate` is consulted depends on the action and on whether a grant
exists:

| action | grant exists | binding absent, enforce | binding absent, observe |
| --- | --- | --- | --- |
| `request_changes`, `defer` | yes | 422 `approval_binding_missing` | accepted, audited `approval.binding_absent` |
| `request_changes`, `defer` | no | 409 `approval_grant_missing` | 409 `approval_grant_missing` |
| `request_cancel` | yes | 422 `approval_binding_missing` | accepted, audited `approval.binding_absent` |
| `request_cancel` | no | accepted, run-bound (below) | accepted, run-bound (below) |

So for a pre-grant `request_cancel` the handler resolves the grant first and,
finding none, skips `bindingGate` entirely rather than letting it answer 422.
The `isHumanAdmin` check runs before this resolution, so the exception never
reaches a caller who is not a direct human admin. No other action gets the
exception.

Run binding for `request_cancel` (always, grant or not): the body may carry
`expected_run_id`, the run the card was rendered for. The handler describes
the execution; if `expected_run_id` is set and differs from the described
`run_id` it answers 409 `cancellation_run_changed` before any write or signal.
The described `run_id` is stored on the row and is the only run the abandon
signal is ever pinned to (step 5).

### 4. Owner-action store

New file `internal/workitems/owner_actions.go`, schema added alongside the
others:

```sql
CREATE TABLE IF NOT EXISTS dev_loop_owner_actions (
  id               TEXT PRIMARY KEY,               -- oa_<random>
  workflow_id      TEXT NOT NULL,
  run_id           TEXT NOT NULL DEFAULT '',
  execution_id     TEXT NOT NULL DEFAULT '',       -- we_
  approval_ref     TEXT NOT NULL DEFAULT '',       -- aar_ observed, never decided
  action           TEXT NOT NULL CHECK (action IN ('request_changes','defer','request_cancel')),
  reason_code      TEXT NOT NULL DEFAULT '',
  requested_by     TEXT NOT NULL,
  principal_id     TEXT NOT NULL DEFAULT '',
  idempotency_key  TEXT NOT NULL,
  content_digest   TEXT NOT NULL,                  -- sha256 of canonical request
  state            TEXT NOT NULL CHECK (state IN ('requested','recorded','signalled','finished')),
  outcome          TEXT NOT NULL DEFAULT '',
  created_at       TIMESTAMPTZ NOT NULL,
  updated_at       TIMESTAMPTZ NOT NULL,
  schema_version   TEXT NOT NULL,
  UNIQUE (requested_by, idempotency_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS dev_loop_owner_actions_one_cancel_per_run
  ON dev_loop_owner_actions (workflow_id, run_id) WHERE action = 'request_cancel';
CREATE UNIQUE INDEX IF NOT EXISTS dev_loop_owner_actions_one_per_grant
  ON dev_loop_owner_actions (approval_ref, action)
  WHERE action IN ('request_changes','defer');
```

API: `CreateOwnerAction(ctx, in) (*OwnerAction, replayed bool, err)` under
`withTx` with an advisory lock on `owner-action:<workflow_id>`; returns the
existing row for the same key+digest, `ErrOwnerActionIdempotencyConflict` for
the same key with a different digest, and the existing row (`replayed=true`)
when a unique index already holds a cancel for the run or an action of that
kind for the grant. `MarkOwnerActionOutcome(ctx, id, fromState, toState, outcome)`
is compare-and-set on `state`. `GetOwnerAction`, `ListOwnerActions(workflowID)`.
The store holds no free text; `content_digest` covers action, workflow id,
binding fields and reason code.

### 5. Action semantics

`request_changes` / `defer`:
- newest grant must exist (`approval_grant_missing`) and be `pending`
  (otherwise `approval_already_decided` for approved, `closedApprovalCodes`
  for the rest);
- create the row in state `recorded`, outcome `changes_requested` or
  `deferred`; no Temporal call, no `DecideActionApproval`;
- respond 200 `{id, workflow_id, action, approval_ref, state, outcome, replayed}`.

`request_cancel`:
1. Extract the body of `AbandonDevLoopWorkflow` after body parsing into
   `h.abandonDevLoopRun(ctx, workflowID, payload) abandonResult` returning
   `{outcome: signalled|already_finished|run_changed|not_found|failed, exec, after, err}`
   and leaving response writing to the caller. `AbandonDevLoopWorkflow` keeps
   its exact responses and audit using it.
2. Owner path: resolve the grant (absent is allowed here, see section 3),
   describe the run and apply the `expected_run_id` check, then create the
   row in state `requested` with the described `run_id` (describe first so
   the per-run unique index applies). `approval_ref` on the row is the
   observed grant id, or empty when no grant exists. A replayed row in
   state `signalled` or `finished` is returned as is, without a signal. A
   replayed row in `requested` retries the signal to the stored `run_id`.
3. Signal payload: `{"reason": "owner_action:<oa_id>:<reason_code>", "abandoned_by": user.ID}`
   (no free text).
4. Outcome mapping (`ownerCancelOutcome`):
   - signalled, grant pending or absent -> state `signalled`, `cancellation_pending`;
   - signalled, grant approved / in_flight / consumed / executed -> state
     `signalled`, `cancellation_effects_unknown`;
   - already finished: `DevLoopEnded(run)`; `Ended` starts with
     `AbandonedEndedPrefix` and `!Implemented` -> `finished`, `cancelled`;
     abandoned and `Implemented` -> `finished`, `cancellation_effects_unknown`;
     not abandoned -> `finished`, `already_finished`; unreadable result ->
     `finished`, `cancellation_effects_unknown` (never guessed as stopped);
   - run changed -> 409 `cancellation_run_changed`, row stays `requested`
     with outcome empty, so a replay with the same key retries against the
     stored run and answers `already_finished`/`cancelled` for it, never the
     new run;
   - signal transport error -> 502 (503 for `ErrUnavailable`), row stays
     `requested`.
5. `GET .../owner-actions/{id}` for a `signalled` cancel re-describes the run
   and, if it has finished, applies the same mapping and persists it with
   `MarkOwnerActionOutcome(signalled -> finished)`. It never signals.

### 6. Audit and response

Audit operation `dev-loop-owner-action` with parameters `owner_action_id`,
`action`, `workflow_id`, `run_id`, `execution_id`, `approval_ref`,
`reason_code`, `outcome`, `replayed`. No grant decision audit
(`action_approval.decision`) is ever written on this path. Responses carry
the same fields plus `state`.

### 7. Documentation

Add an "Owner actions (mctl-api#900)" section to
`docs/decision-context-contract.md`: approve/deny are the only `aar_`
decisions; the three owner actions, their codes, cancel outcome table, and
that cancel is not rollback. It also states:

- the binding table of section 3, including that a pre-grant cancel is
  run-bound and needs no `aar_` binding in either mode;
- the grant after cancellation: cancel does not approve, deny, consume,
  expire or supersede an `aar_`, and this slice adds no grant terminal state,
  so a grant may stay `pending` until `expires_at` after its DevLoop was
  cancelled or finished;
- for owner-triage consumers (mctlhq/mctl-agents#907): do not present an
  actionable Approve control solely because such a grant is still pending
  when the bound DevLoop run is terminal or has a recorded owner cancel.

Add the three routes to `internal/openapi/openapi.yaml` and `embed_test.go`.

## Alternatives

- Model request-changes/defer as `aar_` decisions (new `DecisionRequestChanges`
  in `workitems`). Dropped: the issue forbids parallel approval semantics, and
  every consumer of `aar_` state would have to learn that some "decisions"
  decide nothing.
- Record owner actions in `internal/decisions`. Dropped: a decision row is a
  policy verdict with `Permitted` and attempts, bound to an `aar_` that
  authorizes it; a defer has no verdict, and reusing it would make
  "permitted" ambiguous.
- Wire request-cancel to the existing `/abandon` route from the card
  renderer directly. Dropped: that route admits the service principal, takes
  free text, has no idempotency key and reports only `signalled`, so it
  cannot give `cancellation_pending` / `cancellation_effects_unknown` or
  stale-card protection. Tightening it in place would break existing operator
  callers; sharing its core keeps one signal path.
- Deliver cancel as a human-input answer. Dropped: explicitly forbidden;
  human input is information only.

## Platform impact

- Migration: one additive table and two partial unique indexes created with
  `CREATE TABLE/INDEX IF NOT EXISTS` at store start, like the other workitems
  tables. No change to existing tables.
- Backward compatibility: `/approve`, `/abandon` and human-input responses
  keep their responses, audit and authorization; the refactors
  (`resolveDevLoopGrant`, `abandonDevLoopRun`) are covered by the existing
  `handlers_dev_loop_test.go` and `handlers_dev_loop_abandon_test.go`.
- Resources: one Postgres row per owner action; at most two Temporal calls
  (describe, signal) plus one `DevLoopEnded` read per cancel.
- Risks:
  - The grant state is a proxy for "implement may have started". Mitigation:
    any non-pending grant yields `cancellation_effects_unknown`, never a
    stopped claim.
  - Partial unique index on `(workflow_id, run_id)` requires the run id
    before insert; mitigated by describing first and storing the described
    run.
  - Replays after `run_changed` must not cancel a successor run; mitigated by
    always signalling the stored `run_id`.
  - Relayed humans cannot use these controls; the Telegram renderer must
    deep-link to a direct session. Recorded as an open question.
  - A later change could be tempted to let `request_changes`/`defer` or an
    "approve" action ride on this bearer-callable route. Mitigation: section 1a
    and tests T3/T5 pin that no owner action decides an `aar_`, with and
    without `DEVLOOP_BEARER_APPROVE_ENABLED`.
