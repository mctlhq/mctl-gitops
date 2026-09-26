# Design: issue-401-feat-agents-make-the-temporal-devloop-th

## Current state

**The MCP tool.** `internal/mcp/server.go:3006-3060` defines
`mctl_trigger_issue`. Its only branch is:

```go
if useTemporal, ok := req.GetArguments()["use_temporal"].(bool); ok && useTemporal {
    body, err := s.apiPostJSON(ctx, "/api/v1/agents/dev-loop/start", ...)
    ...
}
params := extractStringParams(req.GetArguments())
body, err := s.apiPost(ctx, "/api/v1/operations/mctl-agents-investigate/execute", params)
```

So the legacy direct-Argo path is reached by omission, and the tool description
(same file, the `WithDescription` block ending at line 3030) still says
"Defaults to false (the direct-Argo path this tool has always used) until that
slice is proven in production". `extractStringParams`
(`internal/mcp/server.go:2632-2640`) copies **every** string argument into the
operations-execute params, so a new `mode` argument would be forwarded to Argo
unless removed explicitly (the registry's undeclared-param stripping would hide
it, not prevent it).

**The Temporal start route.** `internal/api/handlers_dev_loop.go:69-122`
(`POST /api/v1/agents/dev-loop/start`, registered in
`internal/api/router.go:451` inside the 20/min write-rate-limit group) does:
admin+configured check (`requireTemporalAdmin`, lines 42-57), decode
`{issue_url}`, call `h.opts.TemporalClient.StartDevLoopWorkflow`, audit
`dev-loop-start`, then unconditionally answer

```go
writeJSON(w, http.StatusAccepted, map[string]interface{}{
    "workflow_id": workflowID, "run_id": runID,
    "message": "DevLoopWorkflow started. ..."})
```

