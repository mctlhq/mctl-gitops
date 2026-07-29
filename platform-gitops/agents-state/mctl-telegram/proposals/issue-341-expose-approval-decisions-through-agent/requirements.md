# Expose approval decisions through agent API and audit model

## Context

The Communication Agent's human-approval flow exists today as a Postgres/SQLite
state machine (`agent_actions.status`: `proposed -> pending_approval -> approved
-> executing -> executed|rejected|expired|denied`, `internal/db/agent_actions.go`)
decided exclusively through Telegram Saved Messages commands
(`/mctl approve|reject <code>`, parsed by `internal/agent/control.ParseCommand`
and routed by `internal/agent/control.Router`). There is no HTTP surface a UI
client or any caller other than the owner's own Telegram client can use to
list pending approvals or submit a decision, no `edit`/`cancel` decision at
all, and no revision-aware conflict handling beyond the current-status CAS in
`Store.UpdateAgentActionStatus`.

Issue #341 is the third piece of epic #339 ("Add Temporal-backed human
approval flow for Communication Agent"): #340 (dependency, also open) defines
a Temporal workflow (`CommunicationApprovalWorkflow`) and a versioned decision
Signal that will become the new durable owner of an approval's lifecycle.
#341's job is the safe, tenant-scoped HTTP surface and audit model in front of
that workflow: authenticate and authorize the caller, validate the decision
against server-known state, submit the Temporal Signal, and persist a
product-facing audit trail that does not depend on Temporal history being
queried directly. This matters because today the only "audit" for a decision
is the terminal `agent_actions` row and the redacted `slog` line the
executor/router emit — there is no durable, queryable, per-transition record
suitable for support/compliance/UI use, and no caller-facing API at all for a
capability (list + decide) the product needs regardless of which orchestration
engine sits behind it.

## User stories

- AS an account owner I WANT to see my pending Communication Agent approvals
  through an API (not only by reading Saved Messages) SO THAT a web/mobile UI
  can present them.
- AS an account owner I WANT to approve, reject, edit, or cancel a proposed
  action through that same API SO THAT I am not limited to typing `/mctl
  approve <code>` into Saved Messages.
- AS an account owner I WANT a duplicate submission of the same decision to be
  a no-op that returns the original result SO THAT a flaky network retry from
  my client cannot double-execute or double-reject an action.
- AS an account owner I WANT a decision against a stale version of the
  proposal to be rejected with a conflict SO THAT I never approve something
  different from what I actually looked at.
- AS a platform operator I WANT every read and decision on an approval
  recorded in a tenant-scoped audit model SO THAT support and compliance do
  not have to reconstruct history from Temporal's internal event history.
- AS a platform operator I WANT the API to keep working (reads return correct
  state, decisions are accepted or correctly conflict) when the Temporal
  worker is temporarily down SO THAT a worker outage does not silently corrupt
  or lose owner decisions.
- AS a security reviewer I WANT the API to never execute the Telegram action
  itself SO THAT the boundary from #339 ("Claude never touches MTProto
  directly") is preserved end to end, including this new surface.

## Acceptance criteria (EARS)

- WHEN an authenticated caller requests `GET /v1/approvals/{approval_id}` THE
  SYSTEM SHALL return the approval only if it resolves to that caller's own
  `user_id`-scoped tenant/account boundary, otherwise return 404 (not 403, to
  avoid confirming existence across tenants).
- WHEN an authenticated caller requests `GET /v1/approvals?status=pending` THE
  SYSTEM SHALL return only approvals belonging to that caller's `user_id`.
- WHEN a caller submits `POST /v1/approvals/{approval_id}/decision` THE SYSTEM
  SHALL resolve `tenant_id`/`user_id`/actor identity from the authenticated
  session context, never from request body fields, before evaluating the
  decision.
- IF the resolved caller does not own the `account_id`/`agent_profile_id`
  behind the approval THEN THE SYSTEM SHALL reject the request with 404
  without signalling Temporal.
- WHEN a decision request's `expected_revision` does not match the approval's
  current `approval_revision` THE SYSTEM SHALL return 409 Conflict and SHALL
  NOT send a Temporal Signal.
- WHEN a decision request's `request_id` matches a previously accepted
  request for the same approval THE SYSTEM SHALL return the original
  recorded result without re-signalling Temporal.
- WHEN `decision` is `edit` THE SYSTEM SHALL validate `edited_payload` against
  the action type's schema, rejecting any field not defined by that schema,
  before signalling Temporal.
- IF an approval is already in a terminal state (`approved`/executed,
  `rejected`, `cancelled`, `expired`, `denied`) THEN THE SYSTEM SHALL return
  that terminal state and SHALL NOT accept a further decision or reopen it.
