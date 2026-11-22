# Design: issue-41-spike-mcp-tasks-over-durable-temporal-ar

## Current state

Evidence pins (read 2026-11-22):

| Repository | Pin | Read |
| --- | --- | --- |
| mctlhq/.github | `7a0659c` (HEAD of clone) | manifests, spike conventions |
| mctlhq/mctl-api | `5062295fbd4b1d2c5949d4bd21985b16b8fb5f6c` | `go.mod`, `internal/mcp/server.go`, `internal/temporalclient/client.go`, `internal/api/handlers_approval_grant.go`, `internal/workitems/execution_requests.go` `[CODE]` |
| mctlhq/mctl-agents | `05c1dc83b6c025aa5128e6d9234023eb513f95a0` | `orchestrator/temporal/workflows/action_approval.py`, `docs/adr/013-human-input-contract.md`, tree listing `[CODE]` |
| mark3labs/mcp-go | tags `v1.0.0`, `v1.6.0` | `mcp/tasks.go`, `mcp/types.go`, `server/server.go` `[CODE]` |
| Spec | https://tasks.extensions.modelcontextprotocol.io/specification/2026-07-28/tasks | method set, fields, errors, security `[DOC]` |

In this repository (`.github`):

- `roadmap/spikes/mcp-tasks-durable-execution.yaml`: `lifecycle: proposed`,
  owner `mctlhq/mctl-agents`, outcomes
  `GO_ADAPTER_IN_MCTL_API | GO_UPSTREAM_ONLY | NO_GO`, decision due
  `2026-12-15`. Its header comment says the trigger fired (Claude Code ships
  the extension in public beta from v2.1.304 `[DOC]`), the Portal half is
  dropped (the mcp-gateway plan passes Tasks through and checks that at
  G2), and the executable pilot is mctl-api#284.
- `roadmap/epics/enterprise-mcp.yaml`: work item `mcp-tasks` (phase
  `extensions`, required) is mctl-api#284. It depends on
  `correlation-contract` and `compatibility-spike`. Success criterion: "MCP
  Tasks and Apps are accepted only after end-to-end Portal compatibility is
  measured."
- `docs/plans/mcp-gateway.md` (lines 122, 267): Tasks, Apps and elicitation
  pass through the Portal untouched once measured.
- `docs/spikes/automation-control-plane.md` (D1 table and Boundaries): "A
  Task is one execution; an automation is a standing intent". The MCP Tasks
  row reads "one execution = one task". The chain is `au_ -> wi_ -> xr_ ->
  we_`. Its fixture layout (`model/`, `fixtures/`, `schemas/`,
  `temporal-integration/` with a real Temporal dev server through the
  official SDK, `[MODEL]` vs `[TEMPORAL_DEV]` tags) is the pattern reused
  here.
- `docs/spikes/journey-intent-correlation.md`: proposed `REUSE_WORK_ITEM_ID`.
  `wi_` is the journey key, and a modern DevLoop attaches `(temporal,
  workflow_id#run_id)` as its `we_` through `ensure_issue_execution`.
- `docs/spikes/agent-client-compatibility.md`: host compatibility is a draft
  with "pending live run" and `unknown` cells. No host has been run against
  `api.mctl.ai/mcp`.

In mctl-api (`[CODE]` at the pin):

- `go.mod`: `github.com/mark3labs/mcp-go v1.0.0`, `go.temporal.io/sdk v1.50.0`.
- `internal/mcp/server.go`: `server.WithStateLess(true)` (no `Mcp-Session-Id`),
  tool and prompt capabilities on, and `WithResourceCapabilities(false,
  false)` with the comment that a stateless transport has no session to
  deliver notifications to. No `WithTaskCapabilities` and no task tools are
  registered. The server advertises no Tasks support today.
