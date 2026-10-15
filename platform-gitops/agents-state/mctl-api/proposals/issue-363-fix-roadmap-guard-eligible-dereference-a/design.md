# Design: issue-363-fix-roadmap-guard-eligible-dereference-a

## Current state

Verified against the clone at `72cc1e8`.

### `internal/roadmap/wave.go`
- `PlanWave` (line 166) refuses a non-active epic at line 174, through `EpicNotActiveError`
  (done in #365).
- It decodes every item into `byID` and keeps the published `order`.
- It defines the closure `eligible(id) (*WaveItem, *WaveRefusal)`. That closure calls
  `workflowID(url)` (`WorkflowIDFunc`, line 145) and returns `RefusalNotStartable` on error.
- With no explicit items (lines 216-227), each candidate is checked once.
- With explicit items (lines 228-251):
  - The first loop calls `eligible(id)` for validation and collects refusals into a
    `SelectionError`.
  - The second loop walks `order` and runs `item, _ := eligible(id)` followed by
    `*item` (line 247-248).
  - A second `workflowID` call that now fails yields a nil `item`, which panics.
- `plan.hash()` covers `id, repository, number, workflow_id` of `Selected` in order, and
  `OperationID = "wave-" + hash[:16]`.

### `internal/roadmap/wave_test.go`
- `testWorkflowID` is the deterministic stub.
- `TestWavePlanRefusesAnEpicThatIsNotActive` covers `lifecycle-ownership` (completed) and
  `edge-ai-android` (paused) through `PlanWave`.
- It checks `epic_not_active` only on a literal `EpicNotActiveError{Lifecycle: "archived"}`.
- `livePublication(t)` (`roadmap_test.go:52`) parses `testdata/live`. `Publication.epics` is
  `[]*epicEntry` and `find` returns the stored pointer. An in-package test can therefore set
  `e.epic.Lifecycle = "archived"` on a fresh publication without regenerating digests.

### `internal/api/handlers_roadmap_wave.go`
- `roadmapWaveCallTimeout = 10s` and `roadmapWaveTimeout = 5m` are vars (lines 65-68).
- Their comment claims the call bound keeps the response inside the 30s `WriteTimeout`. That
  holds only for a single call, not for a wave.
- `ExecuteRoadmapWave` (line 259) runs these checks in order. Each refusal is audited through
  `refuse`/`auditRefusal`.
  1. Decodes the body.
  2. Reloads the publication.
  3. Checks `state_revision` (`plan_stale`).
  4. Checks freshness (`publication_too_old`).
  5. Re-derives the plan and compares hashes (`invalid_selection`).
- It then builds `wave := context.WithTimeout(context.WithoutCancel(r.Context()),
  roadmapWaveTimeout)`, so a disconnect does not abort the loop.
- For each item it makes up to two Temporal calls (`classifyDevLoop`, then
  `startDevLoopAfterNotFound`), each under `roadmapWaveCallTimeout`.
- After the loop it audits and returns 200 with `operation_id` and `outcomes`.
- Nothing caps `len(plan.Selected)`. The worst case is `min(5m, items*20s)`, which is well
  past the 30s write deadline. Past that point the response is dropped while starts continue.
- `PlanRoadmapWave` (line 194) returns `plan`, `max_age_seconds`, `executable` and
  `not_executable_reason`.

### Server and router
- `cmd/api/main.go:969-975` builds the server with
  `&http.Server{ReadTimeout: 15s, WriteTimeout: 30 * time.Second, IdleTimeout: 60s}` as
  literals.
- `internal/api/router.go:394` applies `middleware.Timeout(30s)` to the request context. The
  wave loop deliberately escapes it with `context.WithoutCancel`.
- The execute route is in the write-rate-limited group at `router.go:572`.

### `internal/mcp/roadmap_wave.go`
- The `mctl_plan_epic_wave` description (line 40) names `epic_paused / epic_completed` only.
- `mctl_start_epic_wave` (line 76-78) documents `plan_stale`, `publication_too_old`,
  `invalid_selection` and the per-item outcomes. It does not mention a cap.
- `wavePost` maps error codes to hints (lines 176-189), including `epic_not_active`.
- The MCP server's own HTTP client has `Timeout: 30s` (`internal/mcp/server.go:71`). An MCP
  caller of a slow wave therefore also times out at 30s.

### `internal/api/handlers_roadmap_wave_test.go`
- The `waveDevLoop` stub supports `hang` (Describe blocks until its ctx is done) and `slow`.
- The existing tests shorten `roadmapWaveCallTimeout`.
- `enterprise-mcp` with `required_only=true` selects 2 items.
- `cloudflare-iac` with `required_only=false` selects 6 ready, bound items, more than a cap
  of 4 (counted from `internal/roadmap/testdata/live/ready-set.json`).

### `internal/api/handlers_dev_loop.go`
- `devLoopDescribeTimeout = 10s` (line 45) says it mirrors `roadmapWaveCallTimeout`. It is
  used by the single-issue start route, which makes only one or two calls, and does not
  change here. Its comment should stop claiming a mirror.

### Deployed state checked
- `mctl_get_service_config(team=admins, service=mctl-api)` returned
  "service not found: admins/mctl-api". mctl-api is not a catalogue tenant service.
- Gitops: `$MCTL_GITOPS_ROOT/services/` (tenants `admins`, `karabu`, `labs`) has no
  `mctl-api/values.yaml`. Grepping `services/*/mctl-api/values.yaml` for `roadmap`/`ROADMAP`
  found nothing.
- Could not observe: the deployed mctl-api env, such as `ROADMAP_WAVE_MAX_AGE`, or any proxy or
  ingress timeout in front of it. Neither read showed it. This is recorded under Open
  questions; it is not treated as absent.
- Nothing in this change reads new env vars, so the deployed config does not affect
  correctness. An ingress timeout shorter than 30s would make the margin smaller than
  intended.

## Proposed solution

### 1. `PlanWave`: build once, reuse (item 2)

In the explicit-items branch, keep the `WaveItem` built during validation:

```go
built := make(map[string]WaveItem, len(req.Items))
for _, id := range req.Items {
    if _, dup := built[id]; dup || requested[id] { ...duplicate... }
    requested[id] = true
    item, refusal := eligible(id)
    if refusal != nil { refused = append(refused, *refusal); continue }
    built[id] = *item
}
if len(refused) > 0 { return nil, &SelectionError{Refused: refused} }
for _, id := range order {
    if it, ok := built[id]; ok { plan.Selected = append(plan.Selected, it) }
}
```

- `WorkflowIDFunc` is called once per id. The second pass has nothing to dereference, so the
  nil path disappears entirely. It is not merely guarded.
- Ordering still follows `order`, so `Selected` and `PlanHash` are byte-identical for
  deterministic lookups.
- Duplicate detection uses `requested`, unchanged.
- Update the doc comment to state that `WorkflowIDFunc` is consulted once per item.

### 2. Bounded synchronous execution (item 3, design a)

**`internal/api`, new exported constant** in a small file such as `server_timeouts.go`, or in
`handlers_roadmap_wave.go`:

```go
// ServerWriteTimeout is the http.Server WriteTimeout cmd/api/main.go uses.
// Any handler that does bounded synchronous work derives its budget from it.
const ServerWriteTimeout = 30 * time.Second
```

`cmd/api/main.go:973` becomes `WriteTimeout: mctlapi.ServerWriteTimeout`. The package is
already imported as `mctlapi`, as in `mctlapi.DefaultRoadmapWaveMaxAge`.

**`handlers_roadmap_wave.go` constants**, replacing lines 59-68. The comment states the
relation:

```go
// Wave execution is synchronous and must answer before the server's
// ServerWriteTimeout (30s): a response written later is dropped while the
// DevLoops it started keep running. So:
//   roadmapWaveBudget   = ServerWriteTimeout - roadmapWaveResponseMargin (25s)
//   worst case per item = 2 * roadmapWaveCallTimeout (Describe + Start, 6s)
//   roadmapWaveMaxItems = roadmapWaveBudget / (2 * roadmapWaveCallTimeout) (4)
// and a plan with more items is refused (wave_too_large) rather than
// started in part. TestRoadmapWaveBudgetFitsTheWriteTimeout pins this.
const roadmapWaveResponseMargin = 5 * time.Second
var (
    roadmapWaveCallTimeout = 3 * time.Second
    roadmapWaveBudget      = ServerWriteTimeout - roadmapWaveResponseMargin
)
func roadmapWaveMaxItems() int { return int(roadmapWaveBudget / (2 * roadmapWaveCallTimeout)) }
```

`roadmapWaveTimeout` (5m) is removed.

New codes: `roadmapCodeWaveTooLarge = "wave_too_large"` and
`roadmapCodeWaveBudgetExhausted = "wave_budget_exhausted"`.

**`ExecuteRoadmapWave` changes:**
- Record `begun := time.Now()` at handler entry, and set `deadline := begun.Add(roadmapWaveBudget)`.
- After the plan-hash check (step 4), and before any Temporal call:
  - If `len(plan.Selected) > roadmapWaveMaxItems()`, call
    `refuse(422, wave_too_large, "...plan at most N items per execute: pass explicit items",
    {"selected": n, "max_items": max})`.
  - If `time.Until(deadline) < time.Duration(n) * 2 * roadmapWaveCallTimeout`, call
    `refuse(503, wave_budget_exhausted, ...)`. This catches a slow publication reload
    eating the budget, so the wave still never starts in part.
- Replace the wave context with
  `context.WithDeadline(context.WithoutCancel(r.Context()), deadline)`. Disconnect
  tolerance stays (`TestRoadmapWave_DisconnectDoesNotAbortTheWave`). The per-call contexts
  derive from it as today.
- With the cap and the pre-check together, the loop's worst case fits the budget and the
  deadline is a hard backstop.

**`PlanRoadmapWave` changes:**
- Always include `"max_items_per_execute": roadmapWaveMaxItems()`.
- If `len(plan.Selected) > cap`, set `executable=false` and
  `not_executable_reason = "wave_too_large: N items selected; at most M per execute — plan
  again with explicit items"`.
- Precedence: `wave_execution_disabled` and `publication_too_old` first, then the empty
  selection, then too-large.

**Splitting a large wave.** Callers split with the existing explicit-`items` plan. Each
subset is its own plan with its own `PlanHash` and `OperationID`. Per-item starts are
idempotent (`already_running`), so overlapping subsets are harmless.

### 3. MCP contract (`internal/mcp/roadmap_wave.go`)

- `mctl_plan_epic_wave` description:
  - Change to "a paused, completed or otherwise inactive epic is refused (epic_paused /
    epic_completed / epic_not_active)".
  - Add: "A single start may contain at most max_items_per_execute items (returned by the
    plan); a larger plan is not executable (wave_too_large): plan again with explicit items."
