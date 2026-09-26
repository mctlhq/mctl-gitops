# Tasks: issue-401-feat-agents-make-the-temporal-devloop-th

- [ ] 1. Add the outcome-bearing start to `internal/temporalclient/client.go`:
      `StartResult{WorkflowID, RunID, Outcome, Status}`, the exported outcome
      constants (`OutcomeStarted`, `OutcomeAlreadyRunning`,
      `OutcomeAlreadyExists`), `IsAlreadyStarted(err)` next to the existing
      `IsNotFound` (line 310), and `StartDevLoop(ctx, issueURL)` using
      `REJECT_DUPLICATE` + `WORKFLOW_ID_CONFLICT_POLICY_FAIL`, classifying an
      `*serviceerror.WorkflowExecutionAlreadyStarted` through `DescribeDevLoop`.
      Keep `StartDevLoopWorkflow` as a wrapper. — DoD: `go test ./internal/temporalclient/...`
      passes; a Describe failure on the collision branch returns an error rather
      than guessing an outcome; the doc comment names the new policy and still
      points at `orchestrator/temporal/cli.py`.
- [ ] 2. (depends on 1) Add `StartDevLoop` to the `DevLoopClient` interface
      (`internal/api/interfaces.go:77-85`) and to `fakeDevLoopClient`
      (`internal/api/handlers_dev_loop_test.go:60-125`) with per-test outcome,
      status and error knobs. — DoD: `go build ./...` and the existing dev-loop
      handler tests pass unchanged.
- [ ] 3. (depends on 2) Rewrite `Handlers.StartDevLoopWorkflow`
      (`internal/api/handlers_dev_loop.go:69-122`) to switch on the outcome:
      202 `started`; 200 `already_running` / `already_exists` with `status`;
      502 when an existing execution's status is unreadable, stating nothing was
      started; 400 for `ErrInvalidIssueURL`; 502 for other Temporal failures.
      Every success body carries `mode:"devloop"`, `outcome`, `workflow_id`, and
      `run_id` when known. Audit params gain `mode` and `outcome`. — DoD: no
      response can contain the word "started" unless a new execution was
      created; audit `WorkflowName` stays empty on failures.
- [ ] 4. (depends on 1) Migrate the wave executor
      (`internal/api/handlers_roadmap_wave.go:349-379`) from Describe-then-Start
      to `StartDevLoop`, redefining `waveOutcome*` (lines 70-75) in terms of the
      `temporalclient` constants. — DoD: `go test ./internal/api/...` including
      `handlers_roadmap_wave_test.go` passes with the outcome strings unchanged
      on the wire.
- [ ] 5. (depends on 3) Add `mode` (enum `devloop` | `legacy-direct`, optional,
      default `devloop`) to `mctl_trigger_issue`
      (`internal/mcp/server.go:3006-3060`); implement the resolution order
      (conflict between `mode` and `use_temporal` → tool error; unknown `mode`
      → tool error; `use_temporal` true/false → alias with a deprecation note;
      absent → `devloop`), delete `mode` from the params passed to
      `/operations/mctl-agents-investigate/execute`, and annotate the reply with
      the `mode` that ran (merge into the JSON object, or prefix a line when the
      body is not an object). — DoD: no argument combination can reach the
      legacy path without an explicit `mode="legacy-direct"` or
      `use_temporal=false`.
- [ ] 6. (depends on 5) On the devloop branch, surface a 503 as a tool error
      whose text names `mode="legacy-direct"` as the explicit fallback; no
      automatic fallback anywhere. — DoD: a test with a 503 backend asserts the
      legacy route was never called and that the error text contains
      `legacy-direct`.
- [ ] 7. (depends on 5) Update the descriptions so the Temporal path reads as
      canonical: `mctl_trigger_issue`, `mctl_trigger_approve`
      (`server.go:2973`), `mctl_approve_dev_loop` (`server.go:3068`),
      `mctl_get_dev_loop` (`server.go:3110`), and the
      `mctl-agents-investigate` operation description
      (`internal/operations/registry.go:695-697`). Remove "until that slice is
      proven in production", "Defaults to false", and "predates use_temporal".
      — DoD: `grep -n "Defaults to false" internal/mcp/server.go` returns
      nothing for this tool; each of the three tools named in the issue's
      acceptance criterion 3 describes the Temporal path as canonical.
- [ ] 8. (depends on 3) Update `internal/openapi/openapi.yaml:2258-2300`: the
      200 attach responses, and `mode` / `outcome` / `status` on the 202 and 200
      schemas. — DoD: the documented fields match what the handler writes; any
      OpenAPI lint/smoke test in `internal/api/smoke_test.go` still passes.
