# CommunicationApprovalWorkflow and Temporal signal contract

## Context

`mctl-telegram` already runs a working, non-Temporal Communication Agent
approval flow: `internal/agent/executor` moves an `agent_actions` row through
`proposed -> pending_approval -> approved -> executing -> executed|denied`
using DB compare-and-swap (`Store.UpdateAgentActionStatus`,
`Store.ReserveAgentActionSend`), a periodic goroutine sweep
(`Executor.RecoverStuck`, `ExpireStaleAgentActions`) for crash recovery and
approval TTL, and a persisted MTProto `send_random_id`
(`Store.BeginExecutingAgentAction`) so a retried send is a safe no-op. The
owner decides via `/mctl approve|reject <code>` in Saved Messages
(`internal/agent/control`), and there is currently no `edit` or `cancel`
decision at all (`internal/agent/control/command.go` only defines `CmdApprove`
and `CmdReject`).

Issue #340 is the second sub-issue of epic #339 ("[Epic] Add Temporal-backed
human approval flow for Communication Agent"). The epic explicitly asks for
Temporal as a *durable orchestration layer for the waiting/decision part of
the flow* — not a replacement for the deterministic policy engine
(`internal/agent/policy`), not a replacement for the existing product audit
log (`audit_logs`, `Store.LogToolCall`, hash-chained), and not a removal of
the existing `agent_jobs`/`agent_actions` queue. It must ship behind a
feature flag, enabled first only for a test tenant/account. #340 itself is
scoped to the workflow, its Activities, and the signal/query contract only;
issue #341 ("Expose approval decisions through agent API and audit model",
`Depends on: #340`) is a separate, later PR that exposes decisions through an
HTTP surface. This proposal treats `mctl-telegram` as introducing Temporal
for the first time — no `go.mod` dependency, no `cmd/*-worker` entrypoint,
and no schema for it exist in the repo today.

This matters because the current approval flow already carries hard-won
crash-safety invariants (persisted `random_id`, atomic budget reservation,
re-check-policy-at-send-time, restricted-field gating, single-use approval
codes) that a new orchestration layer must not silently regress or duplicate
incompatibly. The workflow is new infrastructure layered next to, not instead
of, the current system during the flagged rollout.

## User stories

- AS the Communication Agent policy engine I WANT a durable place to hand off
  a `require_approval` decision SO THAT the process that decides can restart,
  crash, or wait for days without losing state or occupying a worker.
- AS the tenant owner I WANT to approve, reject, edit, or cancel a proposed
  action exactly once per decision SO THAT a duplicate command, a stale
  approval, or a race between two decisions never sends or drops content
  unpredictably.
- AS the platform operator I WANT the Temporal workflow gated behind a
  feature flag and scoped to one test tenant/account SO THAT the existing
  production observe-mode flow (C1/C2, `docs/plans/communication-agent.md`)
  is not put at risk while the new path is proven.
- AS an auditor I WANT every workflow state transition to produce a product
  audit event independent of Temporal history SO THAT audit evidence survives
  a Temporal namespace reset, retention expiry, or a switch away from
  Temporal.
- AS the executor I WANT edited payloads and stale proposals revalidated
  against the current policy/version/kill-switch before any external side
  effect SO THAT an approval decided against an old proposal, an old policy
  version, or a since-revoked capability cannot execute.

## Acceptance criteria (EARS)

- WHEN a policy evaluation for a Temporal-flagged tenant/account returns
  `require_approval` THE SYSTEM SHALL start (or signal-with-start) a
  `CommunicationApprovalWorkflow` keyed by
  `communication:{tenant_id}:{account_id}:{operation_id}` and create a durable
  approval request keyed by `{workflow_id}:{approval_revision}`.
- WHEN the workflow is waiting for a decision THE SYSTEM SHALL consume no
  active worker thread and SHALL survive a worker process restart and a pod
  restart without losing the pending approval.
- WHEN a `DecisionSignal` with `decision=approve` arrives for the current
  `approval_id` and `expected_revision` THE SYSTEM SHALL revalidate the
  proposal and policy/version/ownership/kill-switch state, then execute the
  action through an idempotent Activity exactly once.
- WHEN a `DecisionSignal` with `decision=reject` arrives for the current
  `approval_id` and `expected_revision` THE SYSTEM SHALL transition the
  workflow to `rejected` and SHALL NOT execute any external side effect.
- WHEN a `DecisionSignal` with `decision=edit` arrives THE SYSTEM SHALL create
  a new proposal revision from `edited_payload`, transition to `validating`,
  and re-run policy evaluation before deciding whether the new revision needs
  a fresh `waiting_approval` state or may proceed to `executing`.
- WHEN a `DecisionSignal` with `decision=cancel` arrives THE SYSTEM SHALL
  transition the workflow to `cancelled` and SHALL NOT interrupt or reverse
  an external side effect that Activity execution has already committed.
- WHEN two or more `DecisionSignal`s target the same `approval_id` and
  `expected_revision` THE SYSTEM SHALL accept only the first valid terminal
  decision and SHALL ignore or reject every subsequent one idempotently.
- IF a `DecisionSignal.request_id` has already been recorded as processed for
  this workflow THEN THE SYSTEM SHALL ignore the duplicate without
  re-executing any side effect or re-emitting a duplicate audit transition
  for the same decision.
