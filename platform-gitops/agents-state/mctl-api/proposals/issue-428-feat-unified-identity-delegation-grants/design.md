# Design: issue-428-feat-unified-identity-delegation-grants

This implements Slice B of the accepted proposal
`issue-376-feat-unified-identity-represent-agent-ac` (design.md section 3,
tasks.md B1-B3). It does not re-design it. Where the accepted proposal left a
detail unstated, this document names the gap, picks the narrowest reading, and
records it in requirements.md's open questions.

## Current state

### Slice A landed; the agent principal exists and carries no subject

`internal/auth/agent.go` defines `AgentRunTokenPrefix = "art_"`,
`ErrAgentRunNotFound`, the `AgentRun` struct (`Agent`, `ExecutionID`,
`WorkItemID`, `RunID`, `Permissions`) and the `AgentRunResolver` interface.
`NewAgentUser` (`agent.go:76-85`) builds a `*auth.User` with the unexported
`agent`, `execID`, `workItemID`, `runID` and `agentPermissions` fields set and
nothing else: no groups, no `service`, no `surface`. `User.Identity()`
(`principal.go:118-124`) checks `u.agent != ""` **first**, ahead of every other
discriminator, and returns `Kind: KindAgent`. `HasPermission`
(`oidc.go:402-413`) short-circuits to the run token's own permission list for
an agent, so an agent gets nothing implicitly.

The header comment at `agent.go:29-32` is the load-bearing statement for this
slice:

