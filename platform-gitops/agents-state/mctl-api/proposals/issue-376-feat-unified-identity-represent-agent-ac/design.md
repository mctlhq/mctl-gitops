# Design: issue-376-feat-unified-identity-represent-agent-ac

## Current state

### The principal model exists and already has a slot for agents

`internal/principals/store.go:77-105` defines `principals` (`id` `prn_<ulid>`,
`kind` `CHECK (kind IN ('human','agent','service'))`, `display_name`,
`status`, `created_at`) and `external_identities` (`xid_<ulid>`,
`principal_id`, `provider`, `issuer`, `subject`, `display`, `verified_at`,
`revoked_at`, `UNIQUE (provider, issuer, subject)`). Prefixes are in
`internal/principals/ulid.go:53-57` (`PrincipalIDPrefix = "prn_"`;
`externalIdentityIDPrefix` is unexported).

`auth.KindAgent` (`internal/auth/principal.go:48`) has exactly one reference
in the repository — the validation switch at
`internal/principals/store.go:154`. Nothing constructs
`auth.Identity{Kind: KindAgent}`. `auth.User.Identity()`
(`internal/auth/principal.go:109-129`) can only ever emit `KindService` or
`KindHuman`. `docs/principals.md:15-23` lists every caller shape and has no
`agent` row.

### Every agent run is one static admin service principal

`staticServiceUser` (`internal/auth/oidc.go:446-452`) matches the bearer token
against `MCTL_AGENT_SERVICE_TOKEN` and returns `NewServiceUser()`
(`oidc.go:114`), whose `ID` is `auth.ServiceUserID = "mctl-agent"`
(`oidc.go:247`) and whose groups include `admins`
(`LLMS.md:18`). `Identity()` maps it to
`{Provider: "service", Subject: "mctl-agent", Kind: KindService}`
(`principal.go:114`). The token is matched first in the middleware chain
(`oidc.go:523-528`), ahead of surface and usage-writer tokens.

So `agent_executions` (`internal/agentregistry/store.go:113-132`) knows which
agent version ran, and `audit_events` knows `mctl-agent` called, and nothing
joins the two: the audit row cannot name the run.

### Two-identity recording already works, on one path

The surface relay is the pattern the issue asks to generalise:

- `surfacePrincipalGate` (`internal/api/handlers_surface_identity.go:121-173`)
  is middleware on an explicit route allowlist (`surfaceRoutes`). A
  non-surface caller sending `X-MCTL-Surface-Actor` gets 400
  `actor_not_accepted`; a surface caller on a relay route has its context
  user **swapped** for the subject at lines 161-166; anything unmatched is
  403 `route_not_allowed`.
- `relaySubject` (`handlers_surface_identity.go:176-239`) resolves the
  verified link with `SurfaceIdentities.Resolve(ctx, surface, externalID)`,
  refusing `link_revoked` / `link_expired` / `link_not_found`, then builds
  `auth.NewRelayedUser(login, groups, acting)` (`oidc.go:287-302`) — subject
  as `ID`, `admins` dropped, `actingPrincipal = acting.ID`,
  `viaPrincipalID = acting.principalID` — and calls
  `auth.AttachPrincipal` to resolve the subject's own `prn_`.
- The result reaches the store as `workitems.Mutation`
  (`internal/workitems/inputs.go:15-36`), built at
  `internal/api/handlers_work_items.go:231-235`:
  `Actor: principalOf(user)`, `ActingPrincipal: user.ActingPrincipal()`,
  `ActorPrincipalID: user.PrincipalID()`,
  `ViaPrincipalID: user.ViaPrincipalID()`, `Surface: surface`.
- Audit gets the same pair automatically in
  `internal/api/clientmeta.go:172-191`, and `internal/audit/postgres.go:47-49`
  stores them as `user_principal_id` / `via_principal_id`.

Note the column convention this establishes, because it reads backwards from
the issue's vocabulary: **`actor_principal_id` holds the subject** (whose
authority is exercised) and **`via_principal_id` holds the authenticated
carrier**. This proposal keeps that convention rather than renaming columns.

### The unbound approver

`internal/api/handlers_write.go:171-196`:

```go
if opName == "mctl-agents-approve" {
    if user.IsService() {
        if input["approver"] == "" { input["approver"] = user.ID }
    } else {
        if input["approver"] != "" && input["approver"] != user.ID { /* 400 + audit */ }
        input["approver"] = user.ID
    }
}
```

Any `IsService()` caller — that is, anyone holding
`MCTL_AGENT_SERVICE_TOKEN` — may name an arbitrary approver. The value
originates in `ApproveDevLoopWorkflow`
(`internal/api/handlers_dev_loop.go:139-183`), which does take the approver
from its own authenticated caller and rejects a body-supplied one
(`:168`), but then signals Temporal with a bare
`map[string]string{"approver": approver}` (`:177-178`). By the time
the Temporal worker submits `mctl-agents-approve`, the approver is a free
string with no `prn_` and no reference back to the decision.