- [ ] 9. (depends on 7) Open a follow-up issue in `mctlhq/mctl-agents` for #289
      (the investigator's proposal comment should state the path it ran on) and
      for aligning `orchestrator/temporal/cli.py`'s start policies with
      `StartDevLoop`. — DoD: both issues exist and are linked from
      mctl-api#401; no code in this repo depends on them.
- [ ] 10. (depends on 3, 5, 7) Run `go fmt ./... && go vet ./... && golangci-lint run && go test ./...`
      per `CLAUDE.md`. — DoD: all clean; the MCP tool-count/hint expectation in
      `internal/mcp/server_test.go:34,65-67` is untouched because no tool was
      added or removed.

## Tests

- [ ] T1. `internal/temporalclient`: `StartDevLoop` returns `started` on a clean
      start; `already_running` when the mocked start yields
      `WorkflowExecutionAlreadyStarted` and Describe says `Running`;
      `already_exists` for every closed status; an error (and no outcome) when
      Describe fails on the collision branch. Extend the existing SDK mock in
      `client_mock_test.go`.
- [ ] T2. `internal/api`: `StartDevLoopWorkflow` answers 202 + `outcome=started`
      on a fresh start, and 200 + `outcome=already_running` + `status=Running`
      on a collision — asserting the body does **not** say "started"
      (mctl-api#287, the precondition criterion).
- [ ] T3. `internal/api`: 200 + `already_exists` for a closed execution, 502
      with "nothing was started" for the unreadable-status arm, 400 for a
      malformed `issue_url` with no audit entry, 502 + `failed` audit with an
      empty `WorkflowName` for a Temporal RPC failure (keep
      `TestStartDevLoopWorkflow_TemporalFailureIs502` green).
- [ ] T4. `internal/api`: the `dev-loop-start` audit entry carries `mode` and
      `outcome` for each of the three outcomes.
- [ ] T5. `internal/mcp`: `mctl_trigger_issue` with only `issue_url` hits
      `/api/v1/agents/dev-loop/start` and never
      `/api/v1/operations/mctl-agents-investigate/execute` — the inverse of
      today's `TestToolTriggerIssue_...PostsToOperationsExecute`
      (`server_test.go:1080-1140`), which must be rewritten to pass
      `mode="legacy-direct"`.
- [ ] T6. `internal/mcp`: `mode="legacy-direct"` hits operations-execute and
      the forwarded params contain no `mode` key; `mode="devloop"` and the
      deprecated `use_temporal=true` both hit the dev-loop route;
      `use_temporal=false` alone hits operations-execute with a deprecation note
      in the result text.
- [ ] T7. `internal/mcp`: conflicting (`mode="devloop"`, `use_temporal=false`)
      and (`mode="legacy-direct"`, `use_temporal=true`) return a tool error and
      call neither backend route; an unknown `mode` does the same.
- [ ] T8. `internal/mcp`: the result of both branches states the mode that ran
      (`mode` key present in the JSON reply, or the prefixed line for a
      non-object body).
- [ ] T9. `internal/mcp`: a description test asserting that
      `mctl_trigger_issue`, `mctl_trigger_approve` and `mctl_approve_dev_loop`
      each describe the Temporal DevLoop as canonical and that none of them
      contains "Defaults to false" or "until that slice is proven in
      production".
- [ ] T10. `internal/api`: the wave executor still reports the same four
      outcome strings after the migration to `StartDevLoop`, including the
      fail-closed arm when the DevLoop state cannot be read.

## Rollback

Three independent levers, smallest first:

1. **Behaviour only.** Revert task 5's default in
   `internal/mcp/server.go` so an absent `mode` resolves to `legacy-direct`
   again (a one-line change in the resolution function). The honest-reporting
   fix from tasks 1-3 stays in place; operators who pass `mode="devloop"` or
   `use_temporal=true` keep the Temporal path. Ship as a patch release.
2. **Reporting.** If the conflict-policy change misbehaves against the
   production Temporal server, revert task 1's policy line to
   `WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING` and classify with a pre-start
   `DescribeDevLoop` instead (design alternative 4): honest reporting is kept,
   only the race-freedom is lost.
3. **Full revert.** `git revert` the merge commit and redeploy the previous
   image tag — nothing here writes state, so there is no data to unwind. Any
   DevLoopWorkflow already started keeps running and can still be approved with
   `mctl_approve_dev_loop`; the observable regression is only that
   `mctl_trigger_issue` again defaults to the legacy path.

Verification after any rollback: `mctl_trigger_issue` on a scratch issue,
followed by `mctl_get_dev_loop(issue_url=...)`, must agree — a reported start
means a live execution, a reported legacy run means `workflow not found`.