- WHEN a decision is accepted for signalling THE SYSTEM SHALL respond
  distinguishing `decision_accepted` from `executing`/`completed`/`failed`,
  and SHALL NOT imply the underlying Telegram send already happened.
- WHILE the Temporal worker/frontend is unreachable THE SYSTEM SHALL still
  serve reads from its own durable projection and SHALL return a clear,
  retryable error (not a silent 200) for decisions it cannot durably hand off.
- WHEN any read (`GET /v1/approvals/{id}`, `GET /v1/approvals`) or decision
  submission occurs THE SYSTEM SHALL persist a correlated audit event
  (`workflow_id`, `workflow_run_id` when known, `approval_id`,
  `approval_revision`, `operation_id`, `tenant_id`/`user_id`, `account_id`,
  actor, `request_id`, policy version, proposal hash) independent of Temporal
  history.
- WHEN a repeated decision attempt on the same approval exceeds the
  configured rate SHALL THE SYSTEM reject it with 429 before evaluating
  business logic.
- IF the caller lacks the required capability/role for decisioning approvals
  on the target account THEN THE SYSTEM SHALL reject with 403.
- WHILE this feature is rolled out THE SYSTEM SHALL gate the entire
  `/v1/approvals` surface behind the same feature flag family as #339
  (`AGENT_ENABLED`-style), defaulting closed, enabled first for a single test
  tenant/account.
- WHEN #340's Temporal workflow is not yet deployed for a given
  action/approval THE SYSTEM SHALL continue to serve that approval through
  the existing `agent_actions` state machine so in-flight approvals are not
  broken mid-migration.

## Out of scope

- Implementing the Temporal workflow itself, its Signal handler, Query
  handler, or Activities — that is #340. This proposal defines the contract
  #341's server needs from #340 (workflow/approval IDs, the versioned Signal
  JSON, a Query for status) and integrates against it through a narrow
  interface so #341 can be built and tested before #340 merges.
- Removing or replacing the existing Saved Messages `/mctl approve|reject`
  control-plane commands. Both surfaces must be able to decide the same
  approval consistently during migration (issue's explicit rollout
  requirement).
- A UI/frontend client.
- Deleting or migrating away from `agent_jobs`/the current durable queue
  (explicit non-goal of #339).
- Introducing real multi-account-per-tenant data modeling. Today
  `agent_profiles`/`agent_actions` are keyed 1:1 by `user_id`; this proposal
  treats `tenant_id == account_id == agent_profile_id == user_id` for the
  current single-account-per-user model (see design.md) and adds columns
  that allow a future real tenant/account split without another migration,
  without implementing that split now.
- Introducing `policy_version`/`proposal_hash` computation in
  `internal/agent/policy` — that is #340's workflow-input contract; #341
  only stores whatever values the workflow/API layer is given at decision
  time.
- Rate-limit and capability/role infrastructure beyond what
  `internal/audit.RateLimiter` and `auth.Identity.Scopes` already provide;
  this proposal wires them onto the new endpoints, it does not redesign them.

## Open questions

- #340 is itself unimplemented (open issue, no Temporal SDK dependency in
  `go.mod` today). This proposal assumes #340 will land with the identifiers
  and Signal envelope exactly as specified in its issue body
  (`workflow_id = communication:{tenant_id}:{account_id}:{operation_id}`,
  `approval_id = {workflow_id}:{approval_revision}`). If #340 changes that
  contract before merge, #341's `TemporalSignaler`/`ApprovalReader`
  interfaces (design.md) isolate the blast radius to their implementations.
  Proceeding on this assumption rather than blocking.
- The issue's suggested surface uses `tenant_id`/`account_id` as distinct
  concepts; the current schema has neither column, only `user_id`. Resolved
  by aliasing all three to `user_id` for now (see design.md Platform impact)
  and recording the alias explicitly rather than guessing a real multi-tenant
  shape that doesn't exist in the codebase yet.
- Capability/role model: `auth.Identity.Scopes`/`Groups` exist
  (`internal/auth/identity.go`) but no scope currently gates "may decide
  approvals for account X" specifically (existing scopes are coarse,
  auth-provider-defined). Proposing a new scope
  (`agent:approvals:decide`) minted the same way existing scopes are, without
  redesigning the scope system. Flagging as an assumption, not blocking.
- Whether `GET /v1/approvals` needs cursor pagination beyond `status`
  filtering is unspecified in the issue. Proposing simple `status` +
  `limit`/`before_id` cursor pagination consistent with existing list
  endpoints' style, not full-text search or sort options.
- The issue does not say whether `cancel` is owner-only or also
  system/policy-initiated (e.g. conversation deleted). Proposing owner- and
  admin-initiated only for this proposal's scope; system-initiated
  cancellation (e.g. from a takeover) is left to #340's workflow logic to
  signal itself, not this API.