- `mctl_start_epic_wave` description: add "The call is synchronous and answers within the
  server's 30s write deadline: a plan with more than max_items_per_execute items (4) is
  refused with wave_too_large and nothing starts; wave_budget_exhausted means nothing was
  started and the same plan may be retried."
- Name the number through a shared constant. The `mcp` package cannot import `api` without a
  cycle; this needs checking. If it cannot, write the number in prose and add a test in
  `internal/api` that asserts `roadmapWaveMaxItems() == 4`. That test fails if the cap and the
  MCP description drift apart.
- `wavePost` hints:
  - `wave_too_large`: "Nothing was started. Plan again with explicit items, at most
    max_items_per_execute per plan, and start each plan."
  - `wave_budget_exhausted`: "Nothing was started. Retry the same plan."

### 4. Tests

The test plan is in tasks.md. In summary:
- The `PlanWave` regression uses a `WorkflowIDFunc` that fails on the second call for one id.
- The `epic_not_active` case goes through `PlanWave`.
- A budget invariant test.
- Handler tests for the cap, the hanging-client bound and the budget pre-check.
- The MCP description and hint tests.

## Alternatives

- **(b) Asynchronous execute with 202 + operation id.**
  - Pros: unbounded wave size, and no cap for users.
  - Dropped because the "existing operations API" (`GET /api/v1/operations/{name}`,
    `mctl_get_operation`) serves operation metadata only, not run records. Design (b) needs:
    - a new durable outcome store (Postgres table or audit-log query);
    - a new read route and a new MCP tool;
    - a background goroutine whose lifetime outlives the request and the pod drain. The
      server has a `draining` flag, and a goroutine killed mid-wave loses outcomes unless it
      is persisted per item.
  - That is much larger than a P3 follow-up, and harder to make correct across replicas.
