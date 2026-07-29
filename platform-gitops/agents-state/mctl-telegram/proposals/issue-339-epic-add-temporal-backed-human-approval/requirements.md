# Temporal-backed human approval flow for the Communication Agent

## Context

`mctl-telegram`'s Communication Agent (`internal/agent/*`, `internal/agentapi`,
`internal/db/agent_actions.go`) already has a working `require_approval`
lifecycle: `policy.Evaluate` (`internal/agent/policy/policy.go`) decides
`allow` / `deny` / `require_approval`; a `require_approval` action is
persisted as `agent_actions.status = pending_approval` with an encrypted,
blind-indexed approval code; the owner decides via a Telegram Saved Messages
`/mctl approve|reject <code>` command parsed by `internal/agent/control`
(`command.go`, `router.go`) and executed by `internal/agent/executor`; a
minute-scale background sweep (`Store.ExpireStaleAgentActions`, wired from
`sweeper.AgentExecutor`/`cmd/server/main.go`) expires stale drafts; a second
sweep (`Executor.RecoverStuck`) retries actions crashed mid-send using a
persisted MTProto `random_id` for dedup. This is a real, tested, in-production
(preview) system — see `docs/plans/communication-agent.md`, "Status
(2026-07-27)".

Issue #339 asks for a second, Temporal-backed waiting mechanism layered on
top of this. The stated motivation is durable waiting across process/pod
restarts with an explicit signal channel, deterministic timers for expiry,
and workflow history as an execution audit trail — plus two decision types
the current system does not support at all: `edit` (replace the payload and
revalidate) and `cancel` (stop the broader flow, not just this one action).
This matters because the current design already gets crash-safety and
expiry via DB polling and a persisted-random_id pattern, but it does so with
periodic sweeps rather than an event-driven wait, and it has no notion of
"cancel the whole thing" versus "reject this one draft" — Temporal's signal
and timer primitives are a better fit for both gaps, provided the existing
deterministic policy engine and audit chain remain authoritative (see Out of
scope / Non-goals below, taken directly from the issue).

## User stories

- AS the account owner reviewing an agent-drafted reply I WANT to approve,
  reject, edit, or cancel the pending action from wherever I already interact
  with the agent (Telegram Saved Messages today, an API/UI surface later) SO
  THAT I control what gets sent without needing to trust the model's own
  judgment.
- AS the account owner I WANT an edited draft to be re-validated by the same
  server-side policy that gated the original draft SO THAT editing cannot be
  used to bypass URL/credential/length/rate-limit checks.
- AS an on-call operator I WANT a pending approval to survive a Temporal
  worker restart or Kubernetes rollout without being lost or silently
  re-triggered SO THAT deploys and crashes are never a data-loss or
  double-send event.
- AS an on-call operator I WANT every approve/reject/edit/cancel/expire
  transition to show up in the existing product audit trail (`audit_logs`
  hash chain, `GET /api/audit`) SO THAT Temporal workflow history is not the
  only record and existing audit tooling keeps working unchanged.
- AS a platform engineer rolling this out I WANT it behind a feature flag
  scoped to a single test tenant SO THAT a Temporal integration bug cannot
  regress the already-working DB-based approval path for every other
  account.
- AS a platform engineer I WANT duplicate or late signals (a second
  `/mctl approve`, a signal delivered after expiry, a redelivered decision)
  to be provably incapable of sending an action twice SO THAT Temporal
  becomes an additional safety layer, not a new double-send risk.

## Acceptance criteria (EARS)

- WHEN `policy.Evaluate` returns `require_approval` for a tenant with the
  Temporal approval flag enabled THE SYSTEM SHALL persist the pending action
  exactly as it does today (`agent_actions.status = pending_approval`,
  encrypted approval code) AND start (or idempotently attach to) a durable
  Temporal workflow keyed to that action.
- WHILE a Temporal approval workflow is waiting for a decision THE SYSTEM
  SHALL require no polling loop or occupied worker slot for that wait (a
  Temporal timer plus a blocked signal handler only).
- WHEN the owner issues `approve` THE SYSTEM SHALL execute the proposed
  action exactly once, re-checking policy/kill-switch/mode immediately before
  the send RPC, identically to the existing `Executor.Approve` re-check.
- WHEN the owner issues `reject` THE SYSTEM SHALL terminate the workflow
  without executing the action and SHALL transition the row to `rejected`.
- WHEN the owner issues `edit` with a replacement payload THE SYSTEM SHALL
  replace the proposed payload, re-run `policy.Evaluate` against the new text,
  and SHALL only proceed to execution if the revalidated decision is not
  `deny`; a revalidated `require_approval` SHALL return the workflow to the
  waiting state rather than auto-approving the edit.
- WHEN the owner issues `cancel` THE SYSTEM SHALL stop the action's workflow
  AND SHALL deny every other non-terminal, non-executing action tied to the
  same conversation/job turn (mirroring `Store.DenyPendingActionsForConversation`),
  distinguishing it from `reject`, which affects only the one action.
- IF a decision signal (of any kind) arrives for an action whose workflow has
  already recorded a terminal decision THEN THE SYSTEM SHALL discard the
  signal, SHALL NOT execute or re-execute anything, and SHALL audit the
  discarded attempt.
- IF a decision signal arrives after the action's approval TTL has elapsed
  THEN THE SYSTEM SHALL treat it as expired (same outcome as the deterministic
  timer firing first) and SHALL NOT execute the action.
- WHEN a Temporal worker process restarts while an approval workflow is
  waiting THE SYSTEM SHALL resume that workflow from its persisted history
  with no owner-visible state loss and no duplicate execution once a
  previously-recorded decision replays.
