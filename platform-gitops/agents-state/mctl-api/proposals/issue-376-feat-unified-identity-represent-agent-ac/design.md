# Design: issue-376-feat-unified-identity-represent-agent-ac

Revision 2. It keeps the shape of revision 1 and changes four things the
review asked for: the legacy approver relay defaults ON with a named release
order, `approval_ref` is an `aar_` id, the subject has exactly one derivation
rule (and the mint derives none), and every mint is audited.

## Current state

### The principal model exists and already has a slot for agents

`internal/principals/store.go:77-105` defines `principals` (`id`
`prn_<ulid>`, `kind` `CHECK (kind IN ('human','agent','service'))`,
`display_name`, `status`, `created_at`) and `external_identities`
(`xid_<ulid>`, `principal_id`, `provider`, `issuer`, `subject`, `display`,
`verified_at`, `revoked_at`, `UNIQUE (provider, issuer, subject)`).

`auth.KindAgent` (`internal/auth/principal.go:48`) has exactly one reference
in the repository — the validation switch `validIdentity` at
`internal/principals/store.go:150-160`. Nothing constructs
`auth.Identity{Kind: KindAgent}`. `auth.User.Identity()`
(`internal/auth/principal.go:109-129`) can only ever emit `KindService` or
`KindHuman`. `docs/principals.md:15-23` lists every caller shape and has no
`agent` row.

### Every agent run is one static admin service principal

`staticServiceUser` (`internal/auth/oidc.go:446-452`) matches the bearer token
against `MCTL_AGENT_SERVICE_TOKEN` and returns `NewServiceUser()`
(`oidc.go:114-116`), whose `ID` is `auth.ServiceUserID = "mctl-agent"` and
whose groups include `admins`. `Identity()` maps it to
`{Provider: "service", Subject: "mctl-agent", Kind: KindService}`
(`principal.go:114`). The token is matched first in the middleware chain
(`oidc.go:523-528`).

So `agent_executions` (`internal/agentregistry/store.go:113-132`) knows which
agent version ran, `audit_events` knows `mctl-agent` called, and nothing joins
the two: the audit row cannot name the run.

### Two-identity recording already works, on one path

The surface relay is the pattern the issue asks to generalise:

- `surfacePrincipalGate` (`internal/api/handlers_surface_identity.go:121-173`)
  is middleware on an explicit route allowlist (`surfaceRoutes`). A non-surface
  caller sending `X-MCTL-Surface-Actor` gets 400 `actor_not_accepted`; a
  surface caller on a relay route has its context user **swapped** for the
  subject at lines 161-166; anything unmatched is 403 `route_not_allowed`.
- `relaySubject` (`handlers_surface_identity.go:176-239`) resolves the verified
  link with `SurfaceIdentities.Resolve(ctx, surface, externalID)`, refusing
  `link_revoked` / `link_expired` / `link_not_found`, then builds
  `auth.NewRelayedUser(login, groups, acting)` (`oidc.go:287-302`) — subject as
  `ID`, `admins` dropped, `actingPrincipal = acting.ID`, `viaPrincipalID =
  acting.principalID` — and calls `auth.AttachPrincipal` for the subject's own
  `prn_`.
- The result reaches the store as `workitems.Mutation`
  (`internal/workitems/inputs.go:15-36`), built at
  `internal/api/handlers_work_items.go:231-235`. Audit gets the same pair in
  `internal/api/clientmeta.go:172-191`, stored as `user_principal_id` /
  `via_principal_id` (`internal/audit/postgres.go:47-49`).

Note the column convention, because it reads backwards from the issue's
vocabulary: **`actor_principal_id` holds the subject** (whose authority is
exercised) and **`via_principal_id` holds the authenticated carrier**. This
proposal keeps that convention rather than renaming columns.

### Action approvals are already a real grant, and the dev loop does not use them

`internal/workitems/action_approvals.go` is the machinery the review points
at, and reading it confirms it can carry a dev-loop approval:

