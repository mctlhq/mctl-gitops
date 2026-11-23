# Design: issue-41-spike-mcp-tasks-over-durable-temporal-ar

Revision 2. It supersedes revision 1 of this proposal (committed
2026-11-22T01:52Z), which received REQUEST_CHANGES (2 P1, 4 P2) from an
independent review.

## Current state

### Evidence pins (read 2026-11-22)

| Source | Pin | What was read |
| --- | --- | --- |
| mctlhq/.github | `60e9db5` (clone HEAD) | `roadmap/spikes/mcp-tasks-durable-execution.yaml`, `roadmap/schemas/spike-definition.schema.json`, `roadmap/scripts/validate.py`, `roadmap/tests/test_validate_spike.py`, `roadmap/requirements.txt`, `docs/spikes/automation-control-plane/` layout, AGENTS.md `[CODE]` |
| mctlhq/mctl-api | `80f7a011c975422a6bb632022f5538d59772928f` (main) | `go.mod`, `internal/mcp/server.go`, `internal/temporalclient/client.go`, `internal/workitems/execution_requests.go` (blob `913924a334a8e92daada1bf8370a409d2a47f0b0`, the blob the reviewer cited), `internal/workitems/store.go`, `internal/workitems/orphans.go` `[CODE]` |
| mctlhq/mctl-agents | `eec4fdd865491d89d221a2bd2b8ed40fab65ef23` (main) | `docs/adr/013-human-input-contract.md` `[CODE]`; revision 1 read `orchestrator/temporal/workflows/action_approval.py` at `05c1dc8` |
| Spec | https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks (retrieved 2026-11-22) | input_required, resultType, ttlMs, tasks/update, Mcp-Name, errors, notifications `[DOC]` |

### In this repository

- `roadmap/spikes/mcp-tasks-durable-execution.yaml` has the following
  values:
  - `lifecycle: proposed` and `outcomes: GO_ADAPTER_IN_MCTL_API |
    GO_UPSTREAM_ONLY | NO_GO`;
  - `timebox.decisionBy: 2026-12-15` and owner `mctlhq/mctl-agents`;
  - no `evidence.report` and no `decision`.

  The header comment says the Portal half is dropped: the gateway passes
  Tasks through, and its G2 checks that. It also says the executable pilot
  is mctl-api#284.
- `roadmap/schemas/spike-definition.schema.json` defines the shapes:
  - `outcome` matches `^[A-Z][A-Z0-9_]*$`;
  - `evidence.report` is a relative path;
  - `decision` is allowed only when the spike is decided.
- `roadmap/scripts/validate.py` (around lines 388-395) refuses a
  `decision.verdict` that is not in `spec.outcomes`. That makes the manifest
  outcome list the only machine-checked vocabulary (P2-TS-06).
- `roadmap/requirements.txt` pins `jsonschema==4.25.1` and `PyYAML==6.0.2`.
  That gives an independent schema validator outside the Go model
  (P2-TS-05).
- `docs/spikes/automation-control-plane/` is the precedent layout:
  - `model/`, `fixtures/`, `schemas/`;
  - `harness_test.go`, `negative_test.go`, `regression_test.go`;
  - an opt-in `temporal-integration/` module with its own `go.mod`.

### In mctl-api `[CODE]`

- `go.mod` pins `github.com/mark3labs/mcp-go v1.0.0` and
  `go.temporal.io/sdk v1.50.0`.
- `internal/mcp/server.go`:
  - `server.WithStateLess(true)` (line 246), so there is no session;
  - `server.WithResourceCapabilities(false, false)` (line 285);
  - no `WithTaskCapabilities`, so the server advertises no Tasks today.
- mcp-go v1.x implements the legacy SEP-1686 shape: `tasks/list`,
  `tasks/result`, an in-memory `tasks` map and a goroutine executor (read in
  revision 1). The adapter must never enable it.
- `internal/temporalclient/client.go` has these methods:
  - `StartDevLoopWorkflow`, `DescribeDevLoopExecution` and
    `DescribeDevLoopRun`;
  - `SignalApprove` and `SignalAbandon`;
  - `QueryHumanInputState` (line 456) and `SignalHumanInputResponse`
    (line 479).

  There is no generic `RequestCancel`.
