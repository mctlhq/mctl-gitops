# Guard the wave planner's second eligibility pass and bound wave execution under the server WriteTimeout

## Context
Issue mctlhq/mctl-api#363 collects the follow-ups from the final review of the governed
wave start (#334, #361). Item 1, refusing a non-active epic, was done in #365. Three items remain:

- In `internal/roadmap/wave.go`, `PlanWave` checks every requested id with `eligible(id)` in
  its explicit-items branch. It then calls `eligible(id)` again, throws away the refusal and
  dereferences `*item`. If `WorkflowIDFunc` returns a different answer on the second call,
  `item` is nil and the API process panics inside a request.
- `ExecuteRoadmapWave` in `internal/api/handlers_roadmap_wave.go` lets a wave run for up to
  `roadmapWaveTimeout = 5m`, at `roadmapWaveCallTimeout = 10s` per Temporal call. The HTTP
  server in `cmd/api/main.go` sets `WriteTimeout: 30s`. A wave with several slow items keeps
  starting DevLoops after its response can no longer reach the caller, and no operation
  record lets the caller read those outcomes back.
- Small tails from item 1:
  - The `mctl_plan_epic_wave` description names only two of the three refusal codes.
  - `epic_not_active` is never exercised through `PlanWave`.

This proposal implements design (a) from the issue: execution stays synchronous and is bounded.
The wave budget comes from one shared server write-timeout constant. A single execute call may
start only a capped number of items. A plan larger than the cap is refused with a typed code
before anything starts.

## User stories
- AS a platform operator I WANT `PlanWave` to never panic on a nondeterministic workflow-id
  lookup SO THAT a bad lookup is a typed refusal and does not crash a request.
- AS an admin starting an epic wave through REST or `mctl_start_epic_wave` I WANT every
  execute call to answer within the server's write deadline SO THAT I always get the per-item
  outcomes of the DevLoops it started.
- AS an admin planning a wave I WANT the plan to tell me when a wave is too large to run in
  one call SO THAT I can split it into explicit-item plans before executing.
- AS an MCP client author I WANT the tool descriptions to list every refusal code the
  handlers can return SO THAT my client handles all of them.

## Acceptance criteria (EARS)
- WHEN `PlanWave` is called with explicit `Items` THE SYSTEM SHALL build each `WaveItem`
  exactly once, in the validation pass, and call `WorkflowIDFunc` at most once per id.
- IF a requested id is refused (including `not_startable` because `WorkflowIDFunc` failed)
  THEN THE SYSTEM SHALL return a `*SelectionError` naming it and SHALL NOT panic.
- WHILE the selection is valid THE SYSTEM SHALL return `Selected` in published order, not
  request order, with the same `PlanHash` as before for the same selection.
- THE SYSTEM SHALL define the HTTP server write timeout as one exported constant,
  `api.ServerWriteTimeout` (30s). `cmd/api/main.go` SHALL use it for `http.Server.WriteTimeout`.
- THE SYSTEM SHALL derive the wave budget as `ServerWriteTimeout - roadmapWaveResponseMargin`,
  where the margin is 5s, giving 25s.
- THE SYSTEM SHALL derive the per-execute item cap as
  `floor(budget / (2 * roadmapWaveCallTimeout))`, where the call timeout is 3s, giving a cap
  of 4.
- WHILE the package is built THE SYSTEM SHALL have unit tests that fail if:
  - the budget is not below `ServerWriteTimeout`;
  - `cap * 2 * roadmapWaveCallTimeout` exceeds the budget;
  - the cap is less than 1.
- IF an execute request's re-derived plan selects more items than the cap THEN THE SYSTEM SHALL:
  - refuse it with HTTP 422 and code `wave_too_large`;
  - include `{"selected": N, "max_items": cap}` in the error details;
  - audit the refusal;
  - start nothing.
- IF the time left before the wave deadline, measured from the start of the handler, is less
  than the selected items' worst case (`items * 2 * roadmapWaveCallTimeout`) when the start
  loop is about to begin THEN THE SYSTEM SHALL:
  - refuse with HTTP 503 and code `wave_budget_exhausted`;
  - audit the refusal;
  - start nothing.
- WHEN an execute call runs the start loop THE SYSTEM SHALL bound the whole loop by a deadline
  of handler start plus budget. A client disconnect SHALL still not abort the loop.
- WHEN `/api/v1/roadmap/waves/plan` returns a plan with more selected items than the cap THE
  SYSTEM SHALL:
  - report `executable: false`;
  - set `not_executable_reason` to start with `wave_too_large`;
  - include `max_items_per_execute` in every plan response.
- THE SYSTEM SHALL document the cap, `wave_too_large` and `wave_budget_exhausted` in both the
  REST handler's comments and the `mctl_start_epic_wave` / `mctl_plan_epic_wave` tool
  descriptions.
- WHEN the MCP wave tools receive `wave_too_large` THE SYSTEM SHALL add a hint telling the
  caller to plan again with explicit `items`, at most the cap per plan.
- WHEN the MCP wave tools receive `wave_budget_exhausted` THE SYSTEM SHALL add a hint telling
  the caller to retry the same plan.
- THE SYSTEM SHALL name all three refusal codes `epic_paused`, `epic_completed` and
  `epic_not_active` in the `mctl_plan_epic_wave` description.
- WHEN `PlanWave` runs for an epic whose lifecycle is not `active`, `paused` or `completed`
  THE SYSTEM SHALL return an `*EpicNotActiveError` with reason `epic_not_active`. A test
  SHALL cover this through `PlanWave`.

## Out of scope
- The epic lifecycle model, the published ready set, and the `roadmap-validate` CI check
  (mctlhq/.github#161).
- Asynchronous execution (design b): a 202 with an operation id and a persistent per-item
  outcome store. `mctl_get_operation` / `GET /api/v1/operations/{name}` serves only operation
  schemas (`internal/api/router.go`, "Operation registry (metadata only)"). Design (b) would
  need a new store and a new read API.
- Changing the server's `ReadTimeout` or `IdleTimeout`, or the 30s chi
  `middleware.Timeout` at `internal/api/router.go:394`. The last could also adopt the new
  constant, but that is optional.
- Splitting a large wave automatically across several executes on the server.

## Open questions
- Cap size: a 3s call timeout gives 4 items per execute. If Temporal Describe/Start latency in
  production regularly approaches 3s, items will report `failed` with a deadline error.
  Executes are idempotent, so the caller can rerun the same plan. Should the call timeout be
  4s (cap 3) instead? This proposal uses 3s and keeps it a package var.
- The new refusal statuses are 422 (`wave_too_large`) and 503 (`wave_budget_exhausted`). The
  issue allows 409 or 422 for a too-large plan. 422 was chosen because resubmitting the same
  plan can never succeed.
- The live deployed config of mctl-api (any env override of timeouts) could not be observed;
  see design.md "Deployed state checked".
