# Design: issue-287-mctl-trigger-issue-with-use-temporal-tru

## Current state

**The start path.** `internal/mcp/server.go:3006` defines `toolTriggerIssue`.
Its handler branches on `use_temporal`: when true it does
`s.apiPostJSON(ctx, "/api/v1/agents/dev-loop/start", {"issue_url": ...})` and
returns the raw response body as tool text; otherwise it POSTs to
`/api/v1/operations/mctl-agents-investigate/execute`. The tool has exactly two
inputs today, `issue_url` (required) and `use_temporal` (boolean).

`internal/api/router.go:451` mounts `POST /api/v1/agents/dev-loop/start` on
`h.StartDevLoopWorkflow` (`internal/api/handlers_dev_loop.go:69`). That handler:

1. gates on `requireTemporalAdmin` — 503 when `h.opts.TemporalClient` is nil,
   401 unauthenticated, 403 non-admin;
2. decodes `startDevLoopRequest{IssueURL}` and 400s on an empty `issue_url`;
3. calls `h.opts.TemporalClient.StartDevLoopWorkflow(ctx, body.IssueURL)`;
4. maps `temporalclient.ErrInvalidIssueURL` to 400 and every other error to 502
   plus a `failed` audit entry;
5. on success writes a `succeeded` audit entry and
   `202 {"workflow_id", "run_id", "message": "DevLoopWorkflow started. ..."}`.

**Why step 5 lies.** `temporalclient.Client.StartDevLoopWorkflow`
(`internal/temporalclient/client.go:157`) derives the id via
`WorkflowIDForIssueURL` — `dev-loop-mctlhq-{repo}-{issue}` — and calls
`ExecuteWorkflow` with `WorkflowIDReusePolicy: REJECT_DUPLICATE` and
`WorkflowIDConflictPolicy: USE_EXISTING`. Its own doc comment is explicit that
this "truly no-ops" on a matching id: a running prior run is not errored on and
a closed prior run is not restarted — both return that same run's ID/run ID.
So `run.GetRunID()` is the *existing* run's id, and the handler stamps
"DevLoopWorkflow started." on it regardless. That is precisely the `portfolio#7`
observation in the issue.

**Prior art, one route over.** `ExecuteRoadmapWave`
(`internal/api/handlers_roadmap_wave.go:256`) starts one DevLoop per planned
item and does not trust the idempotent start to be legible. Its per-item loop
(lines ~350-379) reads:

- `DescribeDevLoop(ctx, it.WorkflowID)`;
- a non-NotFound describe error -> `waveOutcomeFailed` with "could not read the
  DevLoop", and it does **not** start blind;
- `status == "Running"` -> `waveOutcomeAlreadyRunning`;
- any other successful describe (a closed execution) -> `waveOutcomeAlreadyExists`;
- NotFound -> the actual `StartDevLoopWorkflow`, then `waveOutcomeStarted`, or
  `waveOutcomeFailed` if the returned workflow id differs from the planned one.

The vocabulary is four constants at `handlers_roadmap_wave.go:71-76`:
`started`, `already_running`, `already_exists`, `failed`. Each Temporal call is
bounded by its own `roadmapWaveCallTimeout` (10s), well under the server's
`WriteTimeout`.

**The client surface.** `DevLoopClient` (`internal/api/interfaces.go:77`) is the
injectable subset: `StartDevLoopWorkflow`, `SignalApprove`, `DescribeDevLoop`,
`QueryShepherdInLoop`, `QueryHumanInputState`, `SignalHumanInputResponse`.
`DescribeDevLoop` returns only a status *string* — it discards
`WorkflowExecutionInfo.Execution.RunId`, which is exactly the field issue #287
asks to return for an already-running execution. `temporalclient.IsNotFound`
already exists for the NotFound discrimination. Tests inject
`fakeDevLoopClient` (`internal/api/handlers_dev_loop_test.go:38`).

