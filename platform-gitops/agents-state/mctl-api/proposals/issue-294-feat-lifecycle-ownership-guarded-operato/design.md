# Design: issue-294-feat-lifecycle-ownership-guarded-operato

## Current state

### The store

`internal/lifecycle` is a PostgreSQL-backed ownership store, and its package doc
(`types.go:15-30`) is explicit about what it is not: not a second lifecycle
database, and not a scheduler — "no timer, no queue, no due_at and no background
sweep". Liveness and progress are DERIVED on read.

- Schema (`store.go:39-95`): `lifecycle_ownership` keyed `UNIQUE (entity_kind,
  entity_id, phase)`, carrying `entity_version`, `owner_type`/`owner_id`,
  `epoch`, `state`, `last_seen_at`, `last_progress_at`, the handoff pair, and
  `released_at`/`released_reason`. `lifecycle_events` is append-only and already
  carries `entity_version`, `actor_type`/`actor_id`, `owner_epoch` and `reason`.
- States (`types.go:59-64`): `active`, `handing-off`, `released`, `terminal`.
  There is deliberately no stored `stale` or `conflicted`.
- Owner types (`types.go:68-78`): `devloop-workflow`, `shepherd`, `pr-steward`,
  plus `reconciler` and `human-codeowner`, which are declared and **currently
  unreferenced anywhere in the repository** — they were reserved for exactly this
  change.
- Events (`types.go:81-90`): `owner-acquired`, `owner-denied`, `progress`,
  `handoff-started`, `handoff-completed`, `owner-released`, `owner-terminal`,
  `recovered`.
- Two bounds per (kind, phase) (`types.go:124-132`): liveness (licenses takeover)
  and progress (licenses escalation to a human, never a takeover). `IsDead`,
  `IsStuck`, `IsHealthy`, `HandoffStalled` derive from them
  (`types.go:228-285`); `Derive` (`derive.go:92-136`) turns a row into a closed
  status vocabulary plus `Held`, the takeover predicate, carried separately from
  `Status` on purpose.
- `diverge.go` classifies the store's answer against the legacy DevLoopWorkflow
  check; `store-permits-old-forbids` is the one dangerous class.

Writes: `Acquire`, `RecordProgress`, `HandoffStart`, `HandoffComplete`,
`Release`, `Terminal` all require the caller to BE the owner and to name the
epoch. `Recover` (`store.go:1215-1408`) is the only write that takes a row from
somebody else, and three properties keep it from being theft: liveness is
re-derived server-side inside the advisory-locked transaction, only liveness
counts (a stuck owner stays its own), and `expectedEpoch` pins the decision to
the row the caller read. Its `UPDATE` (`recoverUpdateSQL`, `store.go:1179-1189`)
pins `epoch` AND `last_seen_at` in the `WHERE`, because a revived owner's
idempotent re-acquire refreshes `last_seen_at` without moving the epoch — the
CAS lesson documented at `store.go:1294-1310` and repeated for the other three
statements at `store.go:461-480`.

### The HTTP layer

`internal/api/handlers_lifecycle.go` exposes four reads and seven writes, all
gated by `requireLifecycleAdmin` (`:52-67`): 503 when the store is nil, 401
unauthenticated, 403 non-admin. `writeLifecycleError` (`:117-177`) maps the store
sentinels onto status codes — 412 for `ErrEpochMismatch`, 409 for
`ErrOwnedByOther`/`ErrNotOwner`/`ErrStaleRead`/`ErrOwnerAlive`, 404 for
`ErrNotFound` — and logs anything else at 500 with the raw error withheld.

Three properties of this layer matter for the work here:

1. **All seven writers share one request struct**, `lifecycleWriteRequest`
   (`:352-371`). On six routes `owner_type`/`owner_id` mean "the caller"; on
   `/recover` the same two fields mean "the NEW owner". That overload is exactly
   the confusability the issue's MCP criterion warns about, and the operator
   surface must not inherit it.
2. **Nothing here is audited.** `internal/audit` is not imported by this file;
   the only writer is `Handlers.logAudit` (`internal/api/clientmeta.go:171-183`),
   used by `handlers_dev_loop.go`, `handlers_domains.go`,
   `handlers_platform_skills.go`, `handlers_write.go` and
   `handlers_portal_server_auth.go`. Every lifecycle handler discards the user:
   `if _, ok := h.requireLifecycleAdmin(w, r); !ok`, even though that helper
   already returns `(*auth.User, bool)`.
3. **Routing** (`router.go:388-430`): reads sit outside any write group by
   deliberate decision; the seven writes have their own `httprate` group at
   120/min keyed `"lifecycle:"+user.ID`, separate from the 20/min
   `/operations/{name}/execute` group, with the reasoning recorded inline.

