# Tasks: issue-363-fix-roadmap-guard-eligible-dereference-a

- [ ] 1. `internal/roadmap/wave.go`: in the explicit-items branch of `PlanWave`, store the
  `WaveItem` that the validation pass builds, keyed by id (`built map[string]WaveItem`). Fill
  `plan.Selected` by walking `order` over that map, and delete the second `eligible(id)` call.
  Update the doc comment: `WorkflowIDFunc` is consulted once per item.
  — DoD:
  - No `item, _ :=` pattern remains.
  - Existing `wave_test.go` tests pass unchanged, with the same `Selected` order and the same
    `PlanHash`.
- [ ] 2. `internal/api`: add the exported `ServerWriteTimeout = 30 * time.Second` with a doc
  comment. Use it in `cmd/api/main.go` (`WriteTimeout: mctlapi.ServerWriteTimeout`).
  — DoD:
  - No `30 * time.Second` literal remains for `WriteTimeout` in main.go.
  - `go build ./...` passes.
- [ ] 3. (depends on 2) `internal/api/handlers_roadmap_wave.go`: replace
  `roadmapWaveTimeout` with the following, plus the comment stating
  `budget = WriteTimeout - margin` and `cap = budget / (2 * call)`:
  - `roadmapWaveResponseMargin = 5s`
  - `roadmapWaveBudget = ServerWriteTimeout - roadmapWaveResponseMargin`
  - `roadmapWaveCallTimeout = 3s`
  - `roadmapWaveMaxItems()`

  Add the codes `wave_too_large` and `wave_budget_exhausted`. Fix the
  `devLoopDescribeTimeout` comment in `handlers_dev_loop.go` so it no longer claims to
  mirror the wave call timeout.
  — DoD: the constants compile and the comment names `ServerWriteTimeout`.
- [ ] 4. (depends on 3) `ExecuteRoadmapWave`:
  - Record the handler start and compute `deadline = start + roadmapWaveBudget`.
  - After the plan-hash check, refuse with an audit:
    - 422 `wave_too_large`, details `{selected, max_items}`, when
      `len(plan.Selected) > roadmapWaveMaxItems()`;
    - 503 `wave_budget_exhausted` when the time left is less than `n * 2 * call timeout`.
  - Run the loop under `context.WithDeadline(context.WithoutCancel(r.Context()), deadline)`.

  — DoD:
  - No code path in the handler can run past `start + roadmapWaveBudget`.
  - Both refusals happen before any Temporal call.
- [ ] 5. (depends on 3) `PlanRoadmapWave`:
  - Always return `max_items_per_execute`.
  - When the selection exceeds the cap, set `executable=false` and
    `not_executable_reason="wave_too_large: ..."`. This comes after the disabled, too-old and
    empty reasons.

  — DoD: the plan response is consistent with what execute would do.
- [ ] 6. (depends on 4, 5) `internal/mcp/roadmap_wave.go`:
  - `mctl_plan_epic_wave` description names `epic_paused / epic_completed / epic_not_active`
    and `max_items_per_execute` / `wave_too_large`.
  - `mctl_start_epic_wave` description states the synchronous, 30s-bounded contract, the cap
    of 4 items, `wave_too_large` (nothing started, split with explicit items) and
    `wave_budget_exhausted` (nothing started, retry).
  - `wavePost` gets hints for both new codes.

  — DoD: the REST handler comment and both tool descriptions describe the same contract.
- [ ] 7. Run `go fmt`, `go vet ./...`, `golangci-lint run` and `go test ./...`. The MCP tool
  count is unchanged (no tools added or removed), so the expectation in `server_test.go`
  stays the same.
  — DoD: everything is green.

## Tests
- [ ] T1. `internal/roadmap/wave_test.go`, `TestWavePlanExplicitItemsConsultWorkflowIDOnce`:
  - A `WorkflowIDFunc` wraps `testWorkflowID`, counts calls per URL and returns an error on
    the second call for one selected enterprise-mcp item.
  - `PlanWave` with explicit items (all ready, required ids) must return a plan without
    panicking, with each URL looked up exactly once.
  - `Selected` and `PlanHash` must equal those of the plain `testWorkflowID` plan.
  - Before task 1 this test panics (nil dereference at wave.go:248).