- `internal/workitems/execution_requests.go` (the P1-TS-02 evidence):
  - `Store.CreateExecutionRequest` (line 367) runs its own
    `s.withTx(ctx, "workitem:"+in.WorkItemID, ...)` (line 373). Inside it:
    `getItem`, then `replayed(...opExecutionRequest, in.Mutation)` (replay
    keyed on `(work_item_id, idempotency_key)`), then the
    `expected_state_version` check, then `openExecutionRequest`
    (`OpenRequestError`), then `checkRunnable`, then the INSERT with state
    `pending`, then `appendEvent`, then `remember`.
  - The id is `ExecutionRequestIDPrefix + uuid.NewString()` with dashes
    removed. That is a UUIDv4, with 122 random bits.
  - The unique index `work_item_execution_requests_one_open` allows at most
    one pending or claimed request per item.
  - `ClaimExecutionRequest` (line 495) scans open requests with
    `claimCandidateSQL` outside any lock, then locks each item. A pending
    `xr_` can therefore be claimed by the dispatcher as soon as its
    transaction commits.
- `internal/workitems/store.go`:
  - `withTx` (line 269) begins a transaction, takes
    `pg_advisory_xact_lock(hashtext(lockKey))`, runs `fn`, and commits;
  - `rememberCreate` writes `work_item_create_requests`
    `(tenant, idempotency_key, request_hash, ...)`;
  - `replayed` and `remember` use `work_item_requests`.

  These helpers are package-private. No public API composes two mutators in
  one transaction.
- `internal/workitems/orphans.go` has `OpenExecutionsWithQueuedRequests` and
  orphan close (`execution_orphan_closed`). This is a precedent for a
  recovery sweep paged by `(started_at, id)`.

### In mctl-agents `[CODE]`

- `docs/adr/013-human-input-contract.md`:
  - The request is sealed and content-addressed (`request_hash`,
    `request_id = "hir-" + request_hash[7:23]`, `question_hash`).
  - `expires_at` is hash-covered and clamped by `MAX_REQUEST_TTL_SECONDS`.
    Rounds are bounded by `MAX_CLARIFICATION_ROUNDS`.
  - `validate_response` checks respondent membership in
    `requested_from.actor_refs`, request id and hash, and expiry.
  - "Clarification is not approval": `WAITING_FOR_INPUT` and
    `WAITING_FOR_APPROVAL` are distinct gates.
  - "A human respondent": the only respondent is the issue author, and a bot
    author is discarded.
  - Continuation records `respondent` and `surface` per answer.
  - There is no field that says which surfaces or assurance levels may
    answer (P2-TS-03 gap).
- `ApprovalWaitWorkflow` (revision 1 read, `action_approval.py`) waits on
  the `{"approval_id": "aar_..."}` signal with a durable timer. Its outcomes
  are `ran | denied | expired | consumed | mismatch`.

### Spec facts `[DOC]` that drive this revision

- `input_required`: "The `inputRequests` field MUST contain all outstanding
  requests from the server to the client". The entries are elicitation or
  sampling payloads. An approval on an out-of-band page is neither
  (P1-TS-01).
- `resultType` MUST be `"complete"` on the `tasks/get`, `UpdateTaskResult`
  and `CancelTaskResult` results. A create returns `"task"` (P2-TS-05).
- `ttlMs`: "Time-to-live duration from creation ... null for unlimited". It
  "MAY change over the lifetime of a task". After it elapses, a server MAY
  mark the task failed and delete it (P2-TS-04).
- `tasks/update`: "Each key MUST correspond to a currently-outstanding
  inputRequest key". Servers SHOULD ignore keys that are not outstanding,
  and MAY accept partial sets.
- The client MUST set `Mcp-Name` to `params.taskId` on `tasks/*`.
- Error codes: `-32602` for an unknown task, `-32603` for an internal error,
  `-32021` for a missing client capability.
- `notifications/tasks` via `subscriptions/listen` carries the full
  `tasks/get`-equivalent state.

### Deployed state checked

- `mctl_get_service_status(team=admins, service=mctl-agents-worker)`
  `[LIVE]`: Argo CD `Healthy` and `Synced`, `imageTag 1.117.0`, updated
  2026-11-22T18:06:58Z.