Lifecycle endpoints bypass `internal/operations` entirely — the store is wired
straight onto `Options.Lifecycle` (`router.go:103-105`) — so they carry no
`RiskLevel`, no `RequiresConfirm` and no `ModifiesPaths`. `internal/openapi/openapi.yaml`
is hand-written and documents none of the eleven lifecycle routes.

### The MCP layer

`internal/mcp/lifecycle.go` registers exactly one tool,
`mctl_get_lifecycle_ownership` (`:115`), read-only, registered at
`server.go:251`. It already assembles the conflict evidence an operator needs —
ownership, derived, three-valued legacy answer with its own `available` flag,
divergence class, optional events, with fan-out caps and two distinct truncation
flags. Mutating tools elsewhere follow a fixed shape: `WithReadOnlyHintAnnotation(false)`
+ `WithDestructiveHintAnnotation(...)` + `WithIdempotentHintAnnotation(...)`, a
`confirm` argument checked by `requireConfirm` (`server.go:2629-2642`) for
destructive ones, and `s.apiPostJSON` / `s.apiPost` (`server.go:2555-2571`) to
reach the API. Three tests police the surface:
`annotations_test.go` `recordedHints` (77 entries) must equal `ListTools()`
exactly; every `mcplib.NewTool(` block in every non-test file must declare both
hints, plus an idempotency hint when not read-only; and
`TestReadOnlyToolsAreTheRecordedSet` pins a 34-name read-only list.
`server_test.go:59-70` compares tool count to `len(recordedHints)`, and
`portal_allowlist_test.go` requires every registered tool to appear in
`docs/portal-allowlist.json` with an explicit decision (a mutating tool may be
`enabled: true` only if also named in the test's `mutatingOnPortal` map).

### What is missing for #294

- No way to clear a dead claim without appointing a successor. `Recover` demands
  one, so an operator who merely wants the entity free has to pick a winner.
- No operator path for a stuck owner or a stalled handoff. `HandoffStart` and
  `HandoffComplete` both require being the relevant actor.
- No recorded "please re-evaluate this entity" request.
- Preconditions stop at the epoch: no expected owner, no entity version/head.
- No audit entries at all, so "recovery appears in the audit trail" is false
  today.
- No MCP surface for any of it.

## Proposed solution

Five new endpoints in three new files, plus small edits to five existing ones.
The operator surface is kept physically and structurally separate from the actor
surface: different files, a different request struct, a different rate-limit
budget, a different authorization helper, and a different event vocabulary.

### 1. `internal/lifecycle/recovery.go` (new)

Types:

```go
// Preconditions every recovery carries. All are compared BOTH on the read
// inside the advisory-locked transaction and in the UPDATE's WHERE clause.
type RecoveryPreconditions struct {
    ExpectedOwner      Owner
    ExpectedEpoch      int
    ExpectedVersion    *string    // nil is a caller error, not "any version"
    ExpectedLastSeenAt *time.Time // optional extra pin on liveness evidence
}

type RecoveryRequest struct {
    Entity    EntityRef
    Phase     string
    Pre       RecoveryPreconditions
    Principal string // the acting human principal; becomes the event actor
    Reason    string
}

type RecoveryResult struct {
    Ownership *Ownership
    Before    Snapshot // owner, epoch, state, version, last_seen_at as read
    Licensed  string   // "dead" | "stuck" | "handoff-stalled" | "none"
    Event     string
}
```

Operations, each naming one transition:

| Method | Licensed by | Effect |
|---|---|---|
| `FenceDeadClaim` | `IsDead` re-derived in-tx | `state = released`, epoch+1 **computed by the database**, `released_reason = "fenced: …"`, owner preserved for forensics, handoff fields cleared. Installs nobody. |
| `RequestHandoff(req, to)` | `IsStuck` re-derived in-tx, state `active` | `state = handing-off`, target set, `handoff_started_at = now`, **epoch unchanged**. The target must still complete via the ordinary `HandoffComplete`. |
| `RetryHandoff` | `HandoffStalled` re-derived in-tx | Re-arms `handoff_started_at` for the SAME target. Owner, target, state and epoch all unchanged. |
| `RequestReconcile` | nothing | Appends `reconcile-requested`. Mutates no ownership column. |
| `InspectConflict` | — | Read: row + `Derive` + recent events + the precondition values to send back. |

Four package-level SQL constants (`fenceUpdateSQL`, `handoffRequestUpdateSQL`,
`handoffRetryUpdateSQL`, and the reconcile path's event insert), for the reason
`store.go:107-113` gives: a constant can be executed directly by a test with a
weakened predicate, which is the only way to show the `WHERE` is load-bearing.
Each `WHERE` pins `entity_kind/entity_id/phase`, `epoch`, `owner_type`,
`owner_id`, `entity_version`, the state (or state class) the decision was derived
from, and the liveness evidence: `last_seen_at` for the fence (the revived-owner
hazard `store.go:1294-1310` describes), `handoff_started_at` and both
`handoff_to_*` columns for the retry (the retarget hazard `store.go:560-588`
describes). The epoch is incremented by the statement (`epoch = epoch + 1`),
never bound from a value the caller read — the argument at `store.go:154-163`.

On a zero-row result each statement re-reads the row under the same lock and
answers the sentinel describing what actually moved, matching `Recover`'s
`raceLostOn`/re-read arm (`store.go:1317-1381`). New sentinels beside the
existing ones in `types.go`:

- `ErrOwnerMismatch` — the expected owner is not the current owner (412).
- `ErrVersionMismatch` — the expected entity version is not the stored one (412).
- `ErrOwnerNotStuck` — handoff requested against a healthy or dead owner (409).
- `ErrHandoffNotStalled` — retry against a handoff still inside its bound (409).

New event names beside the existing block: `EventFenced = "fenced"`,
`EventHandoffRequested = "handoff-requested"`, `EventHandoffRetried =
"handoff-retried"`, `EventReconcileRequested = "reconcile-requested"`. Every
recovery event's actor is `Owner{Type: OwnerHumanCodeowner, ID: principal}` —
the first use of the constant reserved at `types.go:77` — and its reason carries
the old owner, old and new epoch, the claim state, the licensing condition and
the operator's text, in the shape `Recover` already writes at `store.go:1394-1398`.

**Why entity version is a precondition here and nowhere else.** `types.go:156-168`
is explicit that version is not part of the ownership key and not a precondition
on ownership, because a new head on the same pull request is the normal case for
an owner mid-work, not a handoff. That reasoning is about the OWNER's own writes.
An operator's recovery is a judgement made by reading the entity; if the head
moved after that reading, the judgement may be void. So version becomes a
precondition on recovery only, and the key stays untouched.

### 2. `internal/api/handlers_lifecycle_recovery.go` (new)

Its own request struct, `lifecycleRecoveryRequest`, with no field whose meaning
depends on the route:

```json
{
  "kind": "pull-request", "id": "mctlhq/mctl-web#42", "phase": "review-remediation",
  "expected_owner_type": "shepherd", "expected_owner_id": "cron",
  "expected_epoch": 7,
  "expected_version": "sha-abc",
  "expected_last_seen_at": "2026-09-18T04:00:00Z",
  "reason": "wf pod OOMKilled at 03:12; no tick since",
  "to_owner_type": "pr-steward", "to_owner_id": "steward"
}
```

Decoded with `http.MaxBytesReader` at the existing `lifecycleMaxBodyBytes` cap and
with `Decoder.DisallowUnknownFields`, so an invented `force_owner` key is a 400
rather than a silently ignored field — the cheapest possible enforcement of "no
generic force/override exists". `expected_version` is `*string`: absent is a 400
naming the field, `""` matches an unset row exactly. Missing epoch, owner, or
reason are 400s too, on the reasoning `requireEpoch` already records at
`handlers_lifecycle.go:520-538`: a 412 tells a caller to re-read, which does not
help a caller that simply omitted a field.

`requireLifecycleRecovery` wraps `requireLifecycleAdmin` and additionally refuses
with 503 when `h.opts.AuditLog == nil`. `logAudit` is a silent no-op on a nil log
(`clientmeta.go:172`), and an acceptance criterion cannot be contingent on
deployment configuration: an unauditable recovery must not happen.

Handlers: `GetLifecycleConflict`, `RequestLifecycleReconcile`,
`FenceLifecycleClaim`, `RequestLifecycleHandoffRecovery`, `RetryLifecycleHandoff`.
Each binds the `*auth.User` (which the existing handlers throw away) and writes
exactly one `audit.Entry` on BOTH the success and the refusal path:

```go
h.logAudit(r, audit.Entry{
    UserID: user.ID, Operation: "lifecycle-recovery-fence",
    Parameters: map[string]string{ /* entity, phase, version, epoch_before,
        epoch_after, owner_before, state_before, state_after, licensed_by,
        expected_* as sent, reason, outcome */ },
    Status: "succeeded", RiskLevel: string(operations.RiskHigh),
})
```

The refusal entry is the one that proves the stale-client criterion: a 412 that
leaves no trace is indistinguishable from a request nobody made. `Status` uses
the existing vocabulary (`succeeded`, `failed`, `denied`);
`audit.Entry.Parameters` is `map[string]string`, which is the structured home for
the fields the issue enumerates, and `internal/audit/redact.go` already redacts at
read time by key name.

`writeLifecycleError` grows four arms — `ErrOwnerMismatch` and
`ErrVersionMismatch` → 412 with the current record in the body so the operator can
re-read; `ErrOwnerNotStuck` and `ErrHandoffNotStalled` → 409 — for precisely the
reason the file's existing comments give: an unmapped sentinel falls into the
default arm and becomes a 500, which backs clients off and pages an operator over
a caller mistake.

### 3. `internal/api/router.go`

The conflict read joins the reads outside any write group. The four mutations get
their own `httprate` group at 10/min keyed `"lifecycle-recovery:"+user.ID` — a
third budget beside the existing 20/min and 120/min ones, with the same style of
inline justification: these are hand-driven, rare, and each one is a tie-break a
human is supposed to think about. Paths:

```
GET  /api/v1/lifecycle/ownership/conflict
POST /api/v1/lifecycle/ownership/recovery/reconcile
POST /api/v1/lifecycle/ownership/recovery/fence
POST /api/v1/lifecycle/ownership/recovery/handoff/request
POST /api/v1/lifecycle/ownership/recovery/handoff/retry
```

`recovery/handoff/*` is a distinct static prefix from the actor
`handoff/start|complete`, so chi's radix tree separates them; they are kept
adjacent with a note, the convention already used at `router.go:350-354`.

### 4. `internal/mcp/lifecycle_recovery.go` (new)

Five tools, verb-first per repo convention, each naming its transition — no
`operation` enum, because a discriminator argument whose value selects the
semantics is the generic mutation surface the issue forbids:

| Tool | readOnly | destructive | idempotent | confirm |
|---|---|---|---|---|
| `mctl_inspect_lifecycle_conflict` | true | false | — | no |
| `mctl_request_lifecycle_reconcile` | false | false | true | no |
| `mctl_fence_lifecycle_claim` | false | true | false | yes |
| `mctl_request_lifecycle_handoff` | false | true | false | yes |
| `mctl_retry_lifecycle_handoff` | false | false | true | no |

Each mutating description opens by saying it changes state, names the single
transition and the condition that licenses it, states that every precondition
fails closed, points at `mctl_inspect_lifecycle_conflict` as where the
precondition values come from, and repeats the sentence the read tool already
carries: this grants no authority and confers no GitHub merge or approval rights.
`requireConfirm` guards the two destructive ones. Registration goes in the
mctl-agents group beside `s.toolGetLifecycleOwnership()` at `server.go:251`.

Bookkeeping the tests demand: `recordedHints` 77 → 82;
`TestReadOnlyToolsAreTheRecordedSet`'s list gains
`mctl_inspect_lifecycle_conflict`; `docs/portal-allowlist.json` gains five
entries — the inspect tool `enabled: true` with a reason in the style of the
existing `mctl_get_lifecycle_ownership` entry, the four mutations `enabled: false`,
which also avoids touching `mutatingOnPortal`.

### Why this shape satisfies the hard criteria

- **No merge authority**, structurally: the recovery handlers reference
  `h.opts.Lifecycle` and `h.opts.AuditLog` and nothing else. No GitHub client, no
  Temporal client, no Argo executor is in scope in the file, so there is no path
  to a merge, an approval or a push. `NEVER_MERGE_SERVICES` does not appear
  anywhere in this repository; it is mctl-agents policy, and nothing here can
  reach the code that would have to consult it. A test pins this by constructing
  `Handlers` with only those two options set.
- **No generic force**: no operation accepts an owner for a live row. Fence
  appoints nobody; handoff-request names a target that must arrive under its own
  identity; retry cannot change the target; reconcile changes nothing. The
  appointing operation, `Recover`, keeps its dead-owner requirement and is
  untouched.
- **Fails closed**: every precondition is checked twice — once on the read, once
  in the `WHERE` — and a row that moves in between refuses the write.

## Alternatives

1. **Extend `POST /lifecycle/ownership/recover` with a `mode` parameter
   (`fence` | `handoff` | `reconcile`).** Fewer routes, less code. Dropped: a
   single endpoint whose semantics are selected by a field value is a generic
   mutation surface in all but name, and the issue requires each operation to name
   a specific reviewable transition. The existing shared `lifecycleWriteRequest`
   already shows what this costs — `owner_type` means "the caller" on six routes
   and "the new owner" on the seventh — and an MCP descriptor for a mode-switched
   tool cannot state its own destructiveness.
2. **Put recovery in mctl-agents' reconciler and leave mctl-api read-only.**
   Dropped: `mctlhq/mctl-agents#353` is the AUTOMATIC path and is an explicit
   non-goal here. A human path that requires dispatching an Argo workflow is not
   operator recovery, and it would move precondition enforcement outside the store
   that owns the invariant, where it becomes advisory.
3. **Add the recovery operations to the `internal/operations` registry with
   `RiskLevel: RiskHigh, RequiresConfirm: true` and drive them through
   `/operations/{name}/execute`.** This would give free audit and a declared risk
   level. Dropped: that path submits Argo workflow templates
   (`operations.Executor.Submit`), and these are single short Postgres
   transactions; `RequiresConfirm` is also declared-only metadata read nowhere in
   the codebase, so it would buy a label rather than a control.
4. **Record the operator's intent in a `lifecycle_recovery_requests` table that a
   worker drains.** Dropped: that is a queue with a sweeper, which is precisely
   what `types.go:23-27` forbids this package from becoming. The append-only event
   plus the audit entry carry the same information with no new machinery.

## Platform impact

**Migrations: none.** Every column the design writes already exists —
`entity_version`, `released_at`, `released_reason`, the handoff quartet, and
`lifecycle_events.actor_type`/`actor_id`/`entity_version`. The new event names and
the `human-codeowner` actor type are values in existing `TEXT` columns. The schema
block is idempotent `CREATE TABLE IF NOT EXISTS` with no migration runner, so
avoiding new columns is worth the small loss of structure — the enumerated fields
live in `audit.Entry.Parameters` (JSONB in `audit_events`) and in the event
reason.

**Backward compatibility.** Purely additive: eleven existing lifecycle routes,
their request shapes and the single existing MCP tool are unchanged. Deployed
mctl-agents clients are unaffected. An older mctl-api behind a newer MCP server
answers 404 on the new routes; the tools surface that verbatim, matching the
guard `lifecycle.go:290-299` already applies to the record read. Downgrading is
safe: rows fenced by this change are ordinary `released` rows, and the new event
names are inert to readers, which return events as raw JSON
(`lifecycle.go:601-610`) rather than switching on the name.

**Resource impact.** Each mutation is one advisory-locked transaction with one
`SELECT`, one `UPDATE` and one `INSERT`, at a 10/min per-principal ceiling. The
conflict read costs one row read, one events read and at most one dev-loop
describe call. Negligible beside the 120/min actor budget.

**Risks and mitigations.**

- *An operator-requested handoff freezes the owner's liveness.* A `handing-off`
  row has `last_seen_at` frozen by every writer that could move it
  (`store.go:588-591`), so a handoff the incoming actor never completes becomes
  `handoff-stalled`, then dead, then machine-recoverable after the liveness bound
  (10h for review-remediation). That is the intended escalation, but it means an
  operator-initiated handoff that nobody consummates eventually takes the entity
  away from a live owner. Mitigated by licensing the operation on `IsStuck` only
  — an owner that has effected nothing for 48h — by leaving the epoch untouched so
  the owner is not fenced out meanwhile, by recording the operator principal on
  the event, and by documenting the consequence in the tool description and the
  412/409 messages.
- *Fencing a row whose owner revives one second later.* The pinned `last_seen_at`
  turns that into a refused write rather than a silent theft; the revived owner's
  re-acquire refreshes `last_seen_at` and the fence's `WHERE` stops matching. This
  is the exact hazard `store.go:1294-1310` documents, and the mitigation is the
  same one.
- *Audit log unavailable.* Recovery returns 503 rather than proceeding
  unaudited. This makes the audit log a hard dependency of the operator surface
  only; the actor surface is unaffected.
- *Confirmation is client-side.* `requireConfirm` lives in the MCP server, so a
  direct HTTP caller never sees it. The server-side control is therefore not the
  confirm flag but the precondition set plus the mandatory `reason`: a caller that
  cannot state the current owner, epoch and head cannot fence anything.
- *Operator recovery becomes routine.* Every refusal and every success lands in
  `audit_events` with a principal and a risk level, so "how often is a human
  breaking ties" is a query rather than a feeling — the signal that ADR-010's
  automatic path is missing something.
- *MCP surface growth.* Five tools is a meaningful addition to a 77-tool server.
  The alternative — one tool with a mode argument — is rejected above; the
  mitigation is that four of the five are disabled on the shared portal and all
  five are admin-only upstream.
