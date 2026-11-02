# Managed runtime slice 2: claim-only pool credential and the managed claim path

## Context

Issue mctlhq/mctl-telegram#1090 is slice 2 of epic #1088 (P5 of #1002) and
implements sections 2 and 3 of `docs/adr/0008-managed-runtime.md`. Slice 1
(#1089) has already landed: `agent_profiles.runtime` (`own|managed`, default
`own`), the managed consent columns, `MANAGED_RUNTIME_ENABLED` /
`MANAGED_RUNTIME_MAX_ACCOUNTS` in `internal/config/config.go`, and the
consent-gated runtime switch in `internal/assistantinstall/runtime.go`. The
OpenAI runner from slice 3 (`internal/agentworker/openairunner.go`) is also in
the tree. What is missing is the thing that actually lets the platform's own
worker claim a managed account's jobs: a new credential shape (`aud=agent-pool`),
a route to mint it, a guard that makes it claim-only, a runtime predicate in
both claim queries, and a pool branch of `handleClaimJobs` that claims across
managed accounts and hands the worker one job-bound token per job.

It matters because the managed tier widens who holds a credential that can
reach many accounts' job streams. The invariants are therefore enforced where
they cannot be bypassed: own and managed jobs are separated in SQL, the pool
identity can do nothing but claim, revoking the pool kills every job token it
has already produced, and the existing Mac mini (`own`) worker path keeps its
behaviour.

## User stories

- AS a platform operator I WANT to mint one revocable, claim-only pool token per
  environment SO THAT a single platform worker can serve every managed account
  without holding a per-account credential.
- AS an owner who chose `runtime: managed` I WANT my jobs claimed only by the
  platform pool and never by an own worker SO THAT my consent decision is what
  decides who processes my messages.
- AS an owner who runs my own worker (`runtime: own`) I WANT the pool to never
  claim my jobs and my worker to keep working exactly as before SO THAT nothing
  changes for me.
- AS a security reviewer I WANT revoking the pool's `jti` to kill all job tokens
  already derived from it within the revocation cache TTL SO THAT containment is
  one action.
- AS an operator diagnosing the managed worker I WANT every pool claim and every
  pool refusal to be audited/logged with `pool:<name>` SO THAT I can see what the
  pool did.

## Acceptance criteria (EARS)

Pool credential
- WHEN an admin with scope `admin:users` calls `POST /api/agent/pool-token` with
  `{pool_name, ttl_hours}` WHILE `AGENT_ENABLED` and `MANAGED_RUNTIME_ENABLED`
  are on THE SYSTEM SHALL return a token with `aud=agent-pool`,
  `sub=pool:<pool_name>`, no Telegram id, no job id, a fresh random `jti`, and
  `orig_iat` equal to its `iat`, and SHALL log one structured line in the shape
  of `workertoken.LogMinted` (admin user id, pool name, ttl, expires_at, jti).
- IF `ttl_hours` is omitted or `<= 0` THEN THE SYSTEM SHALL use 30 days; IF it
  exceeds 90 days (2160 hours) THEN THE SYSTEM SHALL clamp it to 90 days without
  integer overflow.
- IF `pool_name` is empty or does not match `^[a-z0-9][a-z0-9-]{0,62}$` THEN THE
  SYSTEM SHALL answer 400; IF the caller lacks `admin:users` THEN 403; IF the
  body has unknown fields THEN 400.
- WHILE `MANAGED_RUNTIME_ENABLED` is off THE SYSTEM SHALL NOT mount
  `POST /api/agent/pool-token` (404) and SHALL NOT chain the pool provider, so a
  pool token is refused with 401 on `/api/agent/v1/*`.
- WHEN a request to `/api/agent/v1/*` carries an `aud=agent-pool` token THE
  SYSTEM SHALL verify it with `localjwt.PoolProvider`, which never calls
  `EnsureUserByTelegramID` and returns an identity with `UserID=0`,
  `TelegramID=0`, `Subject=pool:<name>`, `Pool=<name>`, and the token's `jti` and
  `orig_iat`.
- IF a pool token carries a non-zero Telegram id, a job id, a job attempt, a
  conversation id, job tools, a subject without the `pool:` prefix, a pool name
  that fails the name pattern, or no `jti` THEN THE SYSTEM SHALL reject it (401).
- WHEN the pool provider verifies a token THE SYSTEM SHALL always consult the
  revocation cache (fail closed on a cold cache error) and SHALL reject a revoked
  `jti`.
- WHEN an admin records a blanket revocation for an account's Telegram id THE
  SYSTEM SHALL NOT revoke the pool token (it carries Telegram id 0).

Claim-only guard
- WHEN a pool identity calls any `/api/agent/v1` route other than
  `POST /jobs/claim` (including `GET /events`, `GET /jobs/{id}` and
  `POST /jobs/{id}/cost`) THE SYSTEM SHALL answer 403 before the tool gate or
  handler runs and SHALL record the refusal (see design: structured audit log
  line and metric, because `audit_logs.user_id` requires a real user).

Runtime predicate in SQL
- WHEN any claim runs THE SYSTEM SHALL filter jobs in BOTH `ClaimAgentJobs`
  (plain) and `claimCoalesced` (turn coalescing) by
  `COALESCE((SELECT runtime FROM agent_profiles ap WHERE ap.user_id = j.user_id), 'own') = $runtime`.