By contrast the newer path is already strict: `DecideActionApproval`
(`handlers_action_approvals.go:315-341`) requires `isHumanAdmin(user)`,
audits `action_approval.decision_refused` on refusal, and records
`DecidedByPrincipalID` / `DecidedViaPrincipalID`.

### Scoped, non-admin service credentials already exist

The usage writer (`internal/auth/oidc.go:321-396`) is the precedent worth
copying: `UsageWriterUserID = "service:mctl-agents-usage"`, not an admin, no
tenant, holding exactly `PermissionUsageWrite` through
`User.HasPermission` (`:347-358`), with its token refused if too short or
equal to `MCTL_AGENT_SERVICE_TOKEN` or a surface token (`:360-387`).

## Proposed solution

Four pieces, each grounded in an existing mechanism.

### 1. Agent principals (`internal/auth`, `internal/principals`)

Add `ProviderAgent = "agent"` next to `ProviderService`
(`internal/auth/principal.go:31-43`). An agent principal's identity is
`auth.Identity{Provider: "agent", Subject: "agent:<name>", Display: name,
Kind: KindAgent}` — the first production of `KindAgent`, provisioned by the
existing `principals.Store.Provision` with no schema change (the `CHECK`
already permits it).

Add to `auth.User` an unexported `agent string` plus `agentRun` metadata, and:

```go
const AgentPrincipalPrefix = "agent:"          // sibling of SurfacePrincipalPrefix
func NewAgentUser(name string, run AgentRun) *User
func (u *User) AgentName() (string, bool)
func (u *User) IsAgent() bool
func (u *User) ExecutionID() string            // "" unless agent-bound
func (u *User) AgentRunID() string             // art_...
```

`Identity()` gains an `agent` case **before** the `service` case in the
switch at `principal.go:110-128`. `IsAdmin()` is false (no `admins` group),
`Groups` empty, and route access runs through `HasPermission`, the same
mechanism the usage writer already uses. `docs/principals.md`'s caller table
gains a row: `agent run token | agent | — | agent:<name> | agent`.

### 2. Execution-scoped credentials: agent run tokens

New table in the work-items store (which already holds executions and
approvals, so no new database):

```sql
CREATE TABLE IF NOT EXISTS agent_run_tokens (
    id                   TEXT PRIMARY KEY,        -- art_<ulid>
    token_hash           BYTEA NOT NULL UNIQUE,   -- sha256, plaintext never stored
    agent                TEXT NOT NULL,
    agent_principal_id   TEXT NOT NULL DEFAULT '',
    execution_id         TEXT NOT NULL,           -- we_...
    work_item_id         TEXT NOT NULL,
    subject_principal_id TEXT NOT NULL DEFAULT '',
    subject             TEXT NOT NULL DEFAULT '',
    permissions          TEXT[] NOT NULL DEFAULT '{}',
    issued_by_principal_id TEXT NOT NULL DEFAULT '',
    created_at           TIMESTAMPTZ NOT NULL,
    expires_at           TIMESTAMPTZ NOT NULL,
    revoked_at           TIMESTAMPTZ
);
```

Route `POST /api/v1/agent-run-tokens`, the `mctl-agent` service principal
acting directly only (`isDirectService`, the gate
`ConsumeActionApproval` already uses at
`handlers_action_approvals.go:355`). Body
`{agent, execution_id, ttl_seconds?, permissions?}`. The handler:

1. rejects an unregistered `agent` against
   `agentregistry.Store` (400 `agent_unknown`);
2. loads the execution from the work-items store and refuses a terminal
   phase (409 `execution_terminal`);
3. **derives the subject server-side** from the execution's work item —
   `work_items.owner_principal_id`, falling back to the
   `requested_by_principal_id` of the execution request that fulfilled into
   this execution (`work_item_execution_requests`,
   `internal/workitems/execution_requests.go:156-158`). Nothing in the
   request body may name a subject;
4. mints `art_<ulid>` + a 32-byte random secret, stores only
   `sha256(secret)` (the same "stored hashed" shape
   `surface_identity_links` challenges use), caps `ttl_seconds` at 86400
   (default 3600), and returns the plaintext once.

Middleware: a new branch in `auth.Middleware`
(`internal/auth/oidc.go:518-529`), after the static/surface/usage-writer
matches, looks the bearer token up by hash through an
`AgentRunResolver` interface (kept in `internal/auth` so the package stays
store-free, wired in `cmd/api/main.go` like `WithPrincipalResolver` at
`:223`). A hit yields `NewAgentUser(...)` and then `AttachPrincipal`, so a
disabled agent principal is refused 403 by the existing gate
(`oidc.go:594-611`). A miss, expiry or revocation is 401 with no fallback.