- `internal/temporalclient/client.go`: `StartDevLoopWorkflow`,
  `DescribeDevLoopExecution`/`DescribeDevLoopRun`, `SignalApprove`,
  `SignalAbandon`, `SignalBridgeResult`, `QueryShepherdInLoop`,
  `QueryHumanInputState` (`RUNNING | WAITING_FOR_INPUT | INPUT_TIMED_OUT`,
  with `request_id`/`request_hash`, "the ONLY source of truth ... mctl-api
  keeps no copy"), and the human-input response signal. There is **no
  generic workflow-cancel method**.
- `internal/api/handlers_approval_grant.go`: `prepareApprovalGrant`,
  `bindApprovalGrant` and `spendApprovalGrant` form one atomic
  compare-and-set: approved, same intent, not expired, not consumed. The
  approval is bound to `artifact_hash`. Since the owner decision of
  2026-11-18, decisions are made only on the decide page.
- `internal/workitems/execution_requests.go`: `xr_` requests with
  `expected_state_version`, `idempotency_key`, `surface`, `requested_by`,
  `acting_principal`, and `OpenRequestError` (one open request per item).
- `internal/mcp/testdata/support/task_*.json`: A2A task-state fixtures for
  `mctl_get_support_task`. This is a precedent for mapping another
  protocol's task states onto a canonical store without copying it.

In mctl-agents (`[CODE]`):

- `orchestrator/temporal/workflows/action_approval.py`: `ApprovalWaitWorkflow`.
  It waits on a wake-up signal `{"approval_id": "aar_..."}` bounded by a
  durable timer, polls every 15 minutes (ADR-014 section 7), and ends with
  outcomes `ran | denied | expired | consumed | mismatch`.
- `docs/adr/013-human-input-contract.md`: a sealed, content-addressed request
  (`request_hash`, `request_id = "hir-" + ...`, `question_hash`), bounded TTL
  (`MAX_REQUEST_TTL_SECONDS`) and bounded rounds. The workflow validates the
  response (id, hash, expiry, respondent, typed value).
- `orchestrator/temporal/dispatcher.py` claims `xr_` and starts the run via
  Update-with-Start (as recorded in automation-control-plane D1).

In mcp-go (`[CODE]`):

- v1.0.0 and v1.6.0 implement the **legacy SEP-1686** shape:
  `MethodTasksList` ("tasks/list ... for the current session"),
  `MethodTasksResult`, `notifications/tasks/status`, and no `tasks/update`.
  The server task store is `tasks map[string]*taskEntry` in process memory.
  `executeTaskTool` runs the handler in a goroutine with a cancel func, and
  `scheduleTaskCleanup` is a timer. Enabling it would create a second,
  non-durable executor that loses tasks on restart. This contradicts the
  issue and the modern spec.

Modern spec (`[DOC]`, 2026-07-28):

- Negotiation is per request, through
  `params._meta["io.modelcontextprotocol/clientCapabilities"].extensions["io.modelcontextprotocol/tasks"]`.
  The server advertises it in `server/discover`.
- The result is `CreateTaskResult` with `resultType: "task"` (`taskId`,
  `status`, `statusMessage`, `createdAt`, `lastUpdatedAt`, `ttlMs`,
  `pollIntervalMs`), returned only after durable creation.
- Statuses: `working | input_required | completed | cancelled | failed`.
- `tasks/get` returns `result` inline when `completed`, `error` when `failed`,
  and `inputRequests` when `input_required`.
- `tasks/update {taskId, inputResponses}` and `tasks/cancel {taskId}` both
  return an empty, eventually consistent acknowledgement. Cancel is
  cooperative.
- A tool result with `isError: true` is still `completed`.
- There is no `tasks/list` or `tasks/result`. Notifications go through
  `subscriptions/listen` with `notifications/tasks`.
- Errors: `-32602` for an unknown `taskId`, `-32603` internal, `-32021`
  missing client capability.
- `taskId` must have high entropy and every request must be authorized.
- `Mcp-Name: <taskId>` is required on Streamable HTTP `tasks/*` requests.

Deployed state checked:

- `mctl_list_services(team=admins)` `[LIVE]`: `mctl-agents-worker`,
  `-worker-exec` and `-worker-implement` at `1.117.0`, all Synced. mctl-api
  is **not** in the `admins` catalogue, so its deployed image, flags and
  whether a Tasks capability is live are `unknown (not observed)`.
- `services/admins/mctl-agents-worker/values.yaml` `[CONFIG]`: `replicaCount:
  1`, `image.tag "1.117.0"`, `TEMPORAL_NAMESPACE: mctl-agents`,
  `TEMPORAL_ADDRESS: temporal-frontend.temporal.svc.cluster.local:7233`,
  `EXECUTION_REQUEST_DISPATCHER: "true"`.
- `services/admins/mctl-agents-worker-exec/values.yaml` `[CONFIG]`: same
  namespace and tag, `replicaCount: 1`.
- `gh issue view` `[LIVE]`: mctl-api#284 OPEN; .github#375 (authority
  lifecycle, revocation and fencing), #376 (MCP Apps) and #377 (SEP-3415
  events) are OPEN.
