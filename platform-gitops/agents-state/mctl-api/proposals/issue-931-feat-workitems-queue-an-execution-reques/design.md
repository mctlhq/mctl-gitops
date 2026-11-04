# Design: issue-931-feat-workitems-queue-an-execution-reques

## Current state

The execution-request lifecycle (mctl-api#368) lives in
`internal/workitems/execution_requests.go`. The HTTP side is
`internal/api/handlers_execution_requests.go`, with routes in `internal/api/router.go`
around lines 795-813.

### Create

`Store.CreateExecutionRequest` (around lines 356-434) does the following under
`withTx(ctx, "workitem:"+id)`:

1. `getItem`.
2. `replayed(..., opExecutionRequest, in.Mutation)`: an idempotent replay returns the
   stored request.
3. A `state_version` check, which returns `ErrVersionConflict`.
4. `openExecutionRequest`, which returns `OpenRequestError`.
5. `listExecutions` followed by `checkRunnable`.
6. The pinned-intent check.
7. The INSERT of a `pending` row, `appendEvent(EventExecutionRequested)` and
   `remember(...)`.

`checkRunnable` (around lines 310-340) checks four things in this order:

1. a terminal item;
2. any execution with `!IsTerminalPhase` (`ErrExecutionActive`, line 316);
3. the kind rules;
4. that `resumed_from_execution_id` is a known execution of the item.

An active execution is refused before the INSERT and before `remember`, so nothing is
stored. `ErrExecutionActive` maps to 409 `execution_active` in
`internal/api/handlers_work_items.go:186`.

### Claim

`Store.ClaimExecutionRequest` (around lines 479-555) selects up to `claimCandidates` (8)
requests, oldest first, where `state='pending' OR (state='claimed' AND claim_expires_at
<= now)`. It then claims each candidate under the item lock with a compare-and-set
UPDATE. It never looks at executions.

### Fulfil

`FulfilExecutionRequest` (around lines 609-689) re-decides the request inside the same
transaction:

- start: `checkStart`, which checks the version and then calls `checkRunnable`, then
  `attachNewTx`;
- resume: `resumeTx` (`internal/workitems/store.go` around lines 594-615), which checks
  `ErrVersionConflict`, then terminal, then `ErrExecutionActive`.

So the active-execution and stale-version checks are already enforced at fulfil.

### Executions

The table is `work_item_executions` (`store.go` lines 75-95). Phases are `Pending`,
`Running`, `Succeeded`, `Failed` and `Error` (`types.go` lines 87-91). `openPhasesSQL =
('Pending','Running')`, and the partial unique index `work_item_executions_one_open`
allows at most one open execution per item.

A phase changes only through `AttachExecution` re-posting the same `(engine,
engine_ref)` with a new phase (`store.go` around lines 823-870). A terminal phase never
changes again. Ending an execution does not bump the item's `state_version`.

Temporal executions use `engine_ref` `<workflow_id>#run_<run_id>`, or
`<workflow_id>#<request_id>` when dispatched from a request (see
`handlers_dev_loop.go` around line 166 and `OpenExecutionsOfEngineRun`, `store.go`
around line 797). Nothing in mctl-api closes an execution whose owner has died.

### Temporal access

`DevLoopClient` (`internal/api/interfaces.go:114`) offers `DescribeDevLoopExecution`
(the latest run only) and `DevLoopEnded(wf, runID)`. `temporalclient.statusName`
(`internal/temporalclient/client.go:282`) maps Temporal statuses to Running, Completed,
Failed, Canceled, Terminated, ContinuedAsNew, TimedOut and Unknown.

### Switch pattern

`MCTL_SUBMIT_CREATES_EXECUTION` is parsed once in `cmd/api/main.go`:

- `SubmitCreatesExecutionRaw` at line 1606;
- `operations.ParseSubmitCreatesExecution` at line 1016;
- validated in `validate()` at line 2017;
- passed to the router (`router.go:270`, `SubmitCreatesExecution bool`).

`workitems.NewStore` takes `StoreOption`s (`WithClock`, `store.go` around line 213).
Background tickers are started in `cmd/api/main.go` around lines 268-320.

### Tests and docs

Real-Postgres tests skip unless `TEST_DATABASE_URL` is set
(`internal/workitems/store_test.go:15`). The API-level grant tests in
`internal/api/handlers_dev_loop_grant_test.go` use `workItemsEnv` helpers
(`startDevLoopRun`, `requestDevLoopGrant`, `approveDevLoop`) against the real store.

The docs that describe this behaviour are:

- `docs/work-context-contract.md` section "Execution requests (mctl-api#368)", around
  lines 550-580, which documents 409 `execution_active` at create;
- the MCP tool text at `internal/mcp/workitems.go:171`;
- the OpenAPI spec at `internal/openapi/openapi.yaml`.

### Deployed state checked

- `mctl_list_services(team=admins)`: mctl-agents-worker, -exec and -implement at 1.117.0
  (the worker image is 1.115.0), plus web, docs, support, design and umami. mctl-api
  itself is not a catalogue tenant service, so its deployed env vars (and whether
  `MCTL_SUBMIT_CREATES_EXECUTION` or the dispatcher is enabled) could not be observed
  there.
- `$MCTL_GITOPS_ROOT` grep for `MCTL_SUBMIT_CREATES_EXECUTION`,
  `EXECUTION_REQUEST_DISPATCHER` and `MCTL_AGENT_RECEIPT_GATE`: matches only in
  `agents-state/` proposal documents, not in any deployed values file. The mctl-api Helm
  values are not under `services/` in this checkout. The deployed switch state is
  unobserved, not absent (see Open questions in requirements.md). The new switch defaults
  to off, so the design does not depend on it.

## Proposed solution

### 1. Switch

Add the following in `internal/workitems/queue_switch.go`:

- `const QueueWhileActiveEnv = "MCTL_EXECUTION_REQUEST_QUEUE_WHILE_ACTIVE"`;
- `func ParseQueueWhileActive(raw string) (bool, error)`: `""` and `off` give false, `on`
  gives true, anything else is an error;
- `StoreOption WithQueueWhileActive(bool)`, which sets `Store.queueWhileActive`.

In `cmd/api/main.go`:

- add `ExecutionRequestQueueWhileActiveRaw` to the config struct;
- read the variable next to `SubmitCreatesExecutionRaw` (around line 1763);
- validate it in `validate()` (around line 2017), so an invalid value refuses to start;
- pass the option where the work-items store is constructed.

The flag lives in the store because every decision it changes (create, claim,
reconcile) is a store transaction.

### 2. Create

Split `checkRunnable` into `checkRunnable(cur, execs, kind, from, allowActive bool) (activeID
string, err error)`. When `allowActive` is true and the only finding is an open
execution, it returns that execution's id and no error. The terminal check still runs
first, and the kind and `from` checks still run after the active check, so every other
refusal is unchanged. `checkStart` (fulfil) always passes `allowActive=false`, which keeps
the fulfil-time guard.

`CreateExecutionRequest` passes `s.queueWhileActive`. When an `activeID` comes back, it
adds `queued_behind_execution_id` to the `execution_requested` event detail and sets a
non-persisted response field `QueuedBehindExecutionID string
json:"queued_behind_execution_id,omitempty"`.

Nothing else changes: same INSERT, same `remember`, same advisory lock, same
`work_item_execution_requests_one_open` index. So:

- replay works whether the execution is open or closed (`replayed()` runs before any
  check);
- no duplicate is possible;
- the actor, principal ids, intent, surface, idempotency key and
  `expected_state_version` are stored exactly as given.

A start request while an execution is open is still refused by the kind rule ("already
ran; request kind resume"), because it can never be fulfilled.

### 3. Claim guard

When `s.queueWhileActive` is true:

- The candidate query adds `AND NOT EXISTS (SELECT 1 FROM work_item_executions e WHERE
  e.work_item_id = r.work_item_id AND e.phase IN openPhasesSQL)`. Blocked items do not use
  the 8-candidate budget. The one-open index makes this lookup an index probe.
- Inside the per-candidate transaction, after taking the item lock and before the
  compare-and-set UPDATE, `listExecutions` is re-checked. If an execution is open, the
  candidate is skipped without being touched, so no claim event is written. This closes
  the race between the candidate scan and the lock.

When the switch is off, both additions are skipped, so the SQL text and behaviour are
identical to today.

### 4. Fulfil

No change. `resumeTx` and `checkStart` already reject a stale `expected_state_version`
(`state_version_conflict`) and an open execution (`execution_active`). The dispatcher
then rejects the request (stale version) or defers it (active execution), as
mctl-agents' dispatcher already does.

### 5. Orphan reconciliation

Reconciliation lives in mctl-api, with mctl-agents#993 as a complement. Only mctl-api
can close an execution without a running loop, and it already holds the Temporal client.

Store additions (`internal/workitems/orphans.go`):

- `OpenExecutionsWithQueuedRequests(ctx, engine string, olderThan time.Time, limit int)
  ([]Execution, error)`: open executions of the given engine that have at least one open
  request, with `started_at <= olderThan`, oldest first, bounded by `limit`.
- `CloseOrphanedExecution(ctx, OrphanCloseInput{ExecutionID, ExpectedPhase,
  EngineStatus, Mutation}) (*Execution, bool, error)`. Under `"workitem:"+item`, it runs
  `UPDATE work_item_executions SET phase='Error', ended_at=now WHERE id=$1 AND phase=$2`.
  If no row matches, it returns `closed=false` (another writer ended it first). It
  appends an `execution_orphan_closed` event with `{execution_id, engine_ref,
  engine_status}`. The actor is the service principal (`auth.NewServiceUser`).

Temporal addition: `DescribeDevLoopRun(ctx, workflowID, runID string)
(*temporalclient.DevLoopExecution, error)` on `Client` and `Reconnecting`. It calls
`DescribeWorkflowExecution(wf, runID)`, and a not-found result is a typed `ErrRunNotFound`.
This is added to `DevLoopClient`.

Sweeper (`internal/api/execution_orphan_reconciler.go`, `ReconcileOrphanedExecutions(ctx)`):

- Started from `cmd/api/main.go` on a 2-minute ticker, only when the switch is on and
  both the work-items store and the Temporal client are configured.
- For each candidate (minimum age 5 minutes, limit 20 per tick), it parses `engine_ref`:
  - `<wf>#run_<id>` describes that run;
  - `<wf>` or `<wf>#xr_...` describes the latest run, but only when that run started
    before the execution did. Otherwise it skips, because it cannot prove which run owns
    the execution.
- It closes the execution only on Completed, Failed, Canceled, Terminated, TimedOut or
  `ErrRunNotFound`.
- On Running, ContinuedAsNew, Unknown or any other error, it logs (`slog`) and skips.
  This is fail closed: an unreadable answer is never "dead".
- A Temporal-closed run is marked `Error`, never `Succeeded`, because its outcome was not
  reported.

Once the orphan is closed, the claim guard lets the queued request through on the next
claim.

### 6. Docs

- `internal/openapi/openapi.yaml`: on `POST /work-items/{id}/execution-requests`, document
  the 201 response with `queued_behind_execution_id`, and note that 409 `execution_active`
  is returned only when the switch is off.
- `docs/work-context-contract.md`: a "Queued while active" subsection covering the
  switch, the claim guard, orphan closure, the `execution_orphan_closed` event and the
  fulfil-time stale-version rule.
- `internal/mcp/workitems.go:171`: tool text saying that a resume while an execution is
  running is either queued (returned pending, delivered after the execution ends) or
  refused with `execution_active`, depending on server configuration.
- `docs/adr/0001-queue-execution-request-while-active.md`: the decision, the rejected
  variant (c) and the rollout gate.

## Alternatives

- **Record refusals in a separate deferred-request table and replay them later.** This was
  dropped because it duplicates the request lifecycle (idempotency, one-open, fencing),
  and the existing `pending` state already means "durable, not yet delivered".
- **Keep refusing at create and make surfaces retry.** This was dropped because it does
  not meet the owner's "must not be lost" requirement and puts retry state in every
  surface.
- **A second execution on the same WorkItem (variant c).** The owner ruled this out: it
  is also non-terminal during implement, so the one-open-execution index gives the same
  409.
- **Orphan reconciliation only in mctl-agents (#993).** This was dropped as the sole
  mechanism because a terminated loop runs no code, and with no claimable request the
  dispatcher's `_reconcile_closed_loops` never fires. mctl-api's sweeper does not depend
  on either.
- **An unconditional claim guard.** This was dropped because it would change switch-off
  behaviour (a request created before a direct `AttachExecution` would no longer be
  claimed and rejected), which breaks the "off is byte-for-byte today's" rule.

## Platform impact

- **Migrations:** none. No new columns. The event kind is a new string in the existing
  `work_item_events.kind` text column.
- **Backward compatibility:**
  - With the switch off, nothing changes.
  - With it on, a client that relied on a 409 to learn that a loop is busy now gets a 201
    `pending` request. The mctl-agents dispatcher already handles `execution_active` at
    fulfil.
  - Telegram's "already running" message becomes unreachable for resume while the switch
    is on. That is acceptable; the copy can be adjusted later.
- **Resources:**
  - One extra `NOT EXISTS` index probe per claim candidate scan.
  - The sweeper makes at most 20 Temporal describe calls every 2 minutes, and only for
    items that have a queued request.
- **Risks and mitigations:**
  - The sweeper could close a live execution. Mitigations: run-specific describe,
    fail-closed handling of Unknown, errors and ContinuedAsNew, the minimum age, and the
    compare-and-set on phase.
  - Queued requests may all go stale on `state_version`. Mitigation: fulfil rejects them
    explicitly with `state_version_conflict`. The meaning of resume is an mctl-agents
    follow-up.
  - Argo and a2a orphans are not covered. This is documented and left to mctl-agents#993.
- **Rollout:** release with the switch off, then turn it on in mctl-gitops, then enable
  the mctl-agents dispatcher, then run the #992 tests and spec amendment, then a new
  approval, then #992 leaves draft.