**The observability gap the issue also names.** `GetDevLoopWorkflow`
(`handlers_dev_loop.go:234`) answers `status` + `shepherd_in_loop` +
`shepherd_in_loop_known` and nothing about which step a `Running` execution is
on. `GetWorkflow` (`internal/api/handlers_read.go:385`) finds the
`dev-loop-start` audit entry by workflow name, gets no team from
`auditEntryTenant`, and routes a Kubernetes lookup through
`operations.WorkflowNamespace` (`internal/operations/executor.go:89`) — a
namespace that never contained a Temporal execution. Both are out of scope here
and recorded as such.

## Proposed solution

### 1. Extract the describe-then-start decision into one shared function

Add to `internal/api/handlers_dev_loop.go`:

```go
// devLoopOutcome is the shared vocabulary; the wave constants alias these.
const (
    devLoopOutcomeStarted        = "started"
    devLoopOutcomeAlreadyRunning = "already_running"
    devLoopOutcomeAlreadyExists  = "already_exists"
    devLoopOutcomeFailed         = "failed"
)

type devLoopStartResult struct {
    Outcome string
    Status  string // Temporal status of the pre-existing execution
    RunID   string
    Err     error
}

// startDevLoop decides whether to start, then starts. One function so the
// single-issue route and the wave route cannot drift on what
// "already_running" means.
func startDevLoop(ctx context.Context, c DevLoopClient, issueURL, workflowID string) devLoopStartResult
```

`waveOutcome*` in `handlers_roadmap_wave.go` become aliases of the new
constants (`const waveOutcomeStarted = devLoopOutcomeStarted`, ...), so no wave
test or audit string changes value. `ExecuteRoadmapWave`'s per-item switch is
replaced by a `startDevLoop(...)` call inside its existing
`call()` timeout wrapper, keeping the "started workflow X, planned Y" guard.

### 2. Teach the client to return the existing run id

`DescribeDevLoop` keeps its exact signature — the shepherd sweeper and
`GetDevLoopWorkflow` depend on it. Add a sibling that returns more:

```go
type DevLoopExecution struct {
    Status    string
    RunID     string
    StartTime time.Time
}
func (c *Client) DescribeDevLoopExecution(ctx context.Context, workflowID string) (*DevLoopExecution, error)
```

The status mapping already in `DescribeDevLoop`'s switch moves into a small
`statusName(enumspb.WorkflowExecutionStatus) string` helper both call, and
`DescribeDevLoop` becomes a thin wrapper over `DescribeDevLoopExecution` —
identical behaviour, including the `"Unknown"` default arm that
`GetDevLoopWorkflow`'s `shepherd_in_loop_known` derivation reads. `RunID` comes
from `resp.GetWorkflowExecutionInfo().GetExecution().GetRunId()`.
`DescribeDevLoopExecution` is added to the `DevLoopClient` interface and to
`fakeDevLoopClient`.

### 3. Handler and response

`startDevLoopRequest` is unchanged (`issue_url` only).
`StartDevLoopWorkflow` keeps its auth gate, decode and `issue_url` validation
verbatim, then calls `startDevLoop` and maps:

| Outcome | Status | Body |
| --- | --- | --- |
| `started` | 202 | `started: true`, `run_id` (new) |
| `already_running` | 200 | `started: false`, `status: "Running"`, `run_id` (existing), message naming the execution |
| `already_exists` | 200 | `started: false`, `status` (closed state), `run_id` (existing) |
| `failed` (describe unreadable) | 502 | `error` |
| `ErrInvalidIssueURL` | 400 | unchanged |

`workflow_id`, `run_id` and `message` keep their key names and positions, so a
client that only reads those three still works; `message` is the field whose
*text* changes for the no-op cases, which is the whole point of the fix.

Auditing: one entry per request, as today, at the existing risk level.
Parameters gain `outcome`. A no-op stays `Status: "succeeded"` (the request
did succeed) but its `Message` reads `"not started: already_running (run <id>)"`
— so the audit log stops being evidence of runs that never happened.

### 4. MCP tool and spec

`toolTriggerIssue` keeps exactly its two inputs (`issue_url`, `use_temporal`)
and still returns the response body as tool text, so the new
`started`/`outcome` fields reach the caller verbatim. The tool description
gains a paragraph stating that the Temporal start is idempotent on
`dev-loop-mctlhq-{repo}-{issue}` and that `started: false` means nothing was
submitted — the existing execution's `run_id` and `status` are what to follow
up on with `mctl_get_dev_loop`. **No tool or input is added or removed**, so
the `server_test.go` tool-count expectation called out in `CLAUDE.md` is
untouched.