- Not observed: live `api.mctl.ai/mcp` behaviour for `server/discover` and
  `tasks/*`, Portal pass-through, and every AI host. All are `unknown`.

## Proposed solution

The spike's output is documentation plus a reference fixture in this
repository. No production change. The design below is the contract that the
fixture proves and that mctl-api#284 later implements.

### ADR-41: thin Tasks adapter in mctl-api over canonical execution

**Decision (proposed):** `GO_ADAPTER_IN_MCTL_API`, scoped as a bounded pilot
(`BOUNDED_PILOT` in the issue's vocabulary). Do not wait for upstream
(`GO_UPSTREAM_ONLY`), because no upstream SDK piece is required: the
adapter writes its own method handlers. `NO_GO` only if a decision gate
below fails.

1. **Layering and ownership.**

   ```text
   MCP host --(tools/call, tasks/*)--> mctl-api internal/mcp  [protocol adapter, mctl-api]
                                          | tk_ row: protocol state only
                                          v
                         WorkItem store: wi_ / xr_ / we_ / cs_  [canonical identity, mctl-api]
                                          v
                   dispatcher.py claims xr_ -> Temporal workflow  [execution owner, mctl-agents]
                                          v
                              Argo / CI / deploy / agent worker
   ```

   mctl-agents owns execution semantics: states, gates and cancellation
   boundaries. mctl-api owns the protocol adapter and the thin protocol
   table. Service-specific MCP servers (for example mctl-telegram) may
   reuse the same contract later. They never get a store of their own.

2. **Protocol state vs execution state.** A new mctl-api table `mcp_tasks`
   holds **only** protocol state:
   - `task_id`, `tenant`, `owner_principal`, `client_id`;
   - `tool`, `args_digest`, `idempotency_key`;
   - `work_item_id`, `execution_request_id`, and `execution_id` (filled
     lazily from `xr_.execution_id`);
   - `ttl_ms`, `poll_interval_ms`, `created_at`, `expires_at`;
   - `cancel_requested_at`, `answered_input_keys`.

   It has **no status column**. Every `tasks/get` derives status (see 3).
   `lastUpdatedAt` is the maximum of the canonical timestamps read.

3. **Deterministic lifecycle mapping** (first matching row wins):

   | Canonical state | MCP |
   | --- | --- |
   | `xr_` rejected | `failed` (`error.data.reason = execution_request_rejected`) |
   | `xr_` pending or claimed, no `we_` yet | `working` |
   | Temporal `Completed`, result is a tool success | `completed` + `result` |
   | Temporal `Completed`, result carries a business refusal or failure | `completed` + `result.isError: true` |
   | Temporal `Canceled` | `cancelled` |
   | Temporal `Failed`, `TimedOut` or `Terminated` | `failed` + classified `error` |
   | Running, `human_input_state = WAITING_FOR_INPUT` | `input_required` + `inputRequests[request_id]` |
   | Running, `human_input_state = INPUT_TIMED_OUT` | `working` until the workflow ends (the workflow decides) |
   | Running, waiting on `ApprovalWaitWorkflow` with an `aar_` pending | `input_required` + `statusMessage` naming the decide page; **no** answerable `inputRequests` |
   | Running, otherwise | `working` (+ `statusMessage` "cancellation requested" if `cancel_requested_at`) |
   | Any read of Temporal or the store fails | JSON-RPC `-32603`, retryable; never a status |

   `input_required` maps to **both** layers: the persisted, sealed object
   (the ADR 013 `hir-` request, or an `aar_` grant) is the content binding,
   and the Temporal signal is only the transport.

4. **Task identity.** `taskId = "tk_" + base32(128-bit CSPRNG)`. It is not
   the Temporal workflow ID, which is guessable, for example
   `dev-loop-mctlhq-<repo>-<issue>` from `WorkflowIDForIssueURL`.
   Possession is never authorization: every `tasks/*` call re-runs the same
   principal and tenant authorization as the tool (`PrincipalAuthz`, as in
   mcp-gateway-g0), then compares `owner_principal` and `tenant`. A
   mismatch, unknown, malformed or expired ID all return the same `-32602`.
   The handler requires `Mcp-Name` to equal `params.taskId`. There is no
   enumeration method.

5. **Durable create before return.** Inside one Postgres transaction, the
   `tools/call` handler:
   1. creates or joins the `wi_`;
   2. creates the `xr_` (surface `mcp`, `acting_principal`, the idempotency
      key);
   3. inserts the `mcp_tasks` row;
   4. commits;
   5. returns `CreateTaskResult{status: working}`.

   The dispatcher starts Temporal asynchronously, as it does today. So the
   adapter never calls Temporal start itself and creates no second start
   path.

6. **Idempotency.** MCP has no stable request key: JSON-RPC `id` is
   per-connection, and there is no session under the stateless transport.
   Every task-capable tool therefore takes an explicit `idempotency_key`
   argument. It is a tool argument and not only `_meta`, because hosts let
   the model fill arguments, and it is mctl's existing convention (see
   `mctl_create_work_item`). The scope is `(tenant, owner_principal, tool,
   idempotency_key)`, with a unique index:
   - same `args_digest`: the same `taskId` is returned (replayed);
   - different digest: `idempotency_key_reused`;
   - key missing on a consequential tool: refused;
   - after TTL expiry, the key is retained for at least the `xr_`
     idempotency window, so a late retry cannot start a duplicate.