**Why that message can be false (mctl-api#287).**
`internal/temporalclient/client.go:157-172` starts with
`WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE` and
`WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING`. Those policies are deliberate — a
closed run is not restarted and a running one is not errored on — but both
cases return the *existing* run's ids through the same `(workflowID, runID, nil)`
signature, so the handler cannot distinguish "started" from "attached". The
workflow id is deterministic: `WorkflowIDForIssueURL`
(`client.go:111-118`) produces `dev-loop-mctlhq-{repo}-{issue}`.

**The vocabulary already exists.** The governed epic-wave executor solved the
same problem per item: `internal/api/handlers_roadmap_wave.go:70-75` defines
`started` / `already_running` / `already_exists` / `failed`, and lines 349-379
implement Describe-then-Start with a fail-closed arm ("Cannot tell whether it
exists: do not start blind") and an explicit "A closed DevLoop is not restarted
(REJECT_DUPLICATE); report it." The single-issue start is the one entry point
that never got this treatment. `internal/mcp/roadmap_wave.go:78` already
advertises that vocabulary to operators.

**Related surfaces that describe the mechanisms.** `mctl_trigger_approve`
(`server.go:2960-3004`), `mctl_approve_dev_loop` (`server.go:3060-3098`) and
`mctl_get_dev_loop` (`server.go:3100-3140`) all describe the Temporal path in
terms of `use_temporal` ("started via use_temporal", "predates use_temporal").
The operations registry entry `mctl-agents-investigate`
(`internal/operations/registry.go:685-717`) describes the proposal as awaiting
"the dev-loop approve signal, or the mctl-agents-approve operation" with no
statement of which is canonical. `internal/openapi/openapi.yaml:2258-2300`
documents the start route with a single 202 "Workflow started" response.
`internal/api/interfaces.go:77-85` declares the `DevLoopClient` interface the
handlers consume and tests fake
(`internal/api/handlers_dev_loop_test.go:60-125`).

## Proposed solution

Four layers change, smallest blast radius first.

### 1. `internal/temporalclient` — a start that reports what happened

Add an outcome-bearing start and keep Temporal semantics where they belong:

```go
// Outcome vocabulary, identical in value to handlers_roadmap_wave.go's.
const (
    OutcomeStarted        = "started"
    OutcomeAlreadyRunning = "already_running"
    OutcomeAlreadyExists  = "already_exists"
)

type StartResult struct {
    WorkflowID string
    RunID      string
    Outcome    string // one of the three above
    Status     string // Temporal short status when attached, "" when started
}

func (c *Client) StartDevLoop(ctx context.Context, issueURL string) (StartResult, error)
```

Implementation: derive the id with `WorkflowIDForIssueURL` (unchanged 400
semantics through `ErrInvalidIssueURL`), then `ExecuteWorkflow` with
`WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE` and
`WORKFLOW_ID_CONFLICT_POLICY_FAIL`. On success the execution provably did not
exist: `OutcomeStarted` with the new run id. On
`*serviceerror.WorkflowExecutionAlreadyStarted` (new `IsAlreadyStarted` helper
next to the existing `IsNotFound`, `client.go:310-313`) call `DescribeDevLoop`
to classify: `Running` → `OutcomeAlreadyRunning`, any other status →
`OutcomeAlreadyExists`; a failed Describe returns an error, because "exists,
status unknown" must not be reported as either. Any other start error is
returned as today.

Switching the conflict policy from `USE_EXISTING` to `FAIL` is what makes the
answer *provable* rather than inferred, and it preserves the guarantee that
matters: no duplicate execution is ever created, and no closed run is
restarted. The reuse policy is untouched. The Go doc comment on the old method
that asks changes to be mirrored in `orchestrator/temporal/cli.py` stays, with
the new policy named.

`StartDevLoopWorkflow` is kept as a thin wrapper over `StartDevLoop` (returning
`WorkflowID, RunID`) so nothing outside this package breaks in the same commit.

### 2. `internal/api/handlers_dev_loop.go` — never report a start that did not happen

`StartDevLoopWorkflow` (the handler) gains `StartDevLoop` on `DevLoopClient`
(`internal/api/interfaces.go:77`) and switches on the outcome:

| outcome | HTTP | body |
|---|---|---|
| `started` | 202 | `mode:"devloop"`, `outcome:"started"`, `workflow_id`, `run_id`, message pointing at the approve route |
| `already_running` | 200 | `outcome:"already_running"`, `status:"Running"`, `workflow_id`, `run_id` when known, message "attached to the existing execution; nothing was started" |
| `already_exists` | 200 | `outcome:"already_exists"`, `status:"Completed"`… , message "a closed DevLoop for this issue is not restarted" |

`ErrInvalidIssueURL` stays 400 with no audit entry; a Temporal RPC failure stays
502 with a `failed` audit entry and an empty `WorkflowName`; the
already-exists-but-unreadable case is 502 with a message that states nothing was
started. Audit parameters gain `mode` and `outcome` so the ledger can tell an
attach from a start; `Status` stays `succeeded` for all three non-error outcomes
(the request did what was asked).

The wave executor (`handlers_roadmap_wave.go:349-379`) migrates to the same
call: its Describe-then-Start pair collapses into one `StartDevLoop`, which also
closes the same read-then-write race there. Its four outcome constants are
redefined in terms of the `temporalclient` ones so the strings on the wire are
byte-identical and `handlers_roadmap_wave_test.go` keeps passing.

### 3. `internal/mcp/server.go` — an explicit mode, defaulting to devloop

`mctl_trigger_issue` gains:

```go
mcplib.WithString("mode",
    mcplib.Description(`Which mechanism to run. "devloop" (default) ... "legacy-direct" ...`),
    mcplib.Enum("devloop", "legacy-direct"),
),
```

and `use_temporal` stays, redescribed as deprecated. Resolution, in the handler:

1. read `mode` (string) and `use_temporal` (bool, presence-checked as today);
2. if both present and they disagree (`devloop` vs `false`, `legacy-direct` vs
   `true`) → tool error naming both values, nothing started;
3. if `mode` empty, derive it: `use_temporal=true` → `devloop`,
   `use_temporal=false` → `legacy-direct` (plus a deprecation line in the
   result), absent → `devloop`;
4. unknown `mode` value → tool error (the enum is advisory; the handler
   enforces);
5. `devloop` → `apiPostJSON("/api/v1/agents/dev-loop/start", {issue_url})`;
   `legacy-direct` → `extractStringParams` **minus `mode`** →
   `apiPost("/api/v1/operations/mctl-agents-investigate/execute", params)`.

Both branches annotate the reply so the operator sees the path without
inferring it: decode the backend JSON into a `map[string]any`, set `mode`, and
re-encode; if the body is not a JSON object, prepend a `mode: <m>` line to the
text instead. The devloop branch's `mode` is already set by the handler in
layer 2 — the annotation is what covers the legacy branch, whose backend
response is the generic operations-execute envelope.

A 503 on the devloop branch is surfaced as a tool error whose text names
`mode="legacy-direct"` as the explicit fallback. There is no automatic
fallback: an automatic one would recreate exactly the invisible-path failure
this issue is about.

### 4. Descriptions and docs (acceptance criterion 3)

- `mctl_trigger_issue`: the Temporal DevLoop is the canonical lifecycle and the
  default; `legacy-direct` is the fallback that produces no durable execution
  and needs `mctl_trigger_approve` + `mctl_trigger_implementer`; the response
  states `mode` and either `workflow_id`+`outcome` or `workflow_name`.
- `mctl_trigger_approve` (`server.go:2973`): the `.status.yaml` flip is the
  legacy approval path, for proposals with no live DevLoopWorkflow; check with
  `mctl_get_dev_loop` first; prefer `mctl_approve_dev_loop`.
- `mctl_approve_dev_loop` (`server.go:3068`): the canonical approval, for any
  issue triggered on the default path; drop "started via use_temporal".
- `mctl_get_dev_loop` (`server.go:3110`): a 404 now means the issue was
  triggered on the legacy path (or the run aged out), not that it "predates
  use_temporal".
- `internal/operations/registry.go:695-697`
  (`mctl-agents-investigate.Description`): mark it as the legacy direct-Argo
  entry point that the Temporal DevLoop's investigate activity also submits.
- `internal/openapi/openapi.yaml:2258-2300`: document `mode`, `outcome`,
  `status`, and the 200 attach responses next to the 202.
- `internal/mcp/server_test.go`'s tool-count/hint expectation
  (`server_test.go:34,65-67`) is unaffected — no tool is added or removed — but
  the new argument must be reflected wherever the schema is asserted.

## Alternatives

1. **The issue's "Minimum": just default `use_temporal` to `true`.** One-line
   change, and it does stop the silent legacy path. Dropped as the primary
   shape because a boolean cannot carry "which path ran" into the response, an
   explicit `use_temporal=false` reads like a feature flag rather than "give me
   the legacy mechanism", and the name keeps the Temporal path sounding
   optional. The boolean is nevertheless retained as a deprecated alias, so this
   alternative is a strict subset of what ships.
2. **The issue's "Preferred": a required `mode` with no default.** Rejected
   because it contradicts the issue's own first acceptance criterion (a call
   *without* an explicit mode must start a DevLoop) and would break every
   existing caller and MCP schema consumer at once. Optional-with-default
   achieves the stated goal — the legacy path is unreachable by omission —
   without that breakage. Recorded as an open question.
3. **Detect the collision from the raw `StartWorkflowExecutionResponse.Started`
   flag** via `client.Client.WorkflowService()` instead of the
   `AlreadyStarted`+Describe pair. Race-free in one round trip and it keeps
   `USE_EXISTING`, but it bypasses the SDK's data converter and interceptors,
   hand-rolls the payload encoding the Python worker must decode, and depends on
   a server version that populates the field. Dropped in favour of staying on
   `go.temporal.io/sdk` API that is already used here; worth revisiting if the
   extra Describe ever shows up as latency.
4. **Describe-then-Start in the handler, copying the wave loop verbatim.**
   Simplest diff and no client change, but it keeps the read-then-write race
   (two concurrent triggers both see NotFound, both call Start, the second
   attaches via `USE_EXISTING` and still reports "started") — the exact bug
   #287 describes, just narrowed. Rejected; instead the wave loop is migrated
   onto the race-free call.
5. **Fall back to the legacy path automatically when Temporal is unconfigured.**
   Rejected: a fallback nobody asked for is how eight issues ended up with no
   execution in the first place. 503 plus an explicit escape hatch keeps the
   choice visible.

## Platform impact

**Behaviour change (intended).** Any caller of `mctl_trigger_issue` that omits
`use_temporal` moves from an Argo investigate run to a durable DevLoopWorkflow.
Cost per call is unchanged (~$3 of investigator either way); what changes is
that approval must now be signalled (`mctl_approve_dev_loop`) rather than
committed (`mctl_trigger_approve`), and the implementer/shepherd are driven by
the workflow rather than by separate triggers. Operators used to the legacy
sequence must be told once, in the tool descriptions and the changelog.

**Backward compatibility.** `use_temporal=true` keeps working unchanged.
`use_temporal=false` keeps working and keeps meaning legacy. The REST route
`POST /api/v1/agents/dev-loop/start` keeps its request shape and still answers
202 with `workflow_id`/`run_id` when it truly starts; the additions are the new
200 attach responses and the `mode`/`outcome`/`status` fields. Existing
consumers that only read `workflow_id` are unaffected; a consumer that treats
any 2xx as "a new run began" is exactly the consumer this proposal fixes.
`mctl-agents`' own submissions go to `/operations/{name}/execute` directly
(see the table in `internal/api/handlers_write_devloop_params_test.go:26-80`)
and are untouched.

**Deployments without Temporal.** `TEMPORAL_ADDRESS` unset leaves
`opts.TemporalClient` nil (`cmd/api/main.go:557-592`) and the default path
returns 503. This is a real regression for such a deployment and is accepted
deliberately, mitigated by an error message that names
`mode="legacy-direct"`. Production sets `TEMPORAL_ADDRESS`.

**Migrations.** None. No schema, no gitops file format, no stored state.

**Resource impact.** One extra Temporal `DescribeWorkflowExecution` only on the
collision branch (the start itself tells us when there is no collision). The
wave executor loses one Describe per item, so the net effect on the hot path is
negative. The route stays inside the 20/min write budget
(`internal/api/router.go:444-451`).

**Risks and mitigations.**
- *Conflict-policy change has a wider blast radius than the handler.* Every
  caller of the start goes through `temporalclient`; both are migrated in the
  same change, and unit tests assert the three outcomes plus the
  status-unreadable arm.
- *An `already_running` result could be read as failure by an automated
  caller.* Mitigated by 200 (not 4xx/5xx), by the outcome string matching the
  wave vocabulary operators already see, and by the message text.
- *Cross-repo drift:* `orchestrator/temporal/cli.py` starts with SDK default
  policies, so a CLI start racing an API start behaves differently. Out of
  scope here; the client doc comment records it, and a follow-up issue in
  mctl-agents should align the CLI and let the investigator's comment state the
  path it ran on (mctl-agents#289).
- *Tool-description-only criteria are easy to half-do.* The three descriptions
  named in acceptance criterion 3 are covered by a test that greps the
  registered tools' descriptions for the legacy wording.