`internal/openapi/openapi.yaml` (`/api/v1/agents/dev-loop/start`, line 2258)
gains a `200` response for the not-started outcomes and
`started`/`outcome`/`status` on the `202` schema; the request schema is
unchanged.

## Alternatives

**A. Leave the client alone; have the handler call `DescribeDevLoop` twice — once
before and once after the start — and infer "started" from a run-id change.**
Rejected: two describes plus a start triples the Temporal round-trips on the hot
path, and the inference is still a guess. A run id that did not change could also
mean the start raced another caller.

**B. Drop `USE_EXISTING` and let Temporal return `WorkflowExecutionAlreadyStarted`,
mapping that error to 409.** This is the smallest diff and gives an unambiguous
answer straight from the frontend. Rejected because `ExecuteRoadmapWave` depends
on the start being a genuine no-op per item (it starts many items in one request
and must not have one conflict abort the wave), and because the
`StartDevLoopWorkflow` doc comment pins those policies as deliberately mirrored
against `orchestrator/temporal/cli.py`. Changing them is a cross-repo behaviour
change to fix a reporting bug. The describe-then-start pre-check gets the same
information without touching the contract.

**C. Ship an explicit restart (`restart: true` flag or a dedicated
`/dev-loop/{workflow_id}/restart` route) in the same change.** Deferred, not
rejected: restart terminates a live execution — possibly one parked on the
human-input gate with a sealed request — and needs its own decisions (refuse on
`WAITING_FOR_INPUT`? `ALLOW_DUPLICATE` + `TERMINATE_EXISTING` vs a two-RPC
terminate-then-start, which `REJECT_DUPLICATE` would refuse; audit risk level).
Bundling it would couple a destructive capability to a reporting fix. It is a
separate follow-up issue, mctl-api#404.

## Platform impact

- **Migrations:** none. No database, no gitops schema, no Helm value.
- **Backward compatibility:** `workflow_id`, `run_id` and `message` remain on
  every success response; `started`, `outcome` and `status` are additive. The one observable change for an existing
  client is the status code on an already-existing execution: `202` becomes
  `200`. Both are 2xx, and the only in-repo consumer of this route is
  `toolTriggerIssue`, which renders the body and does not branch on the code.
  `DescribeDevLoop`'s signature, semantics and `"Unknown"` default arm are
  unchanged, so the shepherd sweeper (mctl-agents#213) and
  `GetDevLoopWorkflow`'s `shepherd_in_loop_known` derivation are untouched.
  `ExecuteRoadmapWave`'s per-item outcome strings keep their exact values
  through the const aliases, so `handlers_roadmap_wave_test.go` and the audit
  `outcomes` parameter are unaffected.
- **Resource impact:** one extra `DescribeWorkflowExecution` RPC per single
  start — a read against the Temporal frontend, negligible next to the ~$3
  investigate run it guards. The wave path gains no RPCs; it already described
  every item.
- **Risk: the pre-check makes starts refusable.** If Describe fails
  non-NotFound, the handler now returns 502 instead of attempting a start. That
  is deliberate (matching `ExecuteRoadmapWave`'s "do not start blind") and the
  failure mode is benign: a Temporal frontend that cannot answer a describe is
  overwhelmingly unlikely to accept a start. Mitigation: the describe gets its
  own short deadline (reuse the 10s bound `roadmapWaveCallTimeout` already
  establishes, as a named `devLoopDescribeTimeout`) so a hung frontend fails
  fast rather than consuming the request's 30s budget; the 502 body says "could
  not read the existing DevLoop" so an operator can tell it apart from a start
  failure.
- **Risk: TOCTOU between describe and start.** Two operators racing can both
  see NotFound; the second start is then absorbed by `USE_EXISTING` and reported
  as `started` when it was not. This is strictly narrower than today's window
  (which reports every no-op as a start) and is not closable without the
  `AlreadyStarted` error of alternative B. Mitigation: the
  `wf != workflowID` guard already in the wave path is kept in the shared
  function, and the race is documented in the handler comment.