- WHEN an account (`aud=agent`) token claims THE SYSTEM SHALL claim with
  runtime `own`; WHEN the pool claims THE SYSTEM SHALL claim with runtime
  `managed`.
- WHILE an account has no `agent_profiles` row THE SYSTEM SHALL treat it as
  `own`.
- WHEN a job is claimed THE SYSTEM SHALL stamp `agent_jobs.runtime` with the
  runtime it was claimed under, in both claim queries.

Pool claim branch
- IF a pool identity calls `POST /jobs/claim` and no job-token signer is
  configured THEN THE SYSTEM SHALL answer 503 and claim nothing.
- WHEN a pool identity claims THE SYSTEM SHALL list candidates via
  `Store.ListManagedClaimCandidates`: `runtime = 'managed'`, current managed
  consent, at least one due pending job, a non-zero `users.telegram_login_id`,
  fewer than `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` processing jobs, ordered by the
  oldest due job first.
- WHEN processing each candidate THE SYSTEM SHALL render that account's
  instructions and tool set BEFORE claiming; IF rendering fails (assistant
  disabled, lifecycle unknown, fork not runnable, any error) THEN THE SYSTEM
  SHALL skip that account and leave its jobs pending.
- WHEN claiming for candidates THE SYSTEM SHALL claim at most one job per
  account per response, round robin over candidates, until the requested limit
  (default 1, cap 10) is reached.
- WHEN minting the job token for a pool-claimed job THE SYSTEM SHALL take
  `Subject=tg:<id>` and `TelegramID` from the job's user via
  `Store.TelegramIDByUserID`, and SHALL keep the pool's `jti` and `orig_iat`.
- IF a job token cannot be minted for a pool-claimed job THEN THE SYSTEM SHALL
  NOT return that job without a token (the claim is released back to pending
  via the existing retry path) — a pool-claimed job is never handed out without
  a job token.
- WHEN the pool claims a job THE SYSTEM SHALL audit it under the job's user id
  with tool `get_events`, status `ok` and message `pool:<name>`.
- WHEN the pool's `jti` is revoked THE SYSTEM SHALL refuse every job token
  derived from it (for example `propose_reply`) and the pool's own claim within
  the revocation cache TTL (15 s).

Runtime switch fence
- WHEN an account's runtime changes, by the install service or by the admin
  profile route, THE SYSTEM SHALL bump `install_revision`, so the existing fence
  in `internal/agentapi/actions.go` refuses the in-flight attempt; the job is
  requeued by `RequeueStaleAgentJobs` and claimed by the new runtime.

Worker
- WHILE `AGENT_POOL_MODE=true` THE SYSTEM (worker) SHALL use the job token for
  the MCP subprocess, `GetJobStatus` and `ReportJobCost` in both the Claude and
  OpenAI runners, and SHALL fail the job with an error (never fall back to the
  pool token) when a claimed job has no job token.
- WHILE `AGENT_POOL_MODE` is unset or false THE SYSTEM (worker) SHALL behave
  exactly as today.

Own path
- WHILE a worker uses an `aud=agent` account token THE SYSTEM SHALL produce the
  same claim responses, job tokens and audit rows as before for an `own`
  account.

## Out of scope

- Budget ledger, reservations, caps and `budget_paused_until` filtering
  (slice 4, #1092); `ListManagedClaimCandidates` leaves a documented seam.
- Any change to the OpenAI runner's tool loop (#1091), the C1 gate (#1093),
  the CI image (#1094), deployment and Vault secrets (mctl-gitops#2345), docs
  (#1095).
- An MCP tool to mint pool tokens (the ADR makes it HTTP-only).
- Turning `MANAGED_RUNTIME_ENABLED` on in any environment.

## Open questions

- Issue text says `GetJobStatus`/`ReportJobCost` use the job token "when
  present (both runners)", but the acceptance requires the own path to be
  byte-for-byte unchanged and `OpenAIRunner.APIToken` documents why the account
  token is used there (the job token expires at the claim deadline). This
  proposal gates the switch on `AGENT_POOL_MODE=true`, which satisfies both;
  the reviewer should confirm.
- Consequence of inheriting the pool's `orig_iat`: after a blanket revocation
  of account A, every job token later minted from the pool for A is dead on
  arrival. The design skips such accounts in the pool claim branch (jobs stay
  pending and route to the operator like any unclaimed job) instead of claiming
  jobs whose tokens cannot work. Reviewer should confirm this is the intended
  semantic of "revoking an account stops that account's managed job".
- The issue says "403 + audit" for pool refusals, but `audit_logs.user_id` is a
  foreign key to `users` and a pool has no user. The design records the refusal
  as a structured `slog` line plus a policy-denial metric, and additionally as an
  `audit_logs` row under the job's user only when the route names a job that
  resolves to a managed account. Reviewer should confirm.
- Default for `MANAGED_MAX_INFLIGHT_PER_ACCOUNT` is not given; proposed 1
  (matches "concurrency across accounts, not within one").
- In pool mode the job token expires at the claim deadline, so a cost report
  after a deadline cancellation can be refused with 401. This proposal keeps the
  token TTL unchanged and records the risk; the ledger slice (#1092) may want a
  short grace window.