- [ ] T2. `wave_test.go`, a new case in or next to `TestWavePlanRefusesAnEpicThatIsNotActive`:
  - Take a fresh `livePublication(t)`, `find("enterprise-mcp")`, and set
    `e.epic.Lifecycle = "archived"`.
  - Run `PlanWave` with both the all-items and explicit-items requests.
  - Expect `ErrEpicNotActive`, `*EpicNotActiveError`, `Reason() == epic_not_active` and a
    nil plan.
- [ ] T3. `internal/api/handlers_roadmap_wave_test.go`,
  `TestRoadmapWaveBudgetFitsTheWriteTimeout`. Assert all of the following with the package
  defaults:
  - `roadmapWaveBudget < ServerWriteTimeout`
  - `roadmapWaveMaxItems() >= 1`
  - `time.Duration(roadmapWaveMaxItems())*2*roadmapWaveCallTimeout <= roadmapWaveBudget`
  - `roadmapWaveMaxItems() == 4`, which pins the number printed in the MCP description.
- [ ] T4. `TestRoadmapWave_TooLargeIsRefusedBeforeAnyStart`:
  - Plan `cloudflare-iac` with `required_only=false`, which selects 6 items.
  - The plan response has `executable=false`, a `wave_too_large` reason and
    `max_items_per_execute=4`.
  - Execute returns 422 `wave_too_large` with details `{selected: 6, max_items: 4}`.
  - The stub records zero Describe/Start calls and `e.tc.started` is empty.
  - An audited `failed` entry has reason `wave_too_large`.
- [ ] T5. `TestRoadmapWave_ABlockingTemporalCannotHoldTheResponsePastTheBudget`:
  - Set `roadmapWaveCallTimeout=50ms` and `roadmapWaveBudget=250ms`, restored with
    `t.Cleanup`.
  - Plan enterprise-mcp (2 items) with every workflow id in `hang`. Extend the stub with a
    blocking Start, or hang Describe only.
  - Run `ExecuteRoadmapWave` in a goroutine and assert it returns within `budget + slack`.
  - Assert the response is 200, with each item `failed` with a deadline error.
  - Use a second variant with 6 items (cloudflare-iac) to observe the 422 refusal promptly.
  - Before the fix (5m wave timeout, no cap) the 6-item variant runs about `6 * 2 * 50ms`
    past the budget and starts some items, so the test fails.
- [ ] T6. `TestRoadmapWave_ExhaustedBudgetStartsNothing`: set `roadmapWaveBudget` smaller than
  `2 * 2 * roadmapWaveCallTimeout` (for example 10ms with a 50ms call timeout). Execute
  returns 503 `wave_budget_exhausted`, nothing is started, and the refusal is audited.
- [ ] T7. The existing handler tests still pass with the new defaults:
  - `DisconnectDoesNotAbortTheWave`
  - `ASlowItemDoesNotStarveTheOthers`
  - `DescribeAndStartHaveTheirOwnBudgets`

  Where a test sets `roadmapWaveCallTimeout`, the budget must still admit the 2-item
  enterprise-mcp wave. With the default 25s budget and a 50-80ms call timeout it does.
- [ ] T8. `internal/mcp`: assert the following, extending existing description and hint tests
  if any:
  - the `mctl_plan_epic_wave` description contains all three of `epic_paused`,
    `epic_completed` and `epic_not_active`;
  - the `mctl_start_epic_wave` description contains `wave_too_large`;
  - `wavePost` adds the hints for `wave_too_large` and `wave_budget_exhausted`, tested with an
    `httptest` server answering those codes.

## Rollback
Revert the PR. It changes no persisted state, schema, Helm values or env vars. After a revert:
- waves of any size are accepted again, under the old 5m / 10s bounds and their
  dropped-response risk;
- the `PlanWave` panic path returns.

If only the cap causes trouble, for example real waves often exceed 4 items, a small
follow-up can raise `roadmapWaveCallTimeout`/margin trade-offs or move to design (b). The
`PlanWave` fix can stay.