Revocation is implicit as well as explicit: the resolver joins the execution
and treats a terminal phase as revoked, so a run's credential dies with the
run.

### 3. Delegation: `agentPrincipalGate` and the grant resolver

A new middleware `agentPrincipalGate`, modelled line-for-line on
`surfacePrincipalGate` (`handlers_surface_identity.go:121-173`):

- a non-agent caller sending `X-MCTL-On-Behalf-Of` gets 400
  `delegation_not_accepted`;
- an agent caller sending it on a route outside the delegation allowlist
  gets 400 `delegation_not_supported`;
- on an allowlisted route the header value is a **record id**, not a
  principal. A new `internal/delegation` package resolves it:

```go
type Grant struct {
    Ref, Kind          string // "xr_"|"aar_"|"wi_"|"surface-link"
    SubjectPrincipalID string
    Subject            string // the login/principal string, for Mutation.Actor
    ExecutionID, WorkItemID string
}
type Resolver interface { Resolve(ctx context.Context, ref string, bound AgentRun) (Grant, error) }
```

  Resolution reads the subject out of the stored record —
  `work_item_execution_requests.requested_by(_principal_id)`,
  `action_approval_requests.decided_by(_principal_id)`,
  `work_items.owner_principal(_id)`, or a `SurfaceIdentityLink` — and then
  enforces **binding**: the grant's work item or execution must equal the
  run token's. Otherwise 403 `grant_not_bound`. An empty
  `*_principal_id` (phase 1 permits `''`) is 403
  `grant_subject_unresolved`, never a string fallback.