- `services/admins/mctl-agents-worker/values.yaml` `[CONFIG]`:
  `replicaCount: 1`, `image.tag "1.117.0"`, `TEMPORAL_NAMESPACE:
  mctl-agents`, `EXECUTION_REQUEST_DISPATCHER: "true"`. The dispatcher that
  claims `xr_` is live, so an orphan pending `xr_` would really be
  dispatched.
- `services/admins/mctl-agents-worker-exec/values.yaml` `[CONFIG]`:
  `replicaCount: 1`, tag `1.117.0`, namespace `mctl-agents`.
- `services/` listing `[CONFIG]`: no `mctl-api` directory under any tenant
  (`admins`, `karabu`, `labs`, `namax66`, `redloop`). mctl-api's deployed
  image, flags and live Tasks behaviour are `unknown (not observed)`, not
  absent.
- Not observed: `api.mctl.ai/mcp` `server/discover`, Portal pass-through,
  and every AI host. All are `unknown`.

## Proposed solution

### Finding-to-change matrix

| Finding | Revision 1 | Revision 2 change | Proof (Phase 0) | Proof (later gate) |
| --- | --- | --- | --- | --- |
| P1-TS-01 | approval wait -> `input_required`, no `inputRequests` | Approval wait and human-only input map to `working` + advisory `statusMessage`. `input_required` only with a non-empty elicitation `inputRequests`, and only for client-relayable input. Section 3. | N3, N4, S1-S3 (schema negatives) `[MODEL]` | G2 host run |
| P1-TS-02 | "one transaction" over public mutators | Design A: new `Store.CreateTaskExecution` in one `withTx`, with a lock order, commit order, collision rules and a recovery sweep. Design B documented as the fallback. Section 5. | Commit-order model with injected crash points `[MODEL]`, explicitly not an atomicity proof | G1 Postgres fault injection in mctl-api |
| P2-TS-03 | owner may answer any key | Typed form elicitation only, plus respondent policy, `actor_ref` match, freshness, hash, scope, credential class and `client_id`. Never an approval path. Section 7. | N5-N10 `[MODEL]` | G1 + mctl-agents ADR 013 extension |
| P2-TS-04 | `ttlMs` 24 h default, 7 d max | `ttlMs: null` while non-terminal, terminal-only expiry, idempotency scope outlives the row, WorkItem fallback. Section 10. | T21-T23 (8-day approval with a fake clock) `[MODEL]` + `[TEMPORAL_DEV]` time-skipping | G1 |
| P2-TS-05 | only create shape tested | Pinned official schema, independent Python `jsonschema` check of every fixture, `Mcp-Name` exactness, negotiation negatives. Section 12. | S1-S12 | G2 |
| P2-TS-06 | two vocabularies, silent `GO_ADAPTER_IN_MCTL_API` | Manifest vocabulary is canonical. One map in the report. A consistency check. Recommendation, not decision. Section 13. | C1-C3 | owner decision |

### 1. Layering and ownership (unchanged from revision 1)

```text
MCP host --(tools/call, tasks/*)--> mctl-api internal/mcp    [protocol adapter, mctl-api]
                                      | mcp_tasks: protocol binding only
                                      v
                 workitems.Store: wi_ / xr_ / we_ / cs_        [canonical identity, mctl-api]
                                      v
           dispatcher claims xr_ -> Temporal workflow          [execution owner, mctl-agents]
                                      v
                        Argo / CI / deploy / agent worker
```

mctl-agents owns execution semantics: states, gates and cancellation
boundaries. mctl-api owns the adapter and the protocol table. The adapter
never starts Temporal itself, because the dispatcher is the only start
path.

### 2. Protocol state vs execution state

`mcp_tasks` holds only the protocol binding:

- identity and owner: `task_id`, `tenant`, `owner_principal_id`,
  `client_id`;
- the call: `tool`, `args_digest`, `idempotency_key`;
- the canonical links: `work_item_id`, `execution_request_id`;
- protocol timing: `created_at`, `terminal_observed_at`, `expires_at`
  (null while non-terminal), `cancel_requested_at`;
- `schema_version`.

It has no status column. Status is derived on every read (section 3).

### 3. Lifecycle mapping (revised, P1-TS-01)

The first matching row wins.