- `aar_` ids (`:42`), schema `actionapproval/v1` (`:45`).
- A stored state machine: `pending -> approved | denied`, `approved ->
  consumed`, with `CHECK (state IN ('pending','approved','denied','consumed'))`
  (`:100-119`). `expired` is derived and structurally unstorable
  (`effectiveState`, `:265-271`).
- An expiry: `expires_at TIMESTAMPTZ NOT NULL`, capped at `MaxApprovalTTL =
  7 * 24h` (`:72`, `:337-342`).
- Single use: `ConsumeActionApproval` is one CAS —
  `WHERE id=$1 AND state='approved' AND intent_hash=$2 AND expires_at > $3`
  (`:531-534`) — so a receipt authorizes exactly one side effect however many
  callers race.
- A decided-by identity with principal ids: `ActionDecisionInput{DecidedBy,
  DecidedByPrincipalID, DecidedViaPrincipalID}` (`:452-464`), written by the
  UPDATE at `:505-509`.
- A human-admin-only decide rule, enforced at the HTTP layer:
  `isHumanAdmin(u)` = `u.IsAdmin() && !u.IsService() && !relayed && !surface`
  (`internal/api/handlers_action_approvals.go:59-64`), checked in
  `DecideActionApproval` (`:320-325`) and audited on refusal
  (`auditActionApprovalRefusal`, `:163-175`).
- A no-self-decision rule in the store: `cur.RequestedBy == in.DecidedBy` is
  `ErrApprovalSelfDecision` (`:494-496`).
- `execution_id` is a free-form external id (`checkText(..., MaxExternalIDBytes,
  required)`, `:234`) with **no `we_` prefix check** — only `work_item_id` is
  prefix-checked against `wi_` (`:252-254`). A Temporal workflow id is a legal
  `execution_id`.

Two gaps matter here. First, `actionApprovalColumns` (`:135-137`) omits all
four principal-id columns, so they are written and never read back or served:
`decided_by_principal_id` exists in the table and not in the API. Second,
`CreateActionApproval`'s 403 (`handlers_action_approvals.go:204-208`) is the
one refusal on this surface that is not audited.

### The unbound approver, and the dev-loop endpoint behind it

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

Any `IsService()` caller — anyone holding `MCTL_AGENT_SERVICE_TOKEN` — may name
an arbitrary approver. The value originates in `ApproveDevLoopWorkflow`
(`internal/api/handlers_dev_loop.go:149-227`), which does take the approver
from its own caller and rejects a body-supplied one (`:166-170`), but then
signals Temporal with a bare `map[string]string{"approver": approver}`
(`:178-181`). Three further weaknesses are visible on that handler:

- its gate is `requireTemporalAdmin` (`:42-57`), bare `user.IsAdmin()`. The
  `mctl-agent` service principal carries `admins`, so the "one place where a
  human actually performs the act of approving" currently admits the service
  principal and any relayed or surface admin — exactly what `isHumanAdmin` two
  files away exists to exclude;
- it stamps `user.ID`, not `principalOf(user)`, so the approver string has no
  `github:` / `oidc:` namespace and no `prn_` anywhere;
- it decodes with a plain `json.NewDecoder` (`:162`) — no size limit, no
  `DisallowUnknownFields`, no `forbiddenIdentityFields` check, unlike the
  work-item and action-approval paths (`handlers_work_items.go:66-70`,
  `:169-186`).

By the time the Temporal worker submits `mctl-agents-approve`, the approver is
a free string with no `prn_` and no reference back to a decision.

### Scoped, non-admin service credentials already exist

The usage writer (`internal/auth/oidc.go:321-396`) is the precedent worth
copying: `UsageWriterUserID = "service:mctl-agents-usage"`, not an admin, no
tenant, holding exactly `PermissionUsageWrite` through `User.HasPermission`
(`:347-358`), with its token refused if too short or equal to
`MCTL_AGENT_SERVICE_TOKEN` or a surface token (`:360-387`).