- On success the gate swaps the context user, exactly as the surface gate
  does, for a subject user built by a new
  `auth.NewDelegatedUser(subject, groups, actingAgent)` — the same body as
  `NewRelayedUser` (`admins` dropped, `actingPrincipal` = `agent:<name>`,
  `viaPrincipalID` = the agent's `prn_`) plus the execution id.

This is what makes the constraint structural rather than a rule: an agent
cannot name a principal, only a record; and the record must already be bound
to the agent's own run.

### 4. Recording and policy fields

- `principalOf` (`handlers_work_items.go:75-83`) gains an `agent:<name>`
  case, so `Mutation.Actor` / `ActingPrincipal` render agents like every
  other principal.
- `workitems.Mutation` and `audit.Entry` each gain one field,
  `ViaExecutionID`, persisted as `via_execution_id TEXT NOT NULL DEFAULT ''`
  on `work_item_events` and `audit_events` via the
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` idiom those files already use
  (`internal/audit/postgres.go:47-49`,
  `internal/agentregistry/store.go:208-211`). `clientmeta.go:172-191` stamps
  it from `user.ExecutionID()` alongside the principal ids. No new table, no
  second trail.
- `lifecycle.WithCaller(ctx, principalID, viaPrincipalID)`
  (`internal/lifecycle/store.go:218`) is unchanged; the agent path feeds it
  the same pair.
- `ActionApprovalRequest` serves `actor_principal_id`, `actor_kind`,
  `actor_name`, `subject_principal_id`, `subject_kind`, `agent_run_id` and
  `execution_id` — the names the policy checkpoint (#197 / ADR 014) and the
  evidence envelope (mctl-agents#199) read.
- New read-only route `GET /api/v1/identity/self` (`identity/v1`) returns
  `{actor: {principal_id, kind, name}, subject: {...} | null, execution_id,
  work_item_id, agent_run_id, grant: {kind, ref} | null}`. A null `subject`
  is the machine-readable statement "acting for itself", which a policy rule
  needs to distinguish from "acting for a human". This is the first route to
  serve `prn_` values; they stay `json:"-"` everywhere else until #377.

### 5. Retiring `input["approver"]`

`handlers_write.go:171-196` is replaced by:

- any caller, any kind: `input["approver"]` present in the body → 400 (the
  human branch's behaviour, now universal);
- human admin acting directly → `approver = user.ID`,
  `approver_principal_id = user.PrincipalID()`;
- agent principal → `approval_ref` required (400 `approval_ref_required`),
  resolved by the same `delegation.Resolver` as the header. The grant must be
  a decision: an `aar_` in state `approved` or `consumed`, or the audit event
  of a `dev-loop approve` whose `WorkflowName` matches the proposal. The
  approver and `approver_principal_id` come from
  `decided_by` / `decided_by_principal_id` (or the audit row's
  `user_id` / `user_principal_id`). A non-decided, expired or mismatched
  record is 409 `approval_ref_invalid`, audited like
  `auditActionApprovalRefusal`;
- `service` principals other than agents lose the relay entirely.

To make `approval_ref` obtainable, `ApproveDevLoopWorkflow`
(`handlers_dev_loop.go:139-183`) returns the id of the audit entry it writes
and includes it in the Temporal signal payload as `approval_ref` alongside
the existing `approver` key, so the worker has a record id to present.

`MCTL_AGENTS_APPROVE_LEGACY_APPROVER=true` restores the old service branch
for one release, logging a deprecation warning and auditing
`approver.legacy_relay` on every use. Default unset.

## Alternatives

**A. One static token per agent (`MCTL_AGENT_IMPLEMENTER_TOKEN`, …),
following `surfaceTokenEnv` (`oidc.go:260-263`) exactly.** Simplest, no new
table, and it does give a distinct agent actor. Dropped because it gives no
execution scope at all — constraint 3 asks for per-execution where possible —
and because the token count grows with the agent registry, each one a
long-lived secret in Helm values with no revocation short of a redeploy. The
run-token design keeps exactly one long-lived secret
(`MCTL_AGENT_SERVICE_TOKEN`, now only a minting credential) and makes every
acting credential short-lived.

**B. A principal per execution (`prn_` for each `we_`).** The strongest form
of "distinguishable per execution", and it would need no new column on audit.
Dropped because `principals` would grow one row per agent step forever, every
one needing a `provision` round trip on a hot path, and because the
information is already in `execution_id`: a `via_execution_id` column gives
the same query with a bounded principal table. Recorded as an open question
in case the reviewer wants the stronger form.

**C. Keep `mctl-agent` as the actor and add an `X-MCTL-Agent-Name` /
`X-MCTL-Execution-Id` header pair, recorded but not authenticated.** Cheapest
by far and it would fix the audit question. Dropped because it fixes only
audit: the agent still authenticates as an admin, headers it controls become
the record, and constraint 1 is violated the moment anyone conditions policy
on them. An unauthenticated attribution header is worse than none, because
it reads as proof.

**D. Extend the surface relay to cover agents (`surface:agent`).** Reuses
everything, no new code. Dropped because the surface contract is built on
`SurfaceIdentityLink` — a human-initiated possession proof — which has no
meaning for an agent, and because `handlers_surface_identity.go:244-257`
deliberately restricts link creation to a directly-authenticated GitHub
login. Bending it would weaken a security boundary that currently holds.

## Platform impact

**Migrations.** Three additive, idempotent statements, all in the
`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
style the repo already applies at startup: the `agent_run_tokens` table in
the work-items store, and `via_execution_id TEXT NOT NULL DEFAULT ''` on
`audit_events` and `work_item_events`. No column is dropped, renamed or
backfilled. A database created before this change gets them on next start.

**Backward compatibility.** `MCTL_AGENT_SERVICE_TOKEN` keeps working for
everything it does today; agents opt in to run tokens one at a time. The one
behaviour change a caller can observe is the `mctl-agents-approve` approver
relay, which is why it ships behind
`MCTL_AGENTS_APPROVE_LEGACY_APPROVER` for one release. Every existing route,
response shape and audit column is unchanged; `prn_` values stay unserved
except on the new `GET /api/v1/identity/self`.

**Resource impact.** One extra indexed lookup per agent-authenticated
request (by `token_hash`), cacheable on the same 5-minute TTL
`principals.Resolver` uses (`resolver.go:35`). Token rows are short-lived; a
sweeper deletes expired rows on the retention schedule the work-items store
already runs.

**Risks and mitigations.**

- *Token minting becomes the new impersonation surface.* Mitigated by
  deriving the subject exclusively from the execution's own work item at mint
  time, by refusing terminal executions, and by auditing every mint with the
  minting principal (`issued_by_principal_id`).
- *A leaked run token.* Bounded by TTL (1 h default, 24 h ceiling), by the
  agent principal being non-admin and tenant-less, by the permission set on
  the row, and by implicit revocation when the execution terminates.
- *Grant confusion — an agent presenting another run's approval.* Mitigated
  by the binding check (`grant_not_bound`), which is the single place the
  whole security argument rests and therefore gets the heaviest tests.
- *Phase-1 empty principal ids.* `docs/principals.md:43-49` permits `''` when
  the store is unavailable. Delegation refuses rather than degrades
  (`grant_subject_unresolved`), which means an agent delegation fails closed
  during a principal-store outage. That is the correct trade and must be
  called out in the runbook, because it makes the principal store a hard
  dependency for delegated agent work where it is currently soft for
  everything else.
- *`internal/auth` gaining a store dependency.* Avoided by defining
  `AgentRunResolver` as an interface in `auth` and wiring the implementation
  in `cmd/api/main.go`, the shape `PrincipalResolver` already uses.
- *Scope creep into #377.* Authorization still reads `User.ID`,
  `User.Groups`, `User.IsAdmin()`, `User.HasPermission`. Nothing in this
  proposal authorizes on a `prn_`.