> a run token carries no subject: it cannot say who the agent is acting for.
> Delegation (the X-MCTL-On-Behalf-Of header, mctl-api#376 slice B) is a
> separate mechanism layered on top, not part of authentication.

`AgentRun` has no subject field and `agent_run_tokens` has no subject column
(A4's DoD). So there is today no code path by which an agent request can name a
human — which is exactly the property Slice B must extend without breaking.

Recording is already in place from A8: `audit.Entry.ViaExecutionID`
(`internal/audit/logger.go:49-52`), the `via_execution_id` column
(`internal/audit/postgres.go:53`, written at `postgres.go:115-121`),
`workitems.Mutation.ViaExecutionID` (`internal/workitems/inputs.go:27-30`),
stamped from `user.ExecutionID()` in `clientmeta.go:190-191` and
`handlers_work_items.go:237`. Nothing new needs persisting for Slice B.

### The surface relay is the template, line for line

`surfacePrincipalGate` (`internal/api/handlers_surface_identity.go:121-171`) is
the shape B2 copies:

1. no context user -> pass through;
2. not a surface principal -> if it nevertheless sent `X-MCTL-Surface-Actor`,
   400 `actor_not_accepted`; else pass through;
3. walk `surfaceRoutes` (`:81-99`), a slice of
   `{method string, pattern *regexp.Regexp, relay bool}`;
4. on a `relay: true` match, `h.relaySubject` resolves the human and the gate
   calls `next.ServeHTTP(w, r.WithContext(auth.WithUser(ctx, subject)))`;
5. no match -> 403 `surface_route_not_allowed`.

`relaySubject` (`:176-239`) is the subject-resolution template: every gap fails
closed with a typed code and an `surface_identity.relay_refused` audit entry
(`:180-186`); the `github:` prefix is stripped with `strings.CutPrefix` and a
non-GitHub principal is refused (`:208-211`); a failed tenant lookup grants no
groups (`:213-221`); `auth.NewRelayedUser` builds the subject; and
`auth.AttachPrincipal` is run with `ErrPrincipalDisabled` /
`ErrIdentityRefused` mapped to typed refusals and every other error degrading
to "no principal id" (`:229-237`).

`auth.NewRelayedUser` (`internal/auth/oidc.go:334-349`) is what
`NewDelegatedUser` must be a sibling of: it returns nil unless the acting user
is a surface principal and the login is non-empty, filters `admins` out of the
groups, and sets `ID`, `Groups`, `githubLogin: true`, `actingPrincipal`,
`relaySurface` and `viaPrincipalID` — and nothing else.

The gate is mounted in `router.go:321` inside the authenticated group, below
`surfaceAggregateLimit` (`:312-315`) and `middleware.Timeout(30s)` (`:319`) —
the ordering comments at `:310-320` say explicitly that the gate goes under the
timeout because relay resolves a link in Postgres, and under the aggregate
limiter because a refused relay still costs a lookup. Delegation has the same
cost profile.

### The four grant sources all exist, and none of them reads its principal id back

| source | id prefix | subject string | subject principal id |
| --- | --- | --- | --- |
| `work_item_execution_requests` | `xr_` (`execution_requests.go:45`) | `requested_by` (`:129`) | `requested_by_principal_id` (`:156`) |
| `action_approval_requests` | `aar_` (`action_approvals.go:42`) | `decided_by` (`:117`) | `decided_by_principal_id` (`:131`) |
| `work_items` | `wi_` (`types.go:25`) | `owner_principal` (`store.go:20`) | `owner_principal_id` (`store.go:126`) |
| `surface_identity_links` | `sil_` (`surfaceid/store.go:392`) | `Link.Principal` (`store.go:109`) | — none stored |

The important fact: **the `*_principal_id` columns are written but never read
back.** `executionRequestColumns` (`execution_requests.go:161-164`),
`actionApprovalColumns` (`action_approvals.go:135-137`) and `itemColumns`
(`store.go:137`) all omit them, and their scanners
(`scanExecutionRequest` `:204-215`, `scanActionApproval` `:277`,
`scanItem` `:214`) do not read them. Widening those lists is the accepted
proposal's **D1**, which this issue puts out of scope. So Slice B cannot get its
subject principal id through `Store.ExecutionRequest`, `Store.ActionApproval`
or `Store.Get`.

`Store.ExecutionRequest(ctx, itemID, id)` (`execution_requests.go:404`) also
requires a work item id, which shapes the interface below.

A surface link has no principal id at all. What it has is a *mirror*:
`principals.Store.MirrorLink` (`internal/principals/mirror.go:41-84`) copies a
live link into `external_identities` as
`(provider=<surface>, issuer='', subject=<external id>)` pointing at the
human's `prn_`. `surfaceid.Store.Resolve(ctx, surface, externalID)`
(`store.go:459`) already applies revocation and expiry, returning
`ErrLinkRevoked` / `ErrLinkExpired` / `ErrLinkNotFound`.

A surface link also has neither an execution nor a work item, so the accepted
proposal's binding rule ("the grant's execution id or work item id must equal
the run token's") has nothing to compare. The binding that does exist is
`work_item_surface_refs` (`internal/workitems/store.go:88-96`), whose
`actor_external_id` column is documented at `types.go:237-239` as "correlation
metadata, never identity: it resolves to a principal only through a
SurfaceIdentityLink (mctl-api#350)". That is precisely this resolution, so that
is the binding we use.

### Body-field refusal exists and is nearly complete

`forbiddenIdentityFields` (`handlers_work_items.go:64-70`) already lists
`on_behalf_of`, `subject` and `delegated_actor`. It is missing exactly one of
B3's four names: `acting_principal`. `decodeWorkItemBodyLimit`
(`:162-191`) applies the list, refuses unknown fields and refuses trailing
data; `MintAgentRunToken` already decodes through it
(`handlers_agent_run_tokens.go:118`), so the agent-run-token half of B3 is a
one-word change plus a test.

The dev-loop approve route does **not**. `ApproveDevLoopWorkflow`
(`handlers_dev_loop.go:308-340`) decodes with a bare, EOF-tolerant
`json.NewDecoder(r.Body)` at `:321` with no `DisallowUnknownFields`, so a body
carrying `subject` or `acting_principal` is silently ignored today. Replacing
that decoder wholesale is the accepted proposal's **C2** (out of scope), which
also tightens `requireTemporalAdmin` and changes the recorded approver. So B3
needs an additive check, not a replacement.

The additive pattern already exists in this package:
`refuseExecutionIdentity` (`handlers_execution_requests.go:58-76`) reads the
body with `readWorkItemBody`, unmarshals into a `map[string]json.RawMessage`,
refuses the listed keys, and then calls `restoreBody(r, raw)` so the real
decoder still sees the bytes. That is exactly the hook B3 needs.

Finally, `handlers_human_input_response.go:490` also uses a bare
`json.NewDecoder(http.MaxBytesReader(...))`, so if
`POST /human-input/{request_id}/response` is on the delegation allowlist it
needs the same additive check.

## Proposed solution

Three changes, in the order B1 -> B2 -> B3.

### B1. `internal/delegation`: `Grant`, `Resolver`, and the binding rule

A new package, deliberately **store-free**, following the shape
`internal/auth` already uses for `AgentRunResolver`: the package defines the
types, the errors and the interfaces; `internal/workitems` and
`internal/surfaceid` implement the sources; `cmd/api/main.go` wires them. That
keeps `internal/delegation` unit-testable with fakes and keeps SQL where SQL
already lives.

```go
package delegation

// Kinds, keyed on the ref's own id prefix.
const (
    KindExecutionRequest = "execution_request" // xr_
    KindActionApproval   = "action_approval"   // aar_
    KindWorkItem         = "work_item"         // wi_
    KindSurfaceLink      = "surface_link"      // sil_
)

// Grant is a stored record that names a subject and is bound to an
// execution or a work item. Every field comes from a store row.
type Grant struct {
    Ref, Kind          string
    Subject            string // the namespaced principal string, e.g. "github:alice"
    SubjectPrincipalID string // prn_...; never "" in a returned Grant
    ExecutionID        string
    WorkItemID         string
}

var (
    ErrNotBound          = errors.New("delegation: grant is not bound to this run")
    ErrSubjectUnresolved = errors.New("delegation: grant subject has no principal")
    ErrUnavailable       = errors.New("delegation: a grant source is unavailable")
)

// Resolver turns a ref into a Grant bound to the presenting run token.
// Resolve takes the ref and the token binding and NOTHING else: there is
// structurally no argument through which a caller-supplied subject could
// enter (T3d).
type Resolver interface {
    Resolve(ctx context.Context, ref string, bound auth.AgentRun) (Grant, error)
}

// Record is the projection a source returns: the four grant fields, and no
// more of the row than that.
type Record struct {
    Subject, SubjectPrincipalID, ExecutionID, WorkItemID string
}

// Sources. Each is implemented by the store that owns the table.
type WorkItemSource interface {
    ExecutionRequestGrant(ctx context.Context, itemID, id string) (Record, error)
    ActionApprovalGrant(ctx context.Context, id string) (Record, error)
    WorkItemGrant(ctx context.Context, id string) (Record, error)
    // SurfaceRefBound reports whether the work item carries a surface ref
    // for (surface, actorExternalID) -- the binding for a surface link.
    SurfaceRefBound(ctx context.Context, itemID, surface, actorExternalID string) (bool, error)
}
type SurfaceLinkSource interface {
    LinkByID(ctx context.Context, id string) (surface, externalID, principal string, err error)
}
```

`StoreResolver` is the one concrete implementation. `Resolve`:

1. dispatches on the ref's prefix with `strings.HasPrefix`; an unrecognised
   prefix is `ErrNotBound` without touching a store;
2. loads the `Record` from that one source. `xr_` is loaded with the run
   token's `bound.WorkItemID` as `itemID`, which uses
   `getExecutionRequest`'s existing `AND work_item_id=$2` narrowing
   (`execution_requests.go:216-224`) and makes the work-item half of the
   binding a property of the query rather than a later comparison;
3. a not-found row is `ErrNotBound` — never a distinct "no such grant" code, so
   the route is not an id-existence oracle. Any other store error is
   `ErrUnavailable`;
4. enforces binding: `rec.ExecutionID == bound.ExecutionID ||
   rec.WorkItemID == bound.WorkItemID`, with empty-string matches excluded so
   two unset ids never "agree". Otherwise `ErrNotBound`;
5. for `sil_`, binding is instead `SurfaceRefBound(bound.WorkItemID,
   link.surface, link.externalID)`, and the subject principal id comes from the
   gate (see B2) because a link row does not store one;
6. `rec.SubjectPrincipalID == ""` is `ErrSubjectUnresolved`. There is no branch
   that falls back to `rec.Subject`.

The four source methods are new, narrow `SELECT`s on the store side —
`workitems.Store.ExecutionRequestGrant` etc. — each projecting exactly the four
`Record` columns. They deliberately do **not** widen
`executionRequestColumns` / `actionApprovalColumns` / `itemColumns`: that is
D1's job, it changes public read payloads, and Slice B has no business changing
them. A narrow projection also means the resolver never holds a row it must not
expose (a claim token, an intent hash).

The consequence design.md asks to be explicit about is preserved by
construction: step 4 compares ids only, and step 6 reads
`rec.SubjectPrincipalID` only. A run token minted on `wi_X` owned by Alice,
presenting an `xr_` bound to `wi_X` but `requested_by` Bob, yields Bob. The
work item's owner is consulted only when the ref *is* the `wi_`.

### B2. `agentPrincipalGate` in `internal/api/handlers_agent_identity.go`

A new file, modelled on `handlers_surface_identity.go`. It carries:

```go
// OnBehalfOfHeader names the grant an agent run is acting under. It carries
// a RECORD ID, never a principal: the subject is read from the record.
const OnBehalfOfHeader = "X-MCTL-On-Behalf-Of"

const (
    delegationCodeNotAccepted  = "delegation_not_accepted"
    delegationCodeNotSupported = "delegation_not_supported"
    delegationCodeNotBound     = "grant_not_bound"
    delegationCodeUnresolved   = "grant_subject_unresolved"
    delegationCodeUnavailable  = "delegation_unavailable"
)

type delegationRoute struct{ method string; pattern *regexp.Regexp }
var delegationRoutes = []delegationRoute{ ... }
```

`delegationRoutes` is the narrowest set that makes the worker-side C7 possible
— the routes a relayed human can already reach (`surfaceRoutes:84-98`) minus
the ones where there is no prior grant to bind to:

- `POST /api/v1/work-items/{id}/intents`
- `POST /api/v1/work-items/{id}/surface-refs`
- `POST /api/v1/work-items/{id}/execution-requests`
- `POST /api/v1/human-input/{request_id}/response`
- `GET  /api/v1/work-items/{id}`
- `GET  /api/v1/human-input`, `GET /api/v1/human-input/{request_id}`

`POST /api/v1/work-items` is excluded on purpose: creation *names* an owner, so
by definition no grant predates it. `POST /agent-run-tokens`,
`/agents/dev-loop/*`, `/operations/{name}/execute` and `/surface-identities/*`
are excluded as privileged or identity-establishing.

The gate body, in `surfacePrincipalGate`'s order:

1. no context user, or no `X-MCTL-On-Behalf-Of` header -> `next.ServeHTTP`
   unchanged. An agent acting for itself is unaffected, which is what keeps this
   change additive;
2. `user.AgentName()` false -> 400 `delegation_not_accepted`, audited. This one
   check covers a human, a surface principal, a relayed subject, the service
   principal, the usage writer and the evidence writer, because `AgentName()`
   reads the unexported `agent` field that only `NewAgentUser` sets
   (`oidc.go:110-118`);
3. no `delegationRoutes` match -> 400 `delegation_not_supported`, audited;
4. `h.opts.Delegation == nil` -> 503 `delegation_unavailable`;
5. `h.opts.Delegation.Resolve(ctx, ref, auth.AgentRun{Agent: name,
   ExecutionID: user.ExecutionID(), WorkItemID: user.WorkItemID(),
   RunID: user.AgentRunID()})`. `ErrNotBound` -> 403 `grant_not_bound`;
   `ErrSubjectUnresolved` -> 403 `grant_subject_unresolved`; `ErrUnavailable`
   -> 503 `delegation_unavailable`. The first two are audited;
6. `strings.CutPrefix(grant.Subject, "github:")`, exactly as
   `relaySubject:208-211`. Not a GitHub principal -> 403
   `grant_subject_unresolved`;
7. tenant groups via `h.opts.TenantResolver.GetTenantsForUser(login)`, with a
   failed lookup granting none (`relaySubject:213-221`);
8. `subject := auth.NewDelegatedUser(login, groups, user)`;
9. `auth.AttachPrincipal(ctx, h.opts.Principals, subject)`. Unlike the relay,
   delegation **fails closed** on any error: `ErrPrincipalDisabled` and
   `ErrIdentityRefused` are typed 403s as in the relay, and every other error
   is 503 `delegation_unavailable` rather than "proceed without a principal
   id". The whole point of the slice is a recorded subject, so a request that
   cannot record one must not run. This asymmetry with `relaySubject:236` is
   deliberate and is the runbook note D4 already anticipates;
10. assert `subject.PrincipalID() == grant.SubjectPrincipalID`; a mismatch is
    403 `grant_subject_unresolved` and audited. This is the one place the two
    independent derivations of the subject's principal (the stored column and
    the live resolver) are cross-checked, and it is also how a `sil_` grant —
    whose `Record.SubjectPrincipalID` the store cannot supply — gets its
    principal id: for `KindSurfaceLink` the resolver returns the id it
    obtained from the mirror lookup, or `ErrSubjectUnresolved`;
11. `next.ServeHTTP(w, r.WithContext(auth.WithUser(ctx, subject)))`.

Every refusal goes through one helper, `refuseDelegation(w, r, acting, ref,
code, status, msg)`, which writes one audit entry:

```go
audit.Entry{
    UserID: acting.ID, Operation: "agent_identity.delegation_refused",
    Status: "failed", RiskLevel: string(operations.RiskMedium),
    Parameters: map[string]string{
        "acting_principal": acting.ID, "agent": name, "grant_ref": ref,
        "route": r.Method + " " + r.URL.Path, "reason": code,
    },
}
```

shaped after `relaySubject`'s `refuse` closure (`:179-187`). `grant_ref` is a
record id, never a secret, so it is safe to audit.

`auth.NewDelegatedUser` goes in `internal/auth/oidc.go` next to
`NewRelayedUser`:

```go
func NewDelegatedUser(login string, groups []string, acting *User) *User {
    name, isAgent := acting.AgentName()
    if !isAgent || login == "" {
        return nil
    }
    kept := make([]string, 0, len(groups))
    for _, g := range groups {
        if g != "admins" { kept = append(kept, g) }
    }
    return &User{
        ID: login, Groups: kept, githubLogin: true,
        actingPrincipal: AgentPrincipalPrefix + name,
        viaPrincipalID:  acting.principalID,
        execID: acting.execID, workItemID: acting.workItemID, runID: acting.runID,
    }
}
```

Three properties matter. It does **not** set `agent`, so the delegated user is
not an agent principal and `Identity()` returns `KindHuman` through the
`githubLogin` case — the subject is a human, recorded as one. It does **not**
set `relaySurface`, so `isDirectService` / `isHumanAdmin`
(`handlers_action_approvals.go:52-64`) are unaffected and a delegated user is
never mistaken for a surface relay. It **does** carry `execID`, `workItemID`
and `runID`, so `clientmeta.go:190-191` and `handlers_work_items.go:237` keep
stamping `via_execution_id` for the delegated write — which is the whole audit
outcome T5 asserts.

Mount point: `router.go`, immediately after `r.Use(h.surfacePrincipalGate)`
(`:321`) and before `usageWriterGate` (`:323`). That places it under
`middleware.Timeout(30s)` (`:319`), which it needs because it reads Postgres,
and above the 300/min per-user limiter (`:334-341`), so a delegated request's
budget keys on the subject through `rateLimitSubject` — the same behaviour a
relay already has.

New `Options` field in `router.go`, beside `SurfaceIdentities` /
`TenantResolver` / `Principals` (`:113-122`):

```go
// Delegation resolves an X-MCTL-On-Behalf-Of grant ref to the stored
// subject it names (mctl-api#376 slice B). Optional: nil makes every
// delegated request 503, never an undelegated one.
Delegation delegation.Resolver
```

### B3. `forbiddenIdentityFields`, applied where B needs it

1. Add `"acting_principal"` to `forbiddenIdentityFields`
   (`handlers_work_items.go:64-70`). `on_behalf_of`, `subject` and
   `delegated_actor` are already there. Every route already decoding through
   `decodeWorkItemBody` / `decodeWorkItemBodyLimit` — including
   `POST /agent-run-tokens` (`handlers_agent_run_tokens.go:118`) and all of the
   work-item and execution-request routes — picks the new name up for free.
2. Add one additive helper next to it, modelled on `refuseExecutionIdentity`
   (`handlers_execution_requests.go:58-76`):

```go
// refuseIdentityFields answers 400 when the raw body names any
// forbiddenIdentityFields, then restores the body for whatever decoder the
// handler already uses. For routes that cannot yet move to
// decodeWorkItemBodyLimit (the dev-loop approve route's lenient decode is
// Slice C's to change).
func refuseIdentityFields(w http.ResponseWriter, r *http.Request, limit int64) bool
```

   It uses `readWorkItemBody` + `restoreBody`, tolerates an empty body (so the
   approve route's `io.EOF` case still works), and on a non-object body simply
   restores and returns true — leaving the existing decoder to produce the
   error it produces today.
3. Call it at the top of `ApproveDevLoopWorkflow` (`handlers_dev_loop.go:320`,
   before the existing decode) and of `RespondHumanInput`
   (`handlers_human_input_response.go:490`). Nothing else on those routes
   changes: the approve route keeps its `approver == user.ID` tolerance, its
   `requireTemporalAdmin` check and its EOF tolerance, all of which are C2's to
   change.

## Alternatives

**Put the subject on the run token and drop the header.** The mint would take a
subject and `AgentRun` would carry it. Rejected: it recreates exactly the
unbound-approver problem the parent issue exists to kill. A mint request is a
body, so the subject would again be a caller-supplied string, and A4's DoD
("no subject column on the row") would have to be reverted. The header-selects-
a-grant design is what makes the constraint structural.

**Widen the shared column lists now (pull D1 forward).** Adding the four
principal-id columns to `actionApprovalColumns` and friends would let the
resolver reuse `Store.ActionApproval` / `Store.Get`. Rejected: it changes the
JSON of `GET /api/v1/action-approvals/{id}` and of every work-item read, which
is a public contract change the issue puts out of scope, and it is already
scheduled as D1 with its own DoD. Narrow per-grant projections are strictly
smaller and let D1 land unchanged afterwards; the projections can then be
re-pointed at the widened scanners as a cleanup.

**Resolve delegation inside each handler instead of in middleware.** Rejected
for the reason `handlers_surface_identity.go:116-120` already gives for relay:
"Relay resolves here, in one place, rather than per route: a relay route can
then never be reached by a surface principal as itself." Per-handler resolution
makes a forgotten call site a silent privilege bug; middleware plus an explicit
allowlist makes it a 400.

**Reuse `surfacePrincipalGate` with a `delegated` flag on `surfaceRoute`.**
Tempting, since the allowlists overlap. Rejected: the two gates have different
headers, different refusal codes, different statuses (403 vs 400 for the route
case), and different failure postures (a relay degrades on a principal-store
error, delegation must fail closed). Folding them produces a gate with two
modes and a shared blast radius; keeping them siblings keeps every existing
surface-relay test a regression guard (T9).

**Let a non-`github:` subject through as an OIDC principal.** Rejected for now:
`NewRelayedUser` has no such case either, `githubLogin` is proof-of-how-you-
authenticated and must not be set for a Dex subject, and no grant source today
stores a non-`github:` subject that a worker would plausibly delegate for. It is
recorded as an open question rather than guessed at.

## Platform impact

**Migrations.** None. No new table, no new column, no change to an existing
column list. The four `*_principal_id` columns the resolver reads already exist
(`execution_requests.go:156`, `action_approvals.go:131`, `store.go:126`) and are
already written. `internal/delegation` has no schema of its own.

**Backward compatibility.** Additive on every path:

- a request with no `X-MCTL-On-Behalf-Of` header takes the gate's step-1
  pass-through, so every existing caller — human, surface, service, usage
  writer, evidence writer, and an agent acting for itself — is byte-identical;
- the only behaviour change for an existing caller is the B3 body check, which
  turns a silently-ignored `subject` / `acting_principal` / `on_behalf_of` /
  `delegated_actor` key into a 400 on the approve and human-input-response
  routes. No current client sends them (the approve route's own error message at
  `handlers_dev_loop.go:326-328` shows the only field anyone sends is
  `approver`, which is untouched);
- `Delegation == nil` (any deployment that does not wire it) makes a delegated
  request 503 and leaves every other request alone.

**Resource impact.** One extra Postgres round trip per delegated request (two
for a `sil_` grant: the link plus the surface-ref binding check), on the same
pool the relay already uses, inside the existing 30s middleware timeout. An
undelegated request costs one `r.Header.Get` and nothing else. No new
goroutines, no cache, no new connection.

**Risks and mitigations.**

- *A grant ref becomes a capability.* Mitigated by binding: a ref is useless
  without a run token bound to the same execution or work item, run tokens are
  short-lived (`workitems.DefaultAgentRunTokenTTL`, capped at
  `MaxAgentRunTokenTTL`), and an unknown ref is indistinguishable from an
  out-of-scope one, so refs cannot be enumerated.
- *Privilege escalation through the subject.* Mitigated by `NewDelegatedUser`
  dropping `admins` (the same filter `NewRelayedUser:339-344` applies) and by
  the allowlist excluding every admin-only route. T4's "never carries admins"
  assertion is the guard.
- *No per-agent aggregate rate ceiling.* A delegated request's 300/min and
  20/min buckets key on the **subject**, so one agent delegating for many
  humans has no single ceiling — the gap `surfaceAggregateLimit`
  (`router.go:838-845`) closes for surfaces. Mitigated for now by the run
  token's TTL, its explicit permission list, and the fact that every mint is
  audited (`agent_run_token.mint`); recorded as out of scope and called out
  here so a follow-up issue can add the analogue.
- *A principal-store outage breaks delegated agent work* where it merely
  degrades every other path. Accepted deliberately (step 9 above) and to be
  documented as a runbook note; it is the correct trade for a slice whose only
  product is a recorded subject.
- *Two subject derivations could disagree* (the stored `*_principal_id` and the
  live `AttachPrincipal`). Mitigated by the explicit cross-check at step 10,
  which refuses rather than picking one.
- *Scope bleed into Slice C.* Mitigated by B3 being purely additive on the
  approve route: `refuseIdentityFields` adds a check and restores the body, so
  C2 still replaces the decoder, the admin check and the approver stamping
  exactly as its own DoD describes.

**Test and tooling surface.** `go test ./internal/delegation/...
./internal/auth/... ./internal/api/... ./internal/workitems/...` plus
`cd e2e && go test -v`. No MCP tool is added, so
`internal/mcp/server_test.go`'s `TestNewMCPServer_ToolCount` is untouched.
`internal/openapi/openapi.yaml` gains the two header/refusal descriptions for
the allowlisted routes; no new path.