| Canonical state | MCP `status` | Payload |
| --- | --- | --- |
| any read of the store or Temporal fails | JSON-RPC `-32603` | none; never a status |
| `xr_` rejected with reason `cancelled_by_task` (cancel before `we_`) | `cancelled` | |
| `xr_` rejected, any other reason | `failed` | `error` (`execution_request_rejected`), `statusMessage` |
| `xr_` pending/claimed, no `we_` | `working` | |
| Temporal `Completed`, tool success | `completed` | `result` |
| Temporal `Completed`, business refusal | `completed` | `result` with `isError: true` |
| Temporal `Canceled` | `cancelled` | |
| Temporal `Failed`, `TimedOut`, `Terminated` | `failed` | classified `error`, diagnostic `statusMessage` |
| Running, `WAITING_FOR_INPUT`, request `respondent_policy` allows `mcp/client_relayed`, and the caller is an allowed respondent | `input_required` | `inputRequests: {<request_id>: elicitation form request built from the sealed ResponseSpec}` |
| Running, `WAITING_FOR_INPUT`, policy does not allow MCP or the caller is not a respondent | `working` | `statusMessage`: "waiting for human input on another surface" |
| Running, `INPUT_TIMED_OUT` | `working` | the workflow decides the outcome |
| Running, `WAITING_FOR_APPROVAL` / `ApprovalWaitWorkflow` with `aar_` pending | `working` | advisory `statusMessage`: "waiting for owner approval". It includes the `decide_url` only if the caller is authorized to decide that grant (same check as `mctl_get_dev_loop_approval`). Otherwise no link and no grant content. |
| Running, otherwise | `working` | "cancellation requested" if `cancel_requested_at` is set |

Rules:

- An `input_required` result always has a non-empty `inputRequests` map.
- An approval never produces `input_required` or an `inputRequests` entry.
- The `statusMessage` "MAY be exposed to the end-user or model" `[DOC]`.
  A decide link therefore never confers anything: the decide page itself
  requires a fresh sign-in with a second factor and checks the grant's
  `artifact_hash` and `context_digest`.

Alternative evaluated and rejected for the pilot: a URL-mode elicitation
pointing at the decide page. It would be a well-formed `inputRequest`, but:

- the client's accept or decline answer would travel on `tasks/update`,
  the same path as client input, which P2-TS-03 forbids;
- hosts may render "accept" as consent;
- URL-mode support in the 2026-07-28 Tasks flow and in hosts is
  `unknown (not observed)`.

### 4. Task identity

- `taskId = "tk_" + base32(16 bytes from crypto/rand)`. It is never a
  Temporal workflow id (DevLoop ids derive from issue URLs) and never the
  `xr_` id (122 bits, already shown to callers of WorkItem tools).
- Every `tasks/*` call re-authorizes the caller and then compares `tenant`
  and `owner_principal_id`.
- A mismatch, unknown, malformed or expired id all return the same
  `-32602`.
- `Mcp-Name` must equal `params.taskId` byte for byte. Otherwise the call
  gets `-32602`, before any lookup, so the check reveals nothing.

### 5. Durable create-before-return (revised, P1-TS-02)

Revision 1's "one transaction" was false. A controller cannot wrap
`CreateWorkItem` and `CreateExecutionRequest` in one transaction, because
each commits inside its own `withTx`. The failure mode is concrete: a crash
after the `xr_` commits but before the `mcp_tasks` insert leaves a pending
`xr_`. The live dispatcher (`EXECUTION_REQUEST_DISPATCHER: "true"`) then
claims and runs it, while no handle exists. A retry would then see
`OpenRequestError`, not the original task.

**Design A (recommended): one transactional `Store` method in package
`workitems`.**

```go
// CreateTaskExecution creates or joins the work item, creates the start
// request and inserts the task binding in ONE transaction.
func (s *Store) CreateTaskExecution(ctx context.Context, in TaskExecutionInput) (*TaskBinding, bool /*replayed*/, error)
```

Steps inside a single `pgx.Tx`:

1. **Lock 1:** `pg_advisory_xact_lock(hashtext("mcp-task:"+tenant+"|"+owner_principal_id+"|"+tool+"|"+idempotency_key))`.
2. **Scope lookup.** `SELECT` from `mcp_task_scopes` for the scope:
   - found with an equal `args_digest`: return the stored `task_id` (replayed);
   - found with a different digest: `idempotency_key_reused`.
