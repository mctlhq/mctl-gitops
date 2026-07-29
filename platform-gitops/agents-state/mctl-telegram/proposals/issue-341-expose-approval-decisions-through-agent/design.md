# Design: issue-341-expose-approval-decisions-through-agent

## Current state

**Approval state machine.** `internal/db/agent_schema.go` defines
`agent_actions` (statuses in `internal/db/agent_actions.go`:
`ActionProposed`, `ActionPendingApproval`, `ActionApproved`,
`ActionExecuting`, `ActionExecuted`, `ActionRejected`, `ActionExpired`,
`ActionDenied`). Legal transitions are a hardcoded adjacency map
(`agent_actions.go:405-425`) enforced by `Store.UpdateAgentActionStatus`'s
CAS `UPDATE ... WHERE status = from`. There is no `edit` or `cancel`
decision and no numeric revision column — "staleness" today is entirely
"is the row still in the expected status", not "is this the version I looked
at". Approval codes are cryptographically random, stored as a keyed blind
index + per-user AES-GCM ciphertext (never plaintext), single-use, bound to
owner + conversation + action + message version (`agent_schema.go:58-77`,
`approvalcode.go`).

**Decision channel today.** The only way to decide an approval is Telegram
Saved Messages: `internal/agent/control.ParseCommand` parses `/mctl
approve|reject <code>`; `internal/agent/control.Router`
(`internal/agent/control/router.go`) looks the action up by code
(`Store.GetAgentActionByCode`) and calls into `internal/agent/executor`
(`Approve`/`Reject`, `executor.go`), which re-checks kill switch/mode/policy,
persists a Telegram `send_random_id` before the MTProto RPC (crash-safe
retry via Telegram's own dedup), and only then flips the row to
`executing`/`executed`. This executor is explicitly "the only code path in
this repo that sends a reply on the agent's behalf" (package doc,
`executor.go:1-11`) — #341 must not create a second one.

**No Temporal today.** `go.mod` has no Temporal SDK dependency and no code
under `internal/` references Temporal. #339/#340 (both open) propose
introducing it; #340 specifically defines the workflow
(`CommunicationApprovalWorkflow`), its identifiers
(`workflow_id = communication:{tenant_id}:{account_id}:{operation_id}`,
`approval_id = {workflow_id}:{approval_revision}`), and a single versioned
decision Signal (`approve|reject|edit|cancel`, `expected_revision`, `actor`,
`edited_payload`, `reason`, `request_id`, `decided_at`) with a Query for
current status/revision. #341 is written to consume that contract but is not
blocked from being built and tested before #340 merges, because the contract
is small and stable enough to code against as an interface.

**No tenant/account split.** `agent_profiles` is keyed 1:1 by `user_id`
(`agent_schema.go`), and every store method that scopes agent data
(`GetAgentAction`, `ListActionsByStatus`, etc.) takes `userID` directly. The
word "tenant" appears throughout the codebase only as a synonym for
per-user data isolation (`internal/db/store.go:147,722`,
`internal/agent/profile/profile.go`), never as a distinct column or entity.
There is no `account_id` or `agent_profile_id` concept separate from
`user_id` anywhere in the schema.

**Existing auth/API precedent to follow.** `internal/agentapi` is the
worker-facing surface (`aud=agent` JWT, minted by an admin via
`POST /api/agent/token`, mounted at `/api/agent/v1` behind
`auth.Middleware(agentProvider, ...)` in `cmd/server/main.go:442-450`). It
already uses a **narrow interface seam** for an optional collaborator
(`OwnerProfileProvider`, `agentapi/server.go:32-40`) specifically so the
package does not need to depend on a concrete implementation that may not
exist yet — the same pattern #341 needs for "signal a Temporal workflow that
may or may not be deployed yet." User-facing (not worker) endpoints already
exist at `/api/account`, mounted behind the standard `auth.Middleware(provider,
true, m)` (`cmd/server/main.go:392`), using `auth.Identity` from
`internal/auth/identity.go` (`UserID`, `Subject`, `Scopes`, `Groups`) resolved
server-side by the auth provider — never taken from the request body. This is
the correct auth pattern for #341 (an owner/UI-facing surface), not the
`aud=agent` pattern (that's for the trusted worker process only).
`internal/audit.RateLimiter` already provides per-identity and
per-(identity,peer) token buckets with a `Middleware()` and a `metrics`
hook (`ratelimit.go`) — directly reusable for the decision endpoint's
rate limit requirement.

**Existing audit precedent.** `internal/db/audit_chain.go` hash-chains a
fixed-schema MCP tool-call audit log (`user_id`, `tool_name`, `peer_redacted`,
`status`, `error`, `created_at`, `call_path`). Its schema is too narrow for
what #341 needs (no `workflow_id`/`approval_id`/`revision`/`operation_id`/
`policy_version`/`proposal_hash` fields, and it is keyed to one tool call, not
a multi-event approval lifecycle) but its approach — append-only, SHA-256
chained over canonically-ordered fields — is the right pattern to reuse for
tamper-evidence, not a table to repurpose.