- WHEN an action's approval TTL elapses with no decision THE SYSTEM SHALL
  deterministically expire it via a Temporal timer, transition the row to
  `expired`, and SHALL record the expiry in the product audit log.
- WHEN any transition occurs (proposed, pending_approval, approved, edited,
  rejected, cancelled, expired, executing, executed, denied) THE SYSTEM SHALL
  make it retrievable through the existing product audit API
  (`audit_logs` hash chain / `GET /api/audit`), not only through Temporal's
  own workflow history UI.
- WHILE the feature flag is disabled for a tenant THE SYSTEM SHALL continue
  routing that tenant's `require_approval` actions through the existing
  DB-sweep-and-command-router path unchanged.
- IF the Temporal server/namespace is unreachable when a `require_approval`
  decision is proposed for a flagged-in tenant THEN THE SYSTEM SHALL fail
  safe: the action SHALL remain `pending_approval` in the DB (never silently
  `allow`), and existing DB-based expiry SHALL still apply as a backstop.
- WHERE `db.ActionType` is `send_owner_summary` or `request_owner_approval`
  (the two owner-facing, always-`allow` action types) THE SYSTEM SHALL NOT
  route them through the Temporal wait — only `propose_reply` actions that
  actually evaluate to `require_approval` enter a workflow.

## Out of scope

Directly from the issue's Non-goals, applied to this repo:

- Moving Telegram session/domain state (client pool, MTProto sessions,
  conversation/message storage) into Temporal. `internal/telegram`,
  `internal/db`'s conversation tables are unaffected.
- Replacing `policy.Evaluate` with workflow code. The workflow only
  orchestrates waiting and calls back into the existing, unchanged policy
  engine via activities.
- Treating Temporal workflow history as the sole audit store. The
  `audit_logs` hash chain and `GET /api/audit` remain the product audit
  surface of record; Temporal history is operational/debugging detail only.
- Removing the existing DB-based queue, sweep (`ExpireStaleAgentActions`,
  `RecoverStuck`), or `/mctl approve|reject` command path before the
  Temporal path is proven — both paths run in parallel, selected per tenant
  by feature flag, for the duration of this proposal's scope.
- Building the Channels/Option-A transport work described in
  `docs/plans/communication-agent.md` Part 2 — unrelated to this issue.
- Designing the eventual production Temporal cluster topology (multi-region,
  namespace-per-tenant, Temporal Cloud vs self-hosted) in detail; this
  proposal assumes one shared namespace, scoped down to a single test tenant
  by the feature flag, and defers cluster-topology hardening to a follow-up.

## Open questions

The issue is an epic and leaves several implementation choices open. None of
these block the design below; each records the most reasonable
interpretation taken.

1. **Temporal deployment target** (self-hosted in the existing k8s cluster
   vs Temporal Cloud). Not specified in the issue. Assumed: self-hosted
   Temporal server + Postgres persistence store in the `labs` namespace
   initially, matching this repo's existing "preview in `labs`, promote
   later" pattern (`docs/plans/communication-agent.md` C1/C2). A platform
   engineer should confirm before Task 1 below starts.
2. **What "the overall communication workflow" means for `cancel`.** The
   issue's target-flow diagram implies a single workflow per Telegram
   event/agent request, but this codebase's job lifecycle
   (`agent_jobs`/`agent_job_attempts`, claimed over HTTP by
   `cmd/agent-worker`) is not itself a Temporal workflow and this proposal
   deliberately does not move it into one (see Out of scope). Interpreted as:
   `cancel` denies every other non-terminal action tied to the same
   conversation, reusing `Store.DenyPendingActionsForConversation`'s existing
   semantics (already used by `/mctl takeover`), scoped to the approval
   workflow's own action plus siblings from the same conversation turn.
3. **Decision UI surface.** The issue says "expose decision commands through
   the agent API/UI." Saved Messages `/mctl` commands already exist for
   approve/reject; this proposal extends `control.ParseCommand` with `edit`
   and `cancel` subcommands AND adds equivalent `agentapi` HTTP endpoints
   (mirroring the existing `POST /actions/*` shape) so a future web UI is not
   blocked on a Telegram round-trip. No UI mockup is provided by the issue;
   none is assumed beyond the HTTP contract.
4. **Per-tenant Temporal enablement mechanism.** No existing feature-flag
   system exists in this repo beyond env-var booleans
   (`AGENT_ENABLED`, `AGENT_KILL_SWITCH`) and CSV allowlists
   (`agent_profiles.sender_allowlist`, `blocked_senders`). Assumed: a new CSV
   env var `AGENT_TEMPORAL_APPROVAL_TENANTS` (user IDs) plus a global
   `AGENT_TEMPORAL_APPROVAL_ENABLED` kill switch, following the existing
   convention exactly rather than introducing a new config system.
5. **Idempotency key for signals.** The issue requires duplicate signals to
   be safe but does not specify a mechanism. Assumed: each decision carries a
   caller-supplied idempotency token (for `/mctl`, derived from the approval
   code + a per-command sequence the router already tracks via
   `agent_saved_command_cursors`; for the HTTP API, a client-supplied
   `Idempotency-Key` header), and the workflow itself only accepts the first
   decision signal it processes, matching the "signal channel already closed"
   pattern in the Temporal Go SDK.
6. **Retention/deletion of Temporal workflow history for a deleted account.**
   Not mentioned in the issue. Assumed: Temporal's own retention policy
   (configured short, e.g. 7-30 days post-completion) plus this repo's
   existing `HardDeleteAccount` purge terminating any live workflow for that
   user — needs explicit handling, flagged as a task below, not left silent.