3. **Create or join `wi_`.** Use the package-private create path with
   `rememberCreate`, keyed by `(tenant, derived key "mcp-task:"+task_id)`.
4. **Lock 2:** `pg_advisory_xact_lock(hashtext("workitem:"+wi_id))`. This is
   the same key existing mutators use, so they stay serialized.
5. **Create `xr_`.** Run the body of `CreateExecutionRequest`, refactored
   into `createExecutionRequestTx(ctx, tx, in)`, with
   `Mutation.IdempotencyKey = "mcp-task:"+task_id`.
6. **Insert the binding.** INSERT `mcp_tasks` and `mcp_task_scopes`. The
   unique index on the scope is the backstop.
7. **COMMIT.** Only then does the server write `CreateTaskResult` to the
   wire.

Properties:

- **Lock order.** It is always scope lock, then item lock. No existing
  mutator takes a scope lock, so no cycle exists.
- **Commit order.** One commit holds the `wi_`, the `xr_` and the binding.
  The dispatcher's claim scan can see the `xr_` only after the binding is
  visible.
- **Collision handling.** Two racing creates on the same scope serialize on
  lock 1. The loser replays or fails at step 2. A unique violation at step 6
  maps to replay after a re-read. It is never a 500 and never a second
  `xr_`.
- **Crash.** A crash at any step rolls everything back. A retry is a fresh
  create, and the client has never seen a `taskId`.
- **Refactor cost.** `CreateExecutionRequest` becomes a thin wrapper around
  `createExecutionRequestTx`, so its behaviour stays identical. This is
  checked by the existing `execution_requests_test.go`.
- **Migration.** Two additive tables, `mcp_tasks` and `mcp_task_scopes`,
  created with the existing `CREATE TABLE IF NOT EXISTS` schema style.

**Design B (fallback if A is refused): durable protocol intent first.**

1. Commit a `mcp_task_scopes` row in state `reserving`, with `task_id`,
   the derived keys and `args_digest`.
2. Call the public `CreateWorkItem`, using the derived idempotency key.
3. Call the public `CreateExecutionRequest`, using the derived mutation key.
   Both are replayable through `work_item_create_requests` and
   `work_item_requests`.
4. Mark the row `bound`. Only then return.

Retry and recovery under B:

- A retry that finds `reserving` re-runs steps 2-4 idempotently and
  returns the same `taskId`.
- A recovery sweep, paged like `OpenExecutionsWithQueuedRequests`, finishes
  `reserving` rows older than a bound.
- An `xr_` can exist without a bound row only while a `reserving` row names
  it. The execution then runs before the handle is bound, which is
  acceptable because the retry or the sweep binds it.

B is weaker: it has a window in which the execution runs before the handle
exists, and it depends on the retention of the inner idempotency rows (an
open question).

**Phase 0 proof boundary.** The Go model implements A and B against a fake
store, with injected crash points before and after each step. It shows the
commit-order and replay invariants `[MODEL]`. It does NOT prove Postgres
atomicity, lock behaviour or index backstops. Those are gate G1: Postgres
fault-injection tests in mctl-api, run with a real Postgres and a killed
connection at each step. G1 needs owner approval.

### 6. Idempotency

- Every task-capable tool takes an explicit `idempotency_key` argument,
  matching the existing `mctl_create_work_item` convention.
- MCP has no stable request key under `WithStateLess(true)`. The JSON-RPC
  `id` is per connection.
- The scope is `(tenant, owner_principal_id, tool, idempotency_key)`, with
  `args_digest` over canonical JSON arguments without `_meta`.
- A missing key on a consequential tool is refused.

### 7. `tasks/update` trust boundary (revised, P2-TS-03)

Allowed response types:

- form-mode elicitation responses (`action: accept` with `content`, or
  `decline`/`cancel`) to ADR 013 requests;
- no sampling and no URL-mode elicitation.

The server processes each `inputResponses` entry in order. It ignores and
audits any entry that fails a check:

1. **Credential class.** Service, agent and relayed-surface credentials are
   refused for the whole call, and for `tasks/cancel` too. mctl-api already
   refuses such credentials for approvals.
