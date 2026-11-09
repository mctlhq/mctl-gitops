# Design: issue-935-design-workitems-controlled-lease-aware

## Current state

Execution requests (mctl-api#368) live in `internal/workitems/execution_requests.go`, table
`work_item_execution_requests`.

- States: `pending -> claimed -> fulfilled | rejected`. A lapsed claim stays stored as `claimed` and becomes
  claimable again. The package comment says "the lapsed holder can no longer fulfil or reject it".
- One open request per item is enforced in two ways: under the advisory lock `workitem:<id>` (`withTx`,
  `internal/workitems/store.go:266`, `pg_advisory_xact_lock(hashtext(...))`), and by the partial unique index
  `work_item_execution_requests_one_open`.
- `ClaimExecutionRequest` runs `claimCandidateSQL` outside the lock and takes the 8 oldest
  (`claimCandidates = 8`) claimable rows by `(created_at, id)`. With `queueWhileActive` on
  (`MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE`, `queue_switch.go`), the SQL excludes items with an open execution,
  and the locked transaction re-checks that. The UPDATE is the CAS
  `WHERE id=$1 AND (state='pending' OR (state='claimed' AND claim_expires_at <= $4))`. It mints a fresh `xc_` token
  and records `claimed_by = in.Actor`.
- `ClaimRef.holds` compares `claimed_by` and the token in constant time. `FulfilExecutionRequest` and
  `RejectExecutionRequest` both require `state='claimed'`, `holds`, and `claim_expires_at > now`. Otherwise they
  return `ErrExecutionRequestNotClaimed`. A fulfil of a `rejected` request returns `ClosedRequestError`. A reject
  of a `rejected` request returns `ErrExecutionRequestNotClaimed` when the token differs, and a replay when the
  holder sends the same reason.
- `ExecutionRequest.ClaimToken` is `json:"-"`. Only `ClaimExecutionRequest` returns the token, as `claim_token` in
  the response.
- `ExecutionRequests(itemID)` lists one item's requests newest first, capped at `maxExecutionRequestList = 100`.
  There is no cross-item or tenant-wide list.
- HTTP (`internal/api/handlers_execution_requests.go`): claim, fulfil and reject go through `executionPlatform`.
  That check (`isDirectService`, `handlers_action_approvals.go:90`) admits only the service principal acting
  directly. Refusals are audited by `auditExecutionRequestRefusal`. Routes are in `internal/api/router.go:839-841`,
  in their own 120/min rate-limit group. Reads are `GET /work-items/{id}/execution-requests[/{request_id}]`
  (`router.go:965-966`), gated by `visibleWorkItem`/`canSeeWorkItem` (`handlers_work_items.go:135`). Note that
  `canSeeWorkItem` lets any `IsAdmin()` principal through, including the service principal, which carries the
  admins group.
- `isHumanAdmin` (`handlers_action_approvals.go:97`) already means "an admin person acting directly, not service,
  not relayed, not a surface". It is the existing gate for human decisions.
- `internal/workitems/orphans.go` already uses a keyset cursor on `(started_at, id)` for
  `OpenExecutionsWithQueuedRequests`, which feeds the orphan reconciler (`internal/api/execution_orphan_reconciler.go`).
  That is the paging pattern this design reuses.
- Store tests run against real PostgreSQL through `TEST_DATABASE_URL` (`execution_requests_test.go:172`). They
  already exercise racing claimants and lock holders (`TestExecutionRequest_ClaimHasOneWinner`,
  `TestExecutionRequest_LapsedClaimIsFenced`).

Why no existing mechanism is a safe drain. This is the spike's answer.
1. "Pause dispatcher -> list -> reject" cannot work. Reads have no token, and reject needs a live claim held by
   the caller.
2. "Operator uses the service token to call claim, then reject" is also unsafe:
   - Claim cannot target a request. It hands out whichever of the 8 oldest it wins, including requests the
     operator wants to preserve. No release exists, so a preserved request it grabbed stays blocked until its
     lease lapses. The 8-candidate window is also an oldest-N starvation risk.
   - Under queue-while-active, claim never returns requests queued behind an open execution, so those can never
     be drained this way.
   - A human holding `MCTL_TOKEN` and acting as the service principal erases actor identity from audit and
     events (`claimed_by` would be the service).
   - A dispatcher that is still running or restarts would compete for the same rows.
3. Direct SQL bypasses tenancy, the advisory lock, events and audit.

So a new capability is needed. The smallest safe one is a targeted, CAS-guarded, human-only reject that refuses
live claims, plus a bounded read to discover what to reject.

Deferral reasons. Per the mctl-agents#993 proposal (`agents-state/mctl-agents/proposals/issue-993-.../requirements.md`),
a deferral leaves the request `claimed`, and the lease sets only the retry cadence. In mctl-api, therefore, a
deferred request looks like a claimed request that alternates between `claimed_live` and `claimed_lapsed`.
mctl-api stores no deferral reason.

Deployed state checked:
- `mctl_get_service_config(team=admins, service=mctl-api)`: error "service not found: admins/mctl-api". mctl-api
  is not a catalogue tenant service under that name. Its tenant, replicas and env could not be observed.
- `$MCTL_GITOPS_ROOT/services/*/`: lists tenants admins, karabu, labs and namax66. None has an `mctl-api` entry.
  `infra-components/mctl-platform/mctl-api/` holds only `oidc-zitadel.yaml`, `orchestrator-devloop.yaml` and
  `zitadel-hook.yaml`. Neither contains the queue-while-active setting. Whether
  `MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE` is on in production is therefore unknown (see Open questions).
- `services/admins/mctl-agents-worker/values.yaml` (around line 145): `EXECUTION_REQUEST_DISPATCHER: "true"`. The
  dispatcher is on in the worker that owns the schedules. It claims, fulfils and rejects as the `mctl-agent`
  service principal via `MCTL_TOKEN`. The comment there says "a request left claimed is re-claimable once its
  lease lapses".
- Repo `helm/values.yaml`: `replicaCount: 1`. This is the chart default, not verified as deployed.

## Proposed solution

Everything ships behind a new switch, `MCTL_EXECUTION_REQUEST_OPERATOR_DRAIN` (default off). It is parsed like
`ParseQueueWhileActive`: `""`/`off` mean off, `on` means on, and anything else fails startup. When off, both new
routes are not mounted and answer 404.

### 1. Schema (additive, idempotent, in `executionRequestSchema`)
```sql
ALTER TABLE work_item_execution_requests ADD COLUMN IF NOT EXISTS revision BIGINT NOT NULL DEFAULT 1;
ALTER TABLE work_item_execution_requests ADD COLUMN IF NOT EXISTS rejected_by TEXT NOT NULL DEFAULT '';
ALTER TABLE work_item_execution_requests ADD COLUMN IF NOT EXISTS rejected_by_principal_id TEXT NOT NULL DEFAULT '';
ALTER TABLE work_item_execution_requests ADD COLUMN IF NOT EXISTS rejection_kind TEXT NOT NULL DEFAULT ''
    CHECK (rejection_kind IN ('', 'claimant', 'operator'));
```
The existing `work_item_execution_requests_claimable` index on `(created_at, id) WHERE state IN ('pending','claimed')`
already serves the discovery keyset scan. No new index is needed.

`revision` is a per-row fencing counter. Every state-changing UPDATE gets `revision = revision + 1`: claim,
fulfil, dispatcher reject and operator reject. Each row's revision is independent of the item's `state_version`.

### 2. State machine (unchanged states; one new guarded transition)
```
pending --claim(service)--> claimed[live] --lease lapses--> claimed[lapsed] --claim(service)--> claimed[live] (new token, rev+1)
claimed[live, holder]  --fulfil(holder token)--> fulfilled
claimed[live, holder]  --reject(holder token)--> rejected (rejection_kind=claimant)
pending                --operator-reject(human admin, expected_revision)--> rejected (rejection_kind=operator)
claimed[lapsed]        --operator-reject(human admin, expected_revision)--> rejected (rejection_kind=operator, token cleared)
claimed[live]          --operator-reject--> REFUSED 409 execution_request_claim_live
any, revision moved    --operator-reject--> REFUSED 412 execution_request_revision_moved
fulfilled|rejected     --operator-reject--> REFUSED 409 execution_request_closed (or 200 replay)
```
`lease_state` is computed at read time and never stored: `pending`, `claimed_live` (`claim_expires_at > now`) or
`claimed_lapsed`.

### 3. Store (`internal/workitems/execution_requests.go`, new file `operator_drain.go`)

- `OpenExecutionRequests(ctx, OpenRequestFilter{Tenant, States, Limit, After *OpenRequestCursor})
  ([]OpenExecutionRequestRow, *OpenRequestCursor, error)`. It runs one query:
  ```sql
  SELECT <executionRequestColumns>, r.revision, w.tenant, w.state, w.state_version, w.visibility, w.owner_principal,
         (SELECT e.id FROM work_item_executions e WHERE e.work_item_id=r.work_item_id AND e.phase IN <openPhasesSQL>
          ORDER BY e.started_at DESC LIMIT 1) AS open_execution_id
  FROM work_item_execution_requests r JOIN work_items w ON w.id = r.work_item_id
  WHERE r.state IN ('pending','claimed') AND ($tenant = '' OR w.tenant = $tenant)
    AND ($cursor_id = '' OR (r.created_at, r.id) > ($cursor_ts, $cursor_id))
  ORDER BY r.created_at, r.id LIMIT $limit + 1
  ```
  The extra row decides whether `next_cursor` is set. Ordering is by immutable `(created_at, id)`, so a full walk
  visits every row that was open when the walk passed its position. Rows created later appear at the end of the
  walk. There is no oldest-N window to starve in. Requests queued behind an open execution are included.
- `OperatorRejectExecutionRequest(ctx, OperatorRejectInput{Mutation, RequestID, ExpectedRevision, Reason})
  (*ExecutionRequest, *WorkItem, OperatorRejectPrior, bool, error)`. It uses the existing `lockedRequest` (item
  lock, then `SELECT ... FOR UPDATE`), and runs under the same idempotency helpers `replayed`/`remember` with op
  `execution_request_operator_reject`. Order of checks:
  1. Replay of the same actor, key and body: return the stored row with `created=false`.
  2. `fulfilled`/`rejected`: return `ClosedRequestError`.
  3. `x.Revision != ExpectedRevision`: return `*RevisionMovedError{Current: x}`.
  4. `state=claimed && claim_expires_at > now`: return `*ClaimLiveError{Current: x}`.
  5. Otherwise run this UPDATE:
     ```sql
     UPDATE ... SET state='rejected', reason=$2, rejected_by=$3, rejected_by_principal_id=$4,
            rejection_kind='operator', claim_token='', revision=revision+1, updated_at=$5, closed_at=$5
     WHERE id=$1 AND revision=$6 AND state IN ('pending','claimed')
       AND (state='pending' OR claim_expires_at <= $5)
     ```
     It then appends `execution_request_operator_rejected`, with detail `{execution_request_id, prior_state,
     prior_claimed_by, prior_claim_expires_at, revision, requested_by}`. The detail has no reason text and no token.

  The reason is validated with the existing `checkText(..., MaxExecutionRequestReason, true)` and `scanSecrets`.
  The function writes no execution, no approval and no item state.
- Changes to existing paths:
  - Add `revision=revision+1` to the claim, fulfil and dispatcher-reject UPDATEs. The dispatcher reject also sets
    `rejection_kind='claimant'`.
  - In `RejectExecutionRequest`'s `ExecutionRequestRejected` branch, return `ClosedRequestError` when
    `rejection_kind='operator'`. A former holder then learns the request is closed instead of getting
    `not_claimed`.
  - `FulfilExecutionRequest` already returns `ClosedRequestError` for `rejected`, so a lapsed holder can never
    attach an execution, and nothing can record `Succeeded` for it.
  - `executionRequestColumns` and `scanExecutionRequest` gain `revision`, which is serialized. They also gain
    `rejected_by` and `rejection_kind`, serialized as omitempty. `claim_token` stays `json:"-"`.

### 4. HTTP (`internal/api/handlers_execution_requests.go`, new `handlers_execution_request_drain.go`)

Gate: `operatorDrain(w, r, op)` requires `isHumanAdmin(user)`. Otherwise it returns 403
`execution_request_operator_forbidden` and writes a failed audit entry. The service principal is refused here on
purpose: the dispatcher must never call this path.

`GET /api/v1/execution-requests/open?tenant=&state=pending|claimed&limit=50&cursor=`
```json
{"schema_version": "...", "execution_requests": [
  {"id":"xr_..","work_item_id":"wi_..","kind":"resume","state":"claimed","revision":7,
   "lease_state":"claimed_lapsed","claimed_by":"mctl-agent","claimed_at":"..","claim_expires_at":"..",
   "requested_by":"..","surface":"..","created_at":"..","updated_at":"..",
   "tenant":"admins","work_item_state":"waiting","work_item_state_version":12,
   "open_execution_id":"we_.."}],
 "next_cursor":"<opaque>", "as_of":"<server time>", "limit":50}
```
- `cursor` is base64url JSON `{t, id, f}`, where `f` is a hash of the filters. A mismatch or malformed cursor
  answers 400 `invalid_cursor`.
- Each row's item still passes `canSeeWorkItem`. The response never carries `claim_token`.
- Each page is audited as `work_item.execution_requests_open_listed` with risk low, the filters and the row
  count.
- The route sits in the execution-requests rate-limit group.

`POST /api/v1/execution-requests/{request_id}/operator-reject`
```json
{"expected_revision": 7, "reason": "drain before worker rollback; mctlhq/mctl-agents#996", "idempotency_key": "drain-2026-11-xx-xr_.."}
```
- 200 returns `{"execution_request": {...state:"rejected", rejection_kind:"operator", revision:8},
  "prior": {"state":"claimed","lease_state":"claimed_lapsed","claimed_by":"mctl-agent","claim_expires_at":".."},
  "replayed": false}`.
- 409 `execution_request_claim_live` returns `{claim_expires_at, claimed_by, revision}`. The operator waits for
  the lease to lapse, which happens only once the dispatcher has stopped re-claiming, then re-reads.
- 412 `execution_request_revision_moved` returns `{revision, state, lease_state}`.
- 409 `execution_request_closed` reuses `writeExecutionRequestError`.
- 400 is returned for an invalid body or reason. Bodies naming `engine`, `engine_ref`, `execution_id` or
  `claim_token` are refused, extending `refuseExecutionIdentity` with `claim_token` for this route.
- Each item also passes `requireWorkItemRole(..., item.Tenant, operations.RoleAdmin, "execution-request-operator-reject")`,
  so per-item tenancy is checked explicitly even for platform admins.
- A success is audited as `work_item.execution_request_operator_rejected` with `RiskHigh`, through
  `auditExecutionRequest`, with extras covering the prior state, prior claimant and revision. A refusal is
  audited through `auditExecutionRequestRefusal` with the typed code.

### 5. Operator procedure (documented in `docs/`, not automated)
1. Make sure the dispatcher has stopped re-claiming, or will stop. This is an mctl-agents flag change and needs
   its own authorization. Expect pending rows and lapsed claims to remain. A live claim needs one lease
   (at most 15 minutes, `MaxClaimLease`) to lapse.
2. Walk `GET /execution-requests/open` until `next_cursor` is absent, and record the full list in the drain
   ticket.
3. For each request, the human records "reject" or "preserve" with a reason in the ticket. Preserved requests
   are not touched.
4. For each selected request, call operator-reject with the `revision` from the walk. On 412 or 409, re-read
   that one request and decide again. Never retry blindly.
5. Walk discovery again. Positive evidence for a worker-image rollback below M1 is all of the following: no row
   in the drained set is still open; every rejected id has an `execution_request_operator_rejected` event and
   audit entry; the preserved set is listed explicitly.

### Policy and approvals
- The new routes are REST, called by a human directly. They do not pass through the MCP policy checkpoint, and
  they do not replace it. If MCP tools are later added, they must be classified as mutating, so that the
  checkpoint's REQUIRE_APPROVAL applies.
- An operator reject can only prevent work. It never starts an execution and never touches
  `action_approvals` or DevLoop approval grants, so no digest-bound owner approval is bypassed or consumed.

## Alternatives

1. **Operator claim, then reject with the operator's own token (two steps).** A human-admin
   `POST /execution-requests/{id}/operator-claim` would mint a token with `claimed_by=<human>`, and the existing
   reject would be extended to admit it. This reuses fulfil/reject fencing, but it adds a second claimant type to
   the claim/fulfil paths and to the claim scan. The scan would have to ignore human claims, and a human-held
   claim could be "fulfilled", which reject must forbid. It also leaves a window in which a request is held but
   not closed, and the lease semantics then govern a human. The single-transaction CAS reject gives the same
   fencing guarantees with less surface. Dropped. The approach could return if an inspect-while-holding step
   turns out to be needed.
2. **Require a second-admin action approval per reject (mctl-api#366).** The operator would create an
   `ActionApprovalRequest`, with `action_kind=execution-request-operator-reject`,
   `target=<xr id>@<revision>` and `artifact_hash=sha256(reason)`. Another human admin decides it, and
   operator-reject consumes it with `ConsumeActionApproval` plus `MarkActionApprovalExecuted` in the same call.
   This is the strongest form of explicit authorization, but it makes a drain of N requests need N second-person
   decisions. Not chosen as the default. Kept as an additive extension behind an option, and recorded as an open
   question.
3. **Batch or filter reject ("reject all claimed_lapsed in tenant X").** Faster, but this is exactly the
   automated mass rejection the issue forbids, and it loses per-request revision fencing. Dropped.
4. **Expose `claim_token` to admins on reads so the existing reject works.** This would break the invariant that
   only the claimant ever sees the token, and would let a reader impersonate a live holder. Dropped.

## Platform impact
- **Migration:** four additive `ADD COLUMN IF NOT EXISTS` statements with constant defaults. On PostgreSQL 11+
  this is metadata-only, with no table rewrite. Existing rows get `revision=1`. Older API pods run during a
  rolling deploy and ignore the new columns. An older pod's claim does not bump `revision`. The operator reject
  is still safe in that case, because its UPDATE also re-checks state and lease under the lock. The revision CAS
  is then only weaker for a claim made by an old pod, and the live-claim check still covers it. Document that
  the drain should be used only after the rollout has completed.
- **Backward compatibility:** the dispatcher's claim, fulfil and reject contracts are unchanged, apart from new
  fields (`revision`, `rejection_kind`) in their JSON. The one behaviour change: after an operator reject, a
  former holder's reject gets 409 `execution_request_closed` instead of 409 `execution_request_not_claimed`.
  Both are already 409, and both mean "stop".
- **Resources:** the discovery query is bounded at 101 rows and served by an existing partial index. The
  per-row open-execution subquery uses the existing `work_item_executions` per-item index. There are no new
  background jobs.
- **Risks and mitigations:**
  - An operator rejects a request that should have run. Mitigated by per-id selection, the reason, the audit
    entry and the ticket. The requester can create a new request, since the one-open slot is freed.
  - A live dispatcher re-claims mid-drain. Mitigated by the revision CAS (412) and the live-claim refusal (409).
  - The dispatcher started an engine run before its lease lapsed, and then the operator rejects. The fulfil is
    refused with closed, so no execution is attached. The orphaned engine run is the dispatcher's to stop (out of
    scope). The E2E test asserts that no `Succeeded` is recorded.
  - Flag drift. The switch defaults off, and this issue authorizes no change to it.