### Schema convention

There is no migrations directory and no `.sql` file in the repo. Schema is
embedded Go constants executed at startup with idempotent
`CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
(`internal/workitems/store.go:158-180`, `internal/audit/postgres.go:47-49`).

## Proposed solution

Five pieces, each grounded in an existing mechanism.

### 1. Agent principals (`internal/auth`, `internal/principals`)

Add `ProviderAgent = "agent"` next to `ProviderService`
(`internal/auth/principal.go:31-43`). An agent principal's identity is
`auth.Identity{Provider: "agent", Subject: "agent:<name>", Display: name,
Kind: KindAgent}` — the first production of `KindAgent`, provisioned by the
existing `principals.Store.Provision` with no schema change (the `CHECK`
already permits it, and `validIdentity` already accepts `KindAgent`).

Add to `auth.User` an unexported `agent string` plus run metadata, and:

```go
const AgentPrincipalPrefix = "agent:"          // sibling of SurfacePrincipalPrefix
func NewAgentUser(name string, run AgentRun) *User
func (u *User) AgentName() (string, bool)
func (u *User) IsAgent() bool
func (u *User) ExecutionID() string            // "" unless agent-bound
func (u *User) WorkItemID() string
func (u *User) AgentRunID() string             // art_...
```

`Identity()` gains an `agent` case **before** the `service` case in the switch
at `principal.go:110-128`. `IsAdmin()` is false (no `admins` group), `Groups`
is empty, `IsService()` is false — which matters, because `isDirectService`
(`handlers_action_approvals.go:52-55`) must not start matching agents. Route
access runs through `HasPermission`, the mechanism the usage writer already
uses. `docs/principals.md`'s caller table gains a row:
`agent run token | agent | — | agent:<name> | agent`.

**Reserved provider name (review finding 4).** `agent` must be reserved in the
#374 federation provider registry, refused at boot, so no configured OIDC or
opaque provider can mint identities in the `(agent, ...)` namespace and
impersonate an agent principal. The #374 proposal already lists this
reservation; this design depends on it and states the dependency rather than
silently assuming it. If #374 lands after this work, the reservation is a
one-line constant here and moves into the registry when the registry exists.

### 2. Execution-scoped credentials: agent run tokens

New table in the work-items store (which already holds executions and
approvals, so no new database):

```sql
CREATE TABLE IF NOT EXISTS agent_run_tokens (
    id                     TEXT PRIMARY KEY,        -- art_<ulid>
    token_hash             BYTEA NOT NULL UNIQUE,   -- sha256; plaintext never stored
    agent                  TEXT NOT NULL,
    agent_principal_id     TEXT NOT NULL DEFAULT '',
    execution_id           TEXT NOT NULL,           -- we_...
    work_item_id           TEXT NOT NULL,           -- wi_...
    permissions            TEXT[] NOT NULL DEFAULT '{}',
    issued_by_principal_id TEXT NOT NULL DEFAULT '',
    created_at             TIMESTAMPTZ NOT NULL,
    expires_at             TIMESTAMPTZ NOT NULL,
    revoked_at             TIMESTAMPTZ
);
```

**There is deliberately no `subject_principal_id` column.** Revision 1 had one,
and the review was right that it created a second, competing subject rule. The
token binds *the agent, the execution and the work item* and nothing else.

Route `POST /api/v1/agent-run-tokens`, `isDirectService` only
(`handlers_action_approvals.go:52-55`). Body
`{agent, execution_id, ttl_seconds?, permissions?}`. The handler:

1. rejects an unregistered `agent` against `agentregistry.Store`
   (400 `agent_unknown`);
2. loads the execution from the work-items store and refuses a terminal phase
   (409 `execution_terminal`), taking `work_item_id` from the execution;
3. mints `art_<ulid>` + a 32-byte random secret, stores only `sha256(secret)`,
   caps `ttl_seconds` at 86400 (default 3600), returns the plaintext once;
4. **audits the mint** (review finding 5) as `agent_run_token.mint`:
   `{token_id, agent, agent_principal_id, execution_id, work_item_id,
   ttl_seconds, expires_at, permissions, issued_by_principal_id}` and never
   the plaintext. Refusals audit as `agent_run_token.mint_refused` with the
   typed code, the shape `auditActionApprovalRefusal` uses
   (`handlers_action_approvals.go:163-175`). Minting stays with the static
   admin token, so the mint is the one remaining place where the broad
   credential is exercised; it therefore gets the record.

Middleware: a new branch in `auth.Middleware` (`internal/auth/oidc.go:518-529`),
after the static/surface/usage-writer matches, looks the bearer token up by
hash through an `AgentRunResolver` interface (kept in `internal/auth` so the
package stays store-free, wired in `cmd/api/main.go` like
`WithPrincipalResolver`). A hit yields `NewAgentUser(...)` then
`AttachPrincipal`, so a disabled agent principal is refused by the existing
gate (`oidc.go:594-611`). A miss, expiry or revocation is 401 with no fallback.
Revocation is implicit as well as explicit: the resolver joins the execution
and treats a terminal phase as revoked, so a run's credential dies with the run.

### 3. Delegation: one rule, stated once

**The rule.**

> The mint binds the execution and the work item. The `X-MCTL-On-Behalf-Of`
> header only *selects* a grant already bound to that execution or that work
> item. The subject is always read from the selected grant row.

Nothing else may produce a subject. The token carries none; the header carries
a record id, not a principal; the body is rejected outright. This is what
makes constraint 1 structural rather than a rule someone must remember.

A new middleware `agentPrincipalGate`, modelled line-for-line on
`surfacePrincipalGate` (`handlers_surface_identity.go:121-173`):

- a non-agent caller sending `X-MCTL-On-Behalf-Of` gets 400
  `delegation_not_accepted`;
- an agent caller sending it on a route outside the delegation allowlist gets
  400 `delegation_not_supported`;
- on an allowlisted route a new `internal/delegation` package resolves the
  record id:

```go
type Grant struct {
    Ref, Kind               string // "xr_" | "aar_" | "wi_" | "surface-link"
    SubjectPrincipalID      string
    Subject                 string // the principal string, for Mutation.Actor
    ExecutionID, WorkItemID string
}
type Resolver interface {
    Resolve(ctx context.Context, ref string, bound AgentRun) (Grant, error)
}
```

Resolution reads the subject out of the stored record —
`work_item_execution_requests.requested_by(_principal_id)`,
`action_approval_requests.decided_by(_principal_id)`,
`work_items.owner_principal(_id)`, or a `surfaceid` link — and then enforces
**binding**: the grant's execution id or work item id must equal the run
token's. Otherwise 403 `grant_not_bound`. An empty `*_principal_id` (phase 1
permits `''`) is 403 `grant_subject_unresolved`, never a string fallback.

On success the gate swaps the context user, exactly as the surface gate does,
for a subject user built by `auth.NewDelegatedUser(subject, groups,
actingAgent)` — the same body as `NewRelayedUser` (`oidc.go:287-302`): `admins`
dropped, `actingPrincipal = "agent:<name>"`, `viaPrincipalID` = the agent's
`prn_`, plus the execution id.

The consequence the review asked to be explicit about: **the work item's own
owner is never consulted at request time.** If a work item is owned by Alice
and the presented grant is an `xr_` requested by Bob, the subject is Bob. The
grant is the authority; the work item is only the binding scope. That is one
of the tests (T3b).

### 4. Recording and policy fields

- `principalOf` (`handlers_work_items.go:75-83`) gains an `agent:<name>` case.
- `workitems.Mutation` and `audit.Entry` each gain one field, `ViaExecutionID`,
  persisted as `via_execution_id TEXT NOT NULL DEFAULT ''` on
  `work_item_events` and `audit_events` via the existing
  `ADD COLUMN IF NOT EXISTS` idiom. `clientmeta.go:172-191` stamps it from
  `user.ExecutionID()` alongside the principal ids. No new table, no second
  trail.
- `actionApprovalColumns` (`action_approvals.go:135-137`) is extended with the
  four principal-id columns that are already written but never read back, and
  `ActionApprovalRequest` gains `RequestedByPrincipalID`, `ViaPrincipalID`,
  `DecidedByPrincipalID`, `DecidedViaPrincipalID`, plus `ActorKind`,
  `ActorName`, `SubjectPrincipalID`, `SubjectKind` and `AgentRunID`. These are
  the names the policy checkpoint (#197 / ADR 014) and the evidence envelope
  (mctl-agents#199) read.
- New read-only route `GET /api/v1/identity/self` (`identity/v1`) returns
  `{actor: {principal_id, kind, name}, subject: {...} | null, execution_id,
  work_item_id, agent_run_id, grant: {kind, ref} | null}`. A null `subject` is
  the machine-readable statement "acting for itself", which a policy rule needs
  in order to distinguish it from "acting for a human".

### 5. Retiring `input["approver"]` via an `aar_`

**The grant is an `ActionApprovalRequest`, not an audit row** (review finding
2). Revision 1 proposed reading the dev-loop approve audit entry's id as the
`approval_ref`. That was wrong for the reason the review gives: audit rows are
evidence. They have no state machine, no expiry, no single-use rule, and
`internal/audit` has no compare-and-set. Reading one as an authorization source
would mean a leaked audit id is a replayable approval forever. `aar_` already
has all four properties, and the mapping is exact:

| dev-loop approval | `ActionApprovalRequest` field |
| --- | --- |
| which DevLoop | `execution_id` = the Temporal workflow id (free-form; no `we_` check at `:234`) |
| what is approved | `action_kind` = `"mctl-agents-approve"`, `target` = `"<service>/<slug>"` |
| binding | `args_digest` = sha256 of the canonical `{service, slug}`; `intent_hash` over the whole intent |
| who asked | `requested_by` = `"service:mctl-agent"` |
| who approved | `decided_by`, `decided_by_principal_id` |
| still valid? | `state` + `expires_at`, lazily expired |
| spent? | `state = consumed`, set by the CAS at `:531-534` |
| policy | `policy_rule_id` = `"dev-loop.human-approval"`, `policy_version` = `"v1"` until #197 supplies a real rule |

The flow:

1. At its approval gate, the Temporal worker (direct `mctl-agent` service
   principal) creates the `aar_` through the existing
   `POST /api/v1/action-approvals`. No new create route.
2. A human admin calls `POST /api/v1/agents/dev-loop/{workflow_id}/approve`.
   The handler finds the pending `aar_` for that `execution_id` and
   `action_kind` and decides it through the existing
   `WorkItems.DecideActionApproval` — so `DecidedBy`,
   `DecidedByPrincipalID` and `DecidedViaPrincipalID` are written by the same
   code path and the same rules as the generic decide route. It then signals
   Temporal with `{approver, approval_ref: "aar_...", reason?}`.
   - If no pending `aar_` exists (an older worker, or a manual approve), the
     handler **creates one server-side** with `requested_by =
     "service:mctl-agent"` and then decides it. Because the requester is the
     service and the decider is the human, `ErrApprovalSelfDecision`
     (`:494-496`) does not fire.
   - `requireTemporalAdmin` (`handlers_dev_loop.go:42-57`) is tightened from
     bare `IsAdmin()` to `isHumanAdmin`, so the service principal can no
     longer perform the human act. The handler also switches to
     `principalOf(user)` and to the `decodeWorkItemBodyLimit` +
     `forbiddenIdentityFields` decoding the rest of the API uses.
3. The worker submits `mctl-agents-approve` with `approval_ref` and no
   `approver`. The handler loads the `aar_`, recomputes
   `IntentHash(ActionIntent{ExecutionID, ActionKind: "mctl-agents-approve",
   Target: service+"/"+slug, ...})` from the *operation input it was actually
   given*, and calls `WorkItems.ConsumeActionApproval(ctx, ref, intentHash)`.
   The CAS refuses anything not `approved`, not matching the intent, or
   expired, and spends it exactly once. `approver` and
   `approver_principal_id` come from `decided_by` / `decided_by_principal_id`.

Two notes on this step. The handler calls the **store** method, not the HTTP
`/consume` route, whose `isDirectService` gate (`:351-361`) is unchanged and
would not match an agent principal. And this binding is by *intent* (service +
slug), which is deliberately a different binding from the header path's
(execution + work item): the `aar_`'s `execution_id` is a Temporal workflow id,
not the agent's `we_`. Both are server-side; neither reads a subject from the
caller. Naming both explicitly is the point of finding 3.

**Rollout (review finding 1).** `MCTL_AGENTS_APPROVE_LEGACY_APPROVER` defaults
to **`true`**. Revision 1 defaulted it off, which would have made the mctl-api
release reject the `approver` the current worker sends and break every DevLoop
approval until mctl-agents shipped. With the default on, the mctl-api release
is behaviour-neutral for existing callers:

1. **mctl-api release, legacy on.** Run tokens, delegation, `approval_ref`,
   `identity/self` all available; the old `approver` relay still accepted, and
   audited as `approver.legacy_relay` on every single use — approver string,
   calling principal, operation — so the verify step is a query, not a guess.
2. **mctl-agents release.** The worker mints run tokens, creates the `aar_` at
   the approval gate, reads `approval_ref` off the signal, submits
   `mctl-agents-approve` with `approval_ref` and no `approver`, and sends
   `X-MCTL-On-Behalf-Of` where it acts for a human. These tasks are C4-C8
   below; no mctl-agents issue carries them today.
3. **Verify.** Zero `approver.legacy_relay` audit entries across a full DevLoop
   cycle (a week of the Saturday cron plus at least one issue-triggered loop).
4. **mctl-api follow-up release**, flipping the default to `false`. The env var
   survives one more release as an escape hatch, then is deleted.

## Alternatives

**A. One static token per agent (`MCTL_AGENT_IMPLEMENTER_TOKEN`, …), following
`surfaceTokenEnv` (`oidc.go:260-263`).** Simplest, no new table, and it does
give a distinct agent actor. Dropped because it gives no execution scope at all
— constraint 3 asks for per-execution where possible — and because the token
count grows with the agent registry, each one a long-lived secret in Helm
values with no revocation short of a redeploy.

**B. A principal per execution (`prn_` for each `we_`).** The strongest form of
"distinguishable per execution", and it would need no new audit column. Dropped
because `principals` would grow one row per agent step forever, every one
needing a provision round trip on a hot path, while `via_execution_id` gives
the same query with a bounded principal table. Recorded as an open question.

**C. Keep `mctl-agent` as the actor and add an `X-MCTL-Agent-Name` /
`X-MCTL-Execution-Id` header pair, recorded but not authenticated.** Cheapest
by far. Dropped because it fixes only audit: the agent still authenticates as
an admin, headers it controls become the record, and constraint 1 is violated
the moment anyone conditions policy on them. An unauthenticated attribution
header is worse than none, because it reads as proof.

**D. A dedicated `dev_loop_approvals` record instead of `aar_`.** The review
allows this only if `aar_` cannot express the approval. It can: the table above
maps every field, `execution_id` accepts a Temporal workflow id because it is
not prefix-checked (`action_approvals.go:234`, contrast `:252-254`), and state,
expiry, single-use consume and the human-admin decide rule already exist and
are already tested. A second record would duplicate all of it and give the
policy checkpoint two places to look. Dropped.

**E. Extend the surface relay to cover agents (`surface:agent`).** Reuses
everything. Dropped because the surface contract is built on
`SurfaceIdentityLink` — a human-initiated possession proof — which has no
meaning for an agent, and because `handlers_surface_identity.go:244-257`
deliberately restricts link creation to a directly-authenticated GitHub login.

## Platform impact

**Migrations.** Additive and idempotent, in the style the repo already applies
at startup: the `agent_run_tokens` table in the work-items store, and
`via_execution_id TEXT NOT NULL DEFAULT ''` on `audit_events` and
`work_item_events`. No column is dropped, renamed or backfilled. Extending
`actionApprovalColumns` adds no column — it reads four that already exist.

**Backward compatibility.** `MCTL_AGENT_SERVICE_TOKEN` keeps working for
everything it does today; agents opt in to run tokens one at a time. With
`MCTL_AGENTS_APPROVE_LEGACY_APPROVER` defaulting on, the mctl-api release
changes no caller's observable behaviour except two tightenings, both of which
only ever refuse a caller that should not have been there:

- `requireTemporalAdmin` becomes `isHumanAdmin`, so a service principal can no
  longer call the dev-loop approve endpoint. Confirm before shipping that no
  automation calls it with `MCTL_AGENT_SERVICE_TOKEN`; if any does, that is the
  bug this issue exists for, and it is caught in verify step 3.
- The dev-loop approve body gains `DisallowUnknownFields`, so a caller sending
  stray keys now gets a 400. Today's worker sends only `approver` and `reason`.

`prn_` values stay unserved except on `GET /api/v1/identity/self` and the
extended `ActionApprovalRequest` payload.

**Resource impact.** One extra indexed lookup per agent-authenticated request
(by `token_hash`), cacheable on the same 5-minute TTL `principals.Resolver`
uses (`resolver.go:35`). One extra `aar_` row per DevLoop approval — the table
is already indexed on `(execution_id, created_at DESC)` and
`(state, created_at DESC)`. Run-token rows are short-lived; a sweeper deletes
expired rows on the retention schedule the work-items store already runs.

**Risks and mitigations.**

- *Token minting becomes the new broad credential.* Mitigated by the token
  binding nothing but execution and work item (it confers no subject at all),
  by refusing terminal executions, by the TTL ceiling, and by auditing every
  mint and every refused mint.
- *A leaked run token.* Bounded by TTL (1 h default, 24 h ceiling), by the
  agent principal being non-admin and tenant-less, by the permission set on the
  row, and by implicit revocation when the execution terminates. A leaked token
  still cannot name a subject: it must present a grant already bound to its own
  execution.
- *Grant confusion — an agent presenting another run's approval.* Mitigated by
  the binding check (`grant_not_bound`), which is where the whole security
  argument rests and therefore gets the heaviest tests (T3).
- *A replayed `approval_ref`.* Mitigated by the consume CAS: the second use
  finds `state = 'consumed'` and is `ErrApprovalConsumed` → 409. This is the
  concrete property an audit-row ref could not have provided.
- *Rollout skew.* The legacy default being on is what removes it. The residual
  risk is the opposite one — that the flag is never turned off — so verify step
  3 is a named gate with a query behind it, and the flag is deleted one release
  after it flips.
- *Phase-1 empty principal ids.* `docs/principals.md:43-49` permits `''` when
  the store is unavailable. Delegation refuses rather than degrades
  (`grant_subject_unresolved`), which means delegated agent work fails closed
  during a principal-store outage while everything else degrades. That is the
  correct trade and must be in the runbook.
- *`internal/auth` gaining a store dependency.* Avoided by defining
  `AgentRunResolver` as an interface in `auth` and wiring the implementation in
  `cmd/api/main.go`, the shape `PrincipalResolver` already uses.
- *Scope creep into #377.* Authorization still reads `User.ID`, `User.Groups`,
  `User.IsAdmin()`, `User.HasPermission`. Nothing here authorizes on a `prn_`.