- IF a `DecisionSignal.expected_revision` does not match the workflow's
  current proposal revision THEN THE SYSTEM SHALL reject the signal without
  changing workflow state.
- IF a `DecisionSignal.approval_id` does not match the workflow's current
  `approval_id` THEN THE SYSTEM SHALL reject the signal without changing
  workflow state.
- WHILE a proposal is in `waiting_approval` THE SYSTEM SHALL run a durable
  Temporal timer bounding the approval TTL, and WHEN that timer fires before
  any valid decision arrives THE SYSTEM SHALL transition the workflow to
  `expired` exactly once.
- BEFORE any execution Activity fires THE SYSTEM SHALL recheck tenant/account
  ownership, capability, peer identity, proposal version, policy version, and
  the kill switch, mirroring the re-check-at-send-time invariant already
  implemented in `internal/agent/executor.send`.
- WHEN any workflow state transition occurs THE SYSTEM SHALL persist a
  product audit event (using the existing hash-chained `audit_logs` /
  `Store.LogToolCall` pattern or an equivalent independent store) that does
  not depend on Temporal history remaining available.
- WHEN the workflow or worker starts THE SYSTEM SHALL register on an explicit,
  named Temporal task queue rather than the default queue.
- WHEN a client queries workflow status THE SYSTEM SHALL return current
  state, current proposal revision, approval expiry, and the terminal result
  (if any) through a Temporal Query handler, without mutating workflow state.
- IF workflow history is projected to grow unboundedly through repeated
  `edit` cycles THEN THE SYSTEM SHALL use Continue-As-New to bound history
  size.
- WHILE the Temporal integration is being rolled out THE SYSTEM SHALL gate it
  behind an explicit feature flag scoped to a single test tenant/account, and
  THE SYSTEM SHALL leave the existing `agent_actions`/`internal/agent/executor`
  path fully operational for every tenant/account not opted in.

## Out of scope

- Deleting or replacing the current `agent_jobs`/`agent_actions` durable
  queue and the `internal/agent/executor` send path (epic #339 non-goal;
  they keep serving all non-flagged tenants during rollout).
- Replacing `internal/agent/policy.Evaluate`'s deterministic decision logic
  with workflow code — the workflow calls/consumes it, it does not
  reimplement it (epic #339 non-goal).
- The HTTP/API surface for listing approvals and submitting decisions
  (`GET /v1/approvals/...`, `POST /v1/approvals/{id}/decision`) and its
  authorization/rate-limiting — that is issue #341, which explicitly depends
  on this issue.
- Any UI work.
- Moving Telegram session/domain state into Temporal (epic #339 non-goal).
- Treating Temporal workflow history as the sole audit store (epic #339
  non-goal; product audit events must be independently persisted per this
  issue's own requirement).
- Multi-tenant `tenant_id`/`account_id` modeling in the rest of the codebase
  — today's schema is single-tenant-per-`user_id` (see `agent_profiles`,
  `agent_actions`); this proposal introduces `tenant_id`/`account_id` only
  inside the new Temporal workflow's identifiers and input, and maps them
  onto the existing `user_id`/profile model rather than migrating the whole
  schema (see Open questions).
- Channels preview (`cmd/agent-channel`, Part 2 of
  `docs/plans/communication-agent.md`) — unrelated transport work.
- Production promotion / guarded autopilot — this issue only builds the
  workflow; enabling it beyond the flagged test tenant is a later rollout
  gate decision.

## Open questions

- How do Temporal's `tenant_id`/`account_id` map onto the current schema,
  which keys everything by `agent_profiles.user_id` (the Telegram account
  owner) with no tenant/account split? Most reasonable interpretation used
  in this proposal: `tenant_id = user_id` (the owning `users.id`), and
  `account_id` identifies the specific Telegram account/session under that
  owner (today there is exactly one per `user_id`, so `account_id` can start
  as a fixed/derived value such as `"primary"` or the same `user_id`) —
  revisit if/when true multi-account-per-tenant ownership is added.
- Should the workflow persist its own proposal/approval rows, or should it
  read/write through the existing `agent_actions` table so the two paths stay
  reconcilable during the flagged rollout? This proposal assumes a new,
  separate table set (e.g. `communication_approval_workflows` /
  `communication_approval_events`) scoped to the Temporal path, joined to
  `agent_actions`/`agent_jobs` by `operation_id`, rather than repurposing the
  existing CAS-based `agent_actions.status` column for two different
  orchestration engines at once. This avoids a second writer racing the
  existing executor's CAS transitions on the same row.
- Which Temporal deployment (self-hosted Temporal Server + Postgres, or
  Temporal Cloud) is available to `mctl-gitops`? Not decided by this issue;
  the design assumes a reachable Temporal frontend endpoint is provided via
  config/env and defers the deployment decision to the GitOps
  implementation PR.
- Exact wire schema versioning for the `DecisionSignal` payload (the issue
  says "one versioned decision signal") — this proposal adds an explicit
  `signal_version` integer field and documents that unknown/future decision
  values must be rejected, not silently ignored, but the concrete version
  negotiation policy is left to the implementer.
- Whether `waiting_approval` after an `edit` always requires an explicit new
  approval, or can policy legitimately auto-approve some edits. The issue is
  explicit that "a policy rule may require approval again after edit; do not
  assume that an edit implies approval" — this proposal treats every edit as
  routing back through the same `policy.Evaluate` call used for the original
  proposal, with no special-cased shortcut.