2. **Task ownership.** Same as `tasks/get`.
3. **Key.** It must equal the currently open `request_id` from
   `QueryHumanInputState`. Any other key is ignored with reason `not_open`.
   That covers already-answered keys, keys from a prior round, `aar_` ids
   and arbitrary strings.
4. **Respondent policy.** The sealed request's `respondent_policy` must list
   `{surface: mcp, assurance: client_relayed}`. This is a new ADR 013 field,
   owned by mctl-agents. A request without it is never emitted as an
   `inputRequest` and is never answerable here (`policy_denied`).
5. **Respondent identity.** The caller's canonical principal must resolve
   to a member of `requested_from.actor_refs` (`respondent_mismatch`).
6. **Freshness.** `now < effective_deadline` and the round count is below
   `MAX_CLARIFICATION_ROUNDS` (`expired`, `rounds_exhausted`).
7. **Typed validation.** `content` must validate against the sealed
   `ResponseSpec`, within the ADR 013 limits (2000 code points, 8000 chars
   compact JSON) (`invalid_value`).
8. **Binding.** The server forwards with
   `SignalHumanInputResponse(workflowID, runID, {request_id, request_hash,
   value, respondent, surface: "mcp", assurance: "client_relayed",
   client_id, received_at})`. The workflow's own `validate_response`
   re-checks id, hash, expiry and respondent. The adapter's checks never
   replace it.

Rules for the whole call:

- `UpdateTaskResult{resultType: "complete"}` is returned whatever happened
  to the entries. The truth comes from the next `tasks/get`.
- No code path from `tasks/update` reaches `SignalApprove`, an approval
  grant mutation or the `ApprovalWaitWorkflow` signal. A test asserts this
  with a call-graph spy in the model.
- **OAuth-client boundary:**
  - `tasks/get` and `tasks/cancel` are allowed from any OAuth client of the
    owning principal, which is the reconnect-across-hosts goal;
  - `tasks/update` records `client_id` on the answer;
  - for a task whose policy says `same_client`, `tasks/update` also requires
    the creating `client_id`. Pilot default: `any_client_of_owner`.

### 8. Approval handoff

- The task stays `working` (section 3).
- The owner decides on the existing decide page. mctl-api signals
  `ApprovalWaitWorkflow` exactly as today, bound to `aar_` `artifact_hash`
  and `context_digest`.