- **Keep a 10s call timeout and cap at 1 item.** Ten seconds gives
  `floor(25/20) = 1` item per execute. A one-item cap makes "wave" meaningless. Temporal
  Describe/Start are sub-second in the normal case, so 3s per call is generous.
- **Only shorten `roadmapWaveTimeout` to 25s without a cap.** This bounds the response, but
  a large wave would start a prefix and report the tail as `failed` with a deadline error. The
  issue explicitly asks to refuse rather than start part.
- **For item 2, re-check the refusal in the second pass and return an internal error.** This
  works, but still calls `WorkflowIDFunc` twice, and gives a nondeterministic lookup a
  confusing error. Building once is simpler and removes the failure mode.

## Platform impact

- **Migrations:** none. No schema, Helm or env-var changes.
- **API compatibility:**
  - `/roadmap/waves/execute` gains two refusal codes (422 `wave_too_large` and 503
    `wave_budget_exhausted`).
  - The plan response gains `max_items_per_execute` and may report `executable=false` for
    plans of more than 4 items.
  - A client that executed a 5+ item plan in one call before will now be refused, with
    nothing started. That is intended. Today such a call already risked a dropped response.
  - Today's live fixtures show at most 6 ready items per epic (`cloudflare-iac`, optional
    included), so real waves are small.
- **Behaviour change per call:** each Temporal call now has 3s instead of 10s. A slow
  Temporal makes items report `failed` sooner. They are retryable by re-executing the same
  plan, because starts are idempotent.
- **Resources:** none. The change only shortens the worst-case handler time.
- **Risks:**
  - An ingress or proxy timeout below 30s would leave less margin than intended. This could
    not be observed (see Open questions in requirements.md); the 5s margin absorbs small
    differences.
  - The cap and the MCP prose can drift. Mitigation: the pinning test described above.
- **Rollback:** revert the PR. It has no persisted state.