## Proposed solution

### 1. Two seams, not one Temporal dependency

Define two narrow interfaces in a new `internal/agentapproval` package
(mirrors `agentapi`'s package-per-surface convention), so the HTTP layer,
the audit model, and the tests do not require #340 to exist yet:

```go
// ApprovalReader answers point reads and list queries. Backed today by a
// DB projection (see below); once #340 ships, point reads additionally
// consult the workflow Query for authoritative in-flight status.
type ApprovalReader interface {
    Get(ctx context.Context, userID int64, approvalID string) (*ApprovalView, error)
    List(ctx context.Context, userID int64, status string, cursor Cursor) ([]ApprovalView, error)
}

// DecisionSignaler sends the versioned decision Signal defined by #340.
// Returns ErrWorkerUnavailable (mapped to 503, not 200) when Temporal
// cannot be reached, so a decision is never silently dropped.
type DecisionSignaler interface {
    Signal(ctx context.Context, d Decision) (SignalOutcome, error)
}
```

Until #340 merges, `DecisionSignaler` is implemented by an adapter over the
**existing** `internal/agent/executor` Approve/Reject calls and
`Store.UpdateAgentActionStatus` (see "Compatibility" below) — this is what
lets #341 ship and be useful immediately, and is also the required fallback
path per the issue's rollout note ("retain compatibility with the current
approval/job representation during migration"). Once #340 lands, a second
`DecisionSignaler` implementation calls the real Temporal client, and a
per-action flag (already-established `agent_profiles`-scoped feature-flag
convention, e.g. `agent_profiles.temporal_approvals_enabled` or a global env
var following the `AGENT_ENABLED`/`AGENT_KILL_SWITCH` naming precedent in
`internal/config/config.go`) selects which one handles a given approval.
`edit` and `cancel` are new decisions with no legacy equivalent; the legacy
adapter maps them onto the closest existing capability (`edit` -> denied
with a clear "not supported pre-migration" reason at validation time,
surfaced as 422, since the current executor has no revalidate-and-resend
path; `cancel` -> `UpdateAgentActionStatus` to `ActionDenied` with an audit
note) rather than inventing new legacy behavior that would be thrown away
the moment #340 ships.

### 2. HTTP surface

New package `internal/agentapprovalapi` (HTTP layer only; business logic
stays in `internal/agentapproval`), registered the same way `agentapi`
registers itself (`Register(mux registrar)`), mounted at `/api/v1/approvals`
in `cmd/server/main.go` behind the **standard user** `auth.Middleware`
(same provider as `/api/account`, not the `aud=agent`/`aud=bridge` providers
— this surface is for owners/UI, never for the worker), gated by a feature
flag mirroring `AGENT_ENABLED` (e.g. `AGENT_APPROVALS_API_ENABLED`), and
wrapped with `internal/audit.RateLimiter.Middleware()` plus a tighter
per-approval decision rate limit via `AllowPeerN`-style accounting keyed on
`approval_id` instead of a Telegram peer hash.

```
GET  /api/v1/approvals/{approval_id}
GET  /api/v1/approvals?status=pending&limit=&before_id=
POST /api/v1/approvals/{approval_id}/decision
```

Every handler resolves `userID := auth.From(ctx).UserID` first and passes
that (never a body/path-supplied tenant field) into
`ApprovalReader`/`DecisionSignaler`. `approval_id` in the path is opaque to
the caller's authorization — ownership is proven by the row lookup returning
a match for `userID`, not by trusting the ID's embedded `user_id`/`account_id`
segments, exactly per the issue's "do not accept tenant/account/actor
identity from untrusted request fields as authoritative."

`POST .../decision` validates, in order: rate limit -> capability/scope
check (new `agent:approvals:decide` scope on `auth.Identity`) -> ownership
(404 if not owned) -> terminal-state check (return terminal state, no-op) ->
`request_id` idempotency lookup (return prior result if seen) ->
`expected_revision` match (409 if stale) -> `edited_payload` schema
validation for `edit` (422 on unknown fields, reusing `encoding/json`'s
`DisallowUnknownFields` the way other strict-payload handlers in this repo
already validate) -> signal. Every one of these steps writes an audit event
before returning, including the rejected ones (stale-revision and
duplicate-request are themselves required audit event kinds per the issue).

### 3. Audit model

New table `agent_approval_audit_events`, following `audit_chain.go`'s
hash-chain approach but with the correlation fields the issue requires
(new fields relative to the existing `mcp_audit_log`-style chain):

```sql
CREATE TABLE agent_approval_audit_events (
    id                 BIGSERIAL/AUTOINCREMENT PRIMARY KEY,
    event_type         TEXT NOT NULL,   -- requested|viewed|decision_submitted|
                                         -- decision_accepted|decision_rejected_stale|
                                         -- decision_rejected_duplicate|proposal_edited|
                                         -- policy_reevaluated|execution_started|
                                         -- execution_completed|execution_failed|
                                         -- expired|cancelled|rejected
    workflow_id        TEXT,            -- NULL pre-#340 (legacy path)
    workflow_run_id    TEXT,
    approval_id        TEXT NOT NULL,
    approval_revision  INT NOT NULL,
    operation_id       TEXT,
    tenant_id          BIGINT NOT NULL, -- = user_id today, see Platform impact
    account_id         BIGINT NOT NULL, -- = user_id today
    agent_profile_id   BIGINT NOT NULL, -- = user_id today
    actor_type         TEXT NOT NULL,   -- user|system|worker
    actor_id           TEXT NOT NULL,
    request_id         TEXT,
    policy_version     TEXT,
    proposal_hash      TEXT,
    prev_hash          BYTEA/BLOB,
    entry_hash         BYTEA/BLOB NOT NULL,
    created_at         TIMESTAMPTZ/DATETIME NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_agent_approval_audit_tenant ON agent_approval_audit_events(tenant_id, created_at);
CREATE INDEX idx_agent_approval_audit_approval ON agent_approval_audit_events(approval_id, id);
```

Added via `addColumnIfMissing`/idempotent `CREATE TABLE IF NOT EXISTS` in
`internal/db/agent_schema.go`, following the exact pattern already used for
every other agent-domain table in that file (both PG and SQLite dialects,
hooked into `migrateAgent`). Every `GET` (view) and every step of `POST
.../decision` writes one row here, independent of whatever Temporal history
exists — satisfying "Temporal history is operational evidence, not a
substitute for this tenant-scoped audit model." `Store.InsertAgentApprovalAuditEvent`
follows the append-only, no-UPDATE, no-DELETE discipline `audit_chain.go`
already establishes for the MCP audit log.

### 4. Read-model / projection

`agent_actions` remains the source of truth for the legacy (pre-#340) path.
Once #340 exists, `ApprovalReader.Get` calls the workflow Query for
authoritative live state and falls back to the last known
`agent_approval_audit_events` row (or a small denormalized
`agent_approval_projection` view maintained by workflow-emitted audit
events) when the Temporal frontend is unreachable — satisfying "API remains
correct when the Temporal worker is temporarily unavailable" for reads.
`List` always serves from the DB projection/audit table (never a live
Temporal query, which does not scale to "list all pending approvals for a
tenant").

### 5. Editable-payload schema validation

`edit` requires validating `edited_payload` against the specific
`action_type`'s schema (today: `propose_reply`'s payload shape, defined
implicitly by `internal/agentapi/actions.go`'s `handleProposeReply` decode
struct). Proposing a small `internal/agent/policy` (or new
`internal/agent/editvalidate`) registry mapping `action_type -> json.RawMessage
decode-and-reject-unknown-fields struct`, reused by both #341's HTTP layer
and #340's workflow-side revalidation (per #340's "revalidate edited or
stale actions before execution"), so the two issues do not each invent a
separate, potentially-diverging validator.

## Alternatives

1. **Wait for #340 to merge before starting #341.** Rejected: the issue
   explicitly asks for a spec-driven proposal now, and the two seams
   (`ApprovalReader`/`DecisionSignaler`) let the HTTP surface, auth,
   validation, rate-limiting, and audit model — the bulk of #341's actual
   scope — be built and tested against the legacy `agent_actions` state
   machine today, with only the Temporal-backed implementation swapped in
   later. Blocking wastes the interface-seam pattern the codebase already
   uses successfully (`OwnerProfileProvider`).

2. **Extend `agent_actions`/`internal/agentapi` in place instead of new
   packages.** Rejected: `internal/agentapi` is documented as "the ONLY way
   agent code reaches mctl-telegram data" (its aud=agent, worker-trust
   boundary) — mixing an owner-facing, differently-authenticated surface
   into it blurs that boundary and its tests' JWT-audience assumptions. A
   sibling package with its own auth wiring keeps the two trust boundaries
   separable, matching how `internal/bridge`/`agentapi` are already kept
   separate from each other despite both being "internal HTTP surfaces."

3. **Use Temporal workflow history directly as the audit source instead of a
   new DB table.** Rejected by the issue itself ("Temporal history is
   operational evidence, not a substitute for this tenant-scoped audit
   model") and impractical before #340 exists at all; also would not cover
   the legacy pre-#340 path, breaking the migration-compatibility
   requirement.

4. **Real `tenant_id`/`account_id` columns and a full multi-tenant data
   model now.** Rejected as unscoped for this issue: nothing else in the
   codebase has a multi-account-per-user concept yet (`agent_profiles` is
   1:1 with `user_id`), and inventing that shape without a concrete second
   consumer risks guessing wrong. Aliasing to `user_id` while keeping the
   columns distinct in the new audit table is the smaller, reversible step.

## Platform impact

- **Migrations.** Additive only: one new table
  (`agent_approval_audit_events`, both PG/SQLite dialects) via the existing
  idempotent `migrateAgent` pattern in `internal/db/agent_schema.go`; no
  changes to `agent_actions`/`agent_jobs` schemas required for the
  legacy-compatible path. If a numeric `approval_revision` is needed on
  `agent_actions` itself for the legacy adapter's optimistic-concurrency
  check, add it via `addColumnIfMissing` (`agent_actions.revision INT NOT
  NULL DEFAULT 1`, incremented on every status transition), matching the
  file's established idempotent-ALTER convention.
- **Backward compatibility.** The Saved Messages `/mctl approve|reject`
  path is untouched — `internal/agent/executor` keeps being "the only code
  path that sends a reply." The new API's legacy `DecisionSignaler`
  implementation calls into the *same* executor/store methods
  (`Store.UpdateAgentActionStatus`, `executor.Approve/Reject`), so a
  decision made via `/mctl approve` and a decision made via the API cannot
  race past each other undetected — both go through the same CAS.
- **Resource impact.** One additional write per read/decision on the audit
  table; bounded by the existing per-tenant approval volume (observe-mode
  scale per `docs/plans/communication-agent.md`, not high-throughput). Rate
  limiting via the existing `internal/audit.RateLimiter` adds negligible
  memory (in-process token buckets, already used fleet-wide).
- **Risks + mitigations.**
  - *Risk*: two decision paths (Saved Messages, new API) racing on the same
    action. *Mitigation*: both funnel through the same store-level CAS;
    the API additionally records the loser's attempt as a
    `decision_rejected_stale`/`decision_rejected_duplicate` audit event
    instead of silently dropping it.
  - *Risk*: shipping a `DecisionSignaler` seam that #340 doesn't actually
    match once implemented. *Mitigation*: interface is intentionally
    minimal (one `Signal` method) and mirrors #340's own stated Signal
    JSON almost verbatim; a mismatch is a small adapter change, not a
    rewrite of the HTTP/audit layers.
  - *Risk*: `tenant_id == user_id` aliasing looks like real multi-tenancy to
    a future reader and gets load-bearing assumptions built on it.
    *Mitigation*: document the alias explicitly in code comments on the new
    columns and in this proposal; do not derive any authorization decision
    from `tenant_id` alone — always resolve through `user_id`/`auth.Identity`.
  - *Risk*: new capability scope (`agent:approvals:decide`) not actually
    wired into any existing token-minting path. *Mitigation*: rollout
    behind `AGENT_APPROVALS_API_ENABLED`, enabled for one test
    tenant/account first (per issue's Rollout section and #339's own
    delivery note), same as the rest of the Communication Agent rollout.
- **Rollout.** Same feature-flag family as #339
  (`AGENT_APPROVALS_API_ENABLED`, default false), enabled first for the
  existing C1 test tenant/account (`docs/plans/communication-agent.md`'s
  established staging environment), before any production tenant.