- MCP Apps (#376) may display the same canonical status. They never decide.

### 9. Cancellation

This section is unchanged from revision 1, with one addition: the
acknowledgement is `CancelTaskResult{resultType: "complete"}`.

- A new `temporalclient.RequestCancel(workflowID, runID)` is needed later.
- With no `we_` yet, cancel rejects the `xr_` under the item lock.
- Each workflow declares its boundary:
  - input or approval wait: cancels at once;
  - activity: heartbeat cancel, then cleanup;
  - Argo: stop, then wait for its terminal phase;
  - external CI or deploy past the point of no return: completes the step
    and records its side effects, and may end `completed`.
- The first terminal state recorded by Temporal wins.
- A cancel after a terminal state is a no-op acknowledgement.

### 10. TTL and retention (revised, P2-TS-04)

- **Non-terminal (`working` or `input_required`):** `ttlMs: null`. The
  extension defines null as unlimited, and the value MAY change. The task is
  never expired, failed or deleted while the execution lives. That holds for
  a week-long approval and for any wait bounded by the workflow's own
  durable timer.
- **Terminal:** on the first read that observes a terminal state, set
  `terminal_observed_at`. From then on report
  `ttlMs = (terminal_observed_at - created_at) + terminal_retention`, with a
  default of 24 h and a maximum of 7 d.
- **After expiry:** answer `-32602`, and a sweeper deletes the `mcp_tasks`
  row. The `mcp_task_scopes` row stays for `terminal_retention` + the `xr_`
  replay window (open question: that window's retention). A retry inside
  that window replays the same `taskId`, which then returns `-32602`; the
  caller falls back to the WorkItem tools. A retry after that window creates
  a new work item, which is a documented, bounded behaviour.
- **Reclamation:** a task whose execution was closed by
  `execution_orphan_closed` reads as `failed` with
  `error.data.reason = execution_orphaned`. It is then reclaimed like any
  terminal task.
- **Fallback:** `wi_`, `we_`, audit and Temporal history keep their own
  retention. `mctl_get_work_item` and `mctl_list_work_item_executions` still
  return the result.

### 11. Revocation, fencing, audit, notifications, fallback

These points are unchanged from revision 1:

- Authority is re-checked on every call, and the action-time checkpoint
  denies a revoked principal's side effects (#375).
- Lifecycle-ownership fencing stays authoritative, and the adapter never
  acquires ownership.
- Audit records `taskId`, `wi_`, `xr_`, `we_`, method, per-entry reason code,
  principal, `client_id` and tenant, and never content.
- Polling only: `pollIntervalMs` is 5 s while `working` and 30 s while
  `input_required`.
- A future `notifications/tasks` stream from #377 would be a projection of
  the same canonical transition, deduplicated on `(taskId, lastUpdatedAt)`.
- Non-negotiating clients get a `CallToolResult` with `wi_`/`xr_`
  references.

### 12. Conformance (revised, P2-TS-05)

- `schemas/vendor/` holds the official Tasks extension JSON Schema, copied
  at a pinned upstream commit, with its sha256 recorded in the report. If
  the official schema cannot be obtained as a file, the report says so, and
  hand-written schemas are marked `[DOC]-derived`, not official.
- `fixtures/responses/` holds one golden JSON per variant:
  - create;
  - get in each of the five statuses;
  - update acknowledgement;
  - cancel acknowledgement;
  - each error code.
- `fixtures/negative/` holds the negatives. Each must FAIL validation or be
  refused:
  - `input_required` without `inputRequests`, and with an empty map;
  - `completed` without `result`;
  - `failed` without `error`;
  - `resultType: "task"` on get;
  - `resultType` missing on update or cancel;
  - `inputRequests` on `working`;
  - a sampling entry from the pilot;
  - approval content inside `inputRequests`.
- `checks/validate_fixtures.py` runs `python -I` with `jsonschema==4.25.1`
  over both directories. It has no import from the Go model, so it is an
  independent check.
- Transport tests in the Go model:
  - `Mcp-Name` missing, different case, trailing space or another task's id
    -> `-32602`;
  - an undeclared extension on the request -> `CallToolResult` and
    `-32021` on `tasks/*`;
  - the extension declared only in an earlier request -> still `-32021`,
    because negotiation is per request;
  - `tasks/list` and `tasks/result` -> method not found.

### 13. Verdict vocabulary (revised, P2-TS-06)

The manifest `spec.outcomes` is canonical, because `validate.py` enforces
it. The report carries the one map:

| Issue outcome | Manifest outcome |
| --- | --- |
| `ADOPT_THIN_TASKS_ADAPTER` | `GO_ADAPTER_IN_MCTL_API` |
| `BOUNDED_PILOT` | `GO_ADAPTER_IN_MCTL_API` with `decision.followUps` limited to mctl-api#284 (one synthetic tool, gates G1-G4) |
| `DEFER` | `NO_GO`, or `GO_UPSTREAM_ONLY` when the only blocker is an SDK or upstream gap |

- The final decision lives only in the manifest `spec.decision`, written by
  the owner. The report links to it.
- Phase 0 adds only `spec.evidence.report:
  docs/spikes/mcp-tasks-durable-execution.md` and leaves `lifecycle`,
  `outcomes` and `decision` alone. That edit is optional and owner-reviewed.
- The report states a recommendation, `BOUNDED_PILOT`, labelled
  "recommendation, not decision".
- `checks/verdict_consistency.py` checks three things:
  - every issue outcome, from a pinned copy in the report header, has
    exactly one mapping row;
  - every target is in the manifest `spec.outcomes`;
  - the report contains no "Decision:" line unless the manifest has
    `spec.decision`.

### 14. Pilot and gates

The pilot is a synthetic `TaskProbeWorkflow`, local only. Other candidates
were rejected as in revision 1: DevLoop (spend and gitops writes), deploy
(production side effects), Telegram (worker boundary not ready).

The workflow runs these phases:

1. a cancellable sleep;
2. a `WAITING_FOR_INPUT` gate with a sealed ADR 013-shaped request whose
   policy allows `mcp/client_relayed`;
3. a second input gate whose policy is human-only, which must surface as
   `working`;
4. an approval-wait gate against a fake grant store;
5. a deterministic result, or a business error on input `fail`.

Decision gates. Each needs a separate review and a digest-bound owner
approval:

- **G0:** Phase 0 complete. The model and offline tests pass, the
  `[TEMPORAL_DEV]` tests pass or are reported as not run, and the
  schema/consistency checks pass.
- **G1:** mctl-api code spike behind #284 on a branch:
  `CreateTaskExecution` (design A) and the two tables, with Postgres
  fault-injection tests. It has no production endpoint.
- **G2:** mcp-go v1.0.0 accepts custom `tasks/*` handlers and the
  `server/discover` extension without the legacy store, measured in one
  real host (Claude Code) against a non-production endpoint.
- **G3:** Portal pass-through of `tasks/*` and `Mcp-Name` (mcp-gateway G2).
- **G4:** an mctl-agents ADR 013 `respondent_policy` extension, before any
  real (non-probe) input is exposed.

What a failed gate means:

- a failed G1 with design B also failing: `NO_GO`;
- a failed G2 caused by the SDK: `GO_UPSTREAM_ONLY`;
- a failed G3: Tasks stay direct-only.

### Host and SDK compatibility (initial)

| Client | Status | Evidence |
| --- | --- | --- |
| Claude Code | public beta from v2.1.304 | `[DOC]` manifest note; unmeasured |
| Claude web/desktop, ChatGPT, Codex, Antigravity, agy, Grok Bot | unknown | not observed |
| mcp-go v1.0.0 (server) | legacy SEP-1686 only | `[CODE]`; never `WithTaskCapabilities`/`AddTaskTool` |

## Alternatives

- **Keep revision 1's `input_required` with no `inputRequests` for
  approvals.** Dropped: it is non-conformant with the spec (P1-TS-01).
- **A URL-mode elicitation to the decide page.** Dropped for the pilot (see
  section 3). It shares the client-input response path and has unknown host
  support.
- **Controller-level composition of the public `CreateWorkItem` and
  `CreateExecutionRequest`, then an insert.** Dropped: it is not atomic
  (P1-TS-02). Design B is the bounded, recoverable form of this idea and is
  kept as the fallback.
- **A synchronous Temporal start in the adapter, using `taskId` = workflow
  id.** Dropped: it creates a second start path next to the dispatcher, and
  the ids are guessable.
- **mcp-go's built-in task store.** Dropped: in-memory, a goroutine
  executor, the legacy method set.
- **A fixed `ttlMs` with renewal on each poll.** Dropped: an abandoned
  client would let a live task expire. Terminal-only expiry is simpler and
  spec-legal (`null`).
- **Adopting the issue vocabulary in the manifest now.** Dropped: it is a
  roadmap change outside a proposed spike's evidence. It remains an owner
  option (see Open questions in requirements.md).

## Platform impact

- **Phase 0:** documentation and self-contained fixtures in mctlhq/.github.
  - no migration, deployment, endpoint, host, real approval or spend;
  - the Temporal tests run only against a developer-started local dev
    server and skip otherwise;
  - the Python checks use already-pinned dependencies.
- **Later (G1, gated):**
  - two additive Postgres tables;
  - one refactor of `CreateExecutionRequest` into
    `createExecutionRequestTx`, which keeps behaviour and is covered by the
    existing tests;
  - one new `Store` method;
  - one `temporalclient.RequestCancel`.

  Clients that do not declare the extension see no change.
- **Risks and mitigations:**

  | Risk | Mitigation |
  | --- | --- |
  | Orphan `xr_` | Design A single commit; G1 fault injection |
  | Approval bypass through `tasks/update` | No code path to approval signals; spy test; separate gate states |
  | A model answering as the human | `respondent_policy` gates which requests are exposed; assurance is recorded as `client_relayed`; human-only requests stay `working` |
  | A live task hidden by its TTL | `ttlMs: null` until terminal |
  | Schema drift | A pinned vendor schema with sha256, and an independent validator |
  | Vocabulary drift | One map plus the consistency check |
  | Polling load | One describe/query per `tasks/get`, rate limited, measured in G2 |

- **Resource impact:** none in Phase 0.