7. **Input handoff.** `tasks/update` checks the owner, then for each
   `inputResponses` key:
   - if the key equals the open `request_id`: send the existing human-input
     response signal with `request_id`, `request_hash`, the respondent
     principal and the typed value. The workflow validates it, as it does
     today;
   - otherwise: ignore it, record the key in the audit trail, and record
     the key in `answered_input_keys`.

   It acknowledges with an empty result. Truth arrives through the next
   `tasks/get`.

8. **Approval handoff.** `tasks/update` cannot answer an approval. The task
   shows `input_required` and a statusMessage with the `decide_url` that
   `mctl_get_dev_loop_approval`/`mctl_request_deploy_approval` already
   return. The owner decides on the fresh-sign-in page. mctl-api signals
   `ApprovalWaitWorkflow` as today, and the task returns to `working`. MCP
   Apps (#376) may *display* the same status, but they are never a decision
   surface.

9. **Cancellation.** `tasks/cancel` checks the owner, records
   `cancel_requested_at` and the audit entry, then calls a new
   `temporalclient.RequestCancel(workflowID, runID)`. If no `we_` exists
   yet, it marks the `xr_` cancelled. It acknowledges with an empty result.
   Each workflow class declares its boundary:
   - waiting for input or approval: cancels at once (wait_condition
     cancelled);
   - Temporal activity: heartbeat cancellation, then cleanup;
   - submitted Argo work: the cancel handler stops or terminates the Argo
     workflow and waits for its terminal phase before the workflow returns
     `Canceled`;
   - external CI or deploy past the point of no return: the cancel is
     honoured after the current non-rollbackable step. The result records
     which side effects happened, and if the step finished first the task
     ends `completed`.

   Races: Temporal's first terminal state wins. A cancel after a terminal
   state is a no-op acknowledgement. A cancel is never reported as
   `cancelled` early.

10. **TTL and retention.** The default `ttlMs` is 24 hours, capped at 7 days,
    and never longer than the workflow's own bound. After expiry, `tasks/*`
    returns `-32602` and a sweeper deletes the protocol row. `wi_`, `we_`,
    the audit trail and Temporal history keep their own retention, so a
    result stays reachable through the existing WorkItem tools.

11. **Revocation and fencing (#375).** Authority is re-checked on every
    `tasks/*` call. The workflow's action-time checkpoint denies side
    effects for a revoked principal. Lifecycle-ownership fencing epochs stay
    authoritative over who drives the execution. The task adapter never
    acquires ownership.

12. **Notifications vs #377.** The pilot is polling only. `pollIntervalMs` is
    5 s while working and 30 s while `input_required`. The server advertises
    no `subscriptions/listen` for tasks. If #377 chooses a business-event
    stream, `notifications/tasks` becomes a projection of the same
    canonical transition. That projection is keyed on `(taskId,
    lastUpdatedAt)` so a client that both polls and subscribes is not sent
    the same change twice.

13. **Fallback for non-negotiating hosts.** The same tool returns a normal
    `CallToolResult` with `work_item_id` and `execution_request_id`. The
    host then polls through existing `mctl_get_work_item` and
    `mctl_list_work_item_executions`. Nothing long-running holds the HTTP
    request.

14. **Audit.** Each event records principal, tenant, client, `taskId`,
    `wi_`, `xr_`, `we_`, method and outcome. Content is never logged.

### Pilot choice

| Candidate | Durable today | Side effects | Verdict |
| --- | --- | --- | --- |
| DevLoop investigation | yes | gitops commits, model spend | rejected as first pilot (spend and writes) |
| Deploy + wait-for-Argo-health | yes | production deploy | rejected (production side effects) |
| Telegram research | unknown worker boundary | messages | rejected (boundary not ready) |
| **Synthetic `TaskProbeWorkflow`** | built in the fixture with the SDK | none | **chosen** |

`TaskProbeWorkflow` has three phases: a cancellable sleep, a
`WAITING_FOR_INPUT` gate that reuses the ADR 013 request shape, and an
approval-wait gate that reuses the `ApprovalWaitWorkflow` signal shape
against a fake grant store. It then returns a deterministic result, or a
business error on input `fail`. It first lives only in
`docs/spikes/mcp-tasks-durable-execution/temporal-integration/`. Moving it
into mctl-agents and exposing it through mctl-api#284 are later,
owner-gated steps.

### Host and SDK compatibility matrix (initial)

| Client | Extension declared | Evidence |
| --- | --- | --- |
| Claude Code | public beta from v2.1.304 | `[DOC]` (manifest comment), unmeasured |
| Claude (web/desktop), ChatGPT, Codex, Antigravity, agy, Grok Bot | unknown | not observed |
| mcp-go server v1.0.0/v1.6.0 | legacy SEP-1686 only | `[CODE]`; the adapter must not use `WithTaskCapabilities` or `AddTaskTool` |

### Decision gates

- G0: the fixture passes the full test matrix `[MODEL]` and `[TEMPORAL_DEV]`.
- G1: mctl-api can register modern `tasks/*` handlers and `server/discover`
  extension advertisement without the legacy store (code spike in #284).
- G2: direct `api.mctl.ai/mcp` measurement from one real host (Claude Code).
- G3: Portal pass-through of `tasks/*` and `Mcp-Name` (mcp-gateway G2).

Each gate is a separate owner approval. A failed G1 means `NO_GO` for now,
or `GO_UPSTREAM_ONLY` if the gap is an SDK hook. A failed G3 keeps Tasks
upstream-only, as #284 already states.

## Alternatives

- **Enable mcp-go's built-in task support** (`WithTaskCapabilities`,
  `AddTaskTool`). Dropped: in-memory, process-local, and runs the handler in
  a goroutine, which makes it a second executor that loses tasks on
  restart. It also implements the legacy method set (`tasks/list`,
  `tasks/result`, no `tasks/update`).
- **`taskId` = Temporal workflow ID (or `we_`).** Dropped: DevLoop IDs are
  derivable from issue URLs. `we_` does not exist at return time, because
  the dispatcher creates it asynchronously, so durable create-before-return
  would require a synchronous Temporal start in the adapter (a second start
  path). TTL and idempotency would also have no home.
- **`taskId` = `xr_` with no extra table.** Viable if `xr_` IDs prove to have
  at least 128 bits of entropy. The open question decides this. It still
  needs somewhere for TTL and answered-key state, and it overloads the
  execution-request contract with protocol fields. Kept as a fallback.
- **A full task store with its own status machine.** Dropped: it duplicates
  canonical state and drifts.

## Platform impact

- **This proposal:** docs and a reference fixture in `.github` only. No
  migration, no deployment, no spend. The fixture runs locally against a
  Temporal dev server (opt-in, as automation-control-plane does).
- **Later (mctl-api#284, gated):** one additive table `mcp_tasks` with a
  unique `(tenant, owner_principal, tool, idempotency_key)` index, one new
  `temporalclient` cancel method, modern `tasks/*` handlers, and one pilot
  tool. Backward compatibility: clients that do not declare the extension
  see no change.
- **Risks and mitigations:**
  - mcp-go's legacy store is enabled by accident: a test asserts
    `tasks/list`/`tasks/result` return method-not-found.
  - Status drift: no status column, so status is derived per read.
  - Enumeration: 128-bit IDs, a uniform `-32602`, no list method.
  - Duplicate executions: a mandatory key, and `xr_`'s one-open-request
    rule.
  - Approval bypass: `tasks/update` is never an approval path; tested.
  - Early cancelled: cancelled is reported only on Temporal `Canceled`.
  - Polling load: `pollIntervalMs` plus rate limits, and every `tasks/get`
    costs one Temporal describe/query. Accepted for one pilot tool; measured
    in G2.
- **Resource impact:** none now. Later: one describe/query per poll.
