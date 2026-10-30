# Tasks: issue-765-dev-loop-restart-a-failed-run-whose-impl

- [ ] 1. Add `gitops.ProposalCompletion` and
  `(*Reader).ReadProposalCompletion(repo string, issue int) (*ProposalCompletion, string, error)`
  to `internal/gitops/reader.go`. It works under `r.mu.RLock()`, takes the
  revision with `revisionLocked()`, matches the exact `issue-<N>-` directory
  prefix, does Lstat and regular-file checks with a size cap, and decodes into
  a `yaml.Node` with a tri-state `head_sha`. Add the method to `GitReader` in
  `internal/api/interfaces.go`, and update every fake that implements
  `GitReader` (for example `fakeGitReader` in `internal/api/smoke_test.go`).
  DoD: `go build ./...` passes. Reader unit tests cover none, one and two
  matching directories, a missing file, a symlinked file, bad YAML, a missing
  `authoritative` block, `head_sha` null, `head_sha` set and `head_sha`
  absent.
- [ ] 2. Export a helper in `internal/temporalclient/client.go` that returns
  `(repo, issue)` from an issue URL, reusing `issueURLPattern`. Update the
  `RestartAbandonedDevLoopWorkflow` doc comments (client.go and
  interfaces.go) to cover the no-commit-failure caller. No behaviour change.
  DoD: unit test for the helper; existing temporalclient tests pass.
- [ ] 3. (depends on 1, 2) In `internal/api/handlers_dev_loop.go`:
  - Add `devLoopOutcomeRestartedAfterFailure`, `devLoopEvidenceReadTimeout`
    (5s), `StartTime` and an evidence-reference field on
    `devLoopStartResult`, and the `devLoopFailureEvidence` bundle.
  - Set `StartTime` in `classifyDevLoop`.
  - Thread `ev` through `startDevLoop` into `restartIfAbandoned`, and route
    `Failed` to the new `restartIfNoCommitFailure`, which follows the check
    order in design.md section 2.
  - Extend the doc comments, including TOCTOU, and leave the wave route
    untouched.

  DoD: the Completed branch is byte-identical in behaviour, and
  `go vet ./...` and `golangci-lint` are clean.
- [ ] 4. (depends on 3) In the `StartDevLoopWorkflow` handler:
  - Build `devLoopFailureEvidence` from `h.opts.GitReader` and
    `h.opts.AgentRegistry`, guarding against a typed nil.
  - Add the `restarted_after_failure` case (202, `previous_run_id`, audit
    message with the implementer Argo run and gitops revision).
  - Update the `already_exists` user message and the `failed` case comment.

  DoD: handler tests pass and the audit entries match the requirements.
- [ ] 5. (depends on 4) Update docs:
  - `internal/openapi/openapi.yaml`: dev-loop/start description, 202
    `outcome` enum adds `restarted_after_failure`, `previous_run_id`
    description.
  - The `mctl_trigger_issue` description in `internal/mcp/server.go`.

  DoD: the openapi lint/test (if any) passes and the `server_test.go` tool
  count is unchanged.
- [ ] 6. (depends on 4, after deploy; owner-run, not part of the implementer
  PR's DoD) Live acceptance on a dedicated throwaway test issue, never on
  mctlhq/mctl-agents#746: the owner opens a test issue, lets its DevLoop fail
  after implement with `no_commits` and `head_sha: null`, then calls
  `mctl_trigger_issue(issue_url=<test issue>, use_temporal=true)`.
  DoD:
  - The response shows `outcome: restarted_after_failure` and
    `previous_run_id` equal to the failed run.
  - `mctl_get_dev_loop` shows `Running`, and the new run reaches the approval
    gate with a fresh proposal.
  - The audit entry records both runs.
  - `dev-loop-mctlhq-mctl-agents-746` is not touched: its continuation runs
    as separate slice issues (owner decision 2026-10-23, mctlhq/.github#215).

## Tests

- [ ] T1. `restartIfAbandoned`: Failed + qualifying completion (bound
  implementer execution, `deterministic_failure`/`no_commits`, `head_sha`
  null) restarts. Expect `restarted_after_failure`, the new RunID,
  PreviousRunID equal to the failed run, and exactly one
  `RestartAbandonedDevLoopWorkflow` call.
- [ ] T2. Failed + `head_sha` set: no restart, `already_exists`,
  NotRestarted names the sha, zero restart calls.
- [ ] T3. Failed + unreadable completion (reader error, ambiguous
  directories): `failed`, the Err names the read failure, zero restart calls.
  Failed + `ListExecutions` error: same.
- [ ] T4. Failed + no proposal, no `authoritative` block, or no `head_sha`
  key: `already_exists` with the matching NotRestarted text.
- [ ] T5. Failed + `outcome` other than `deterministic_failure`, or
  `stop_reason` other than `no_commits`: `already_exists`.
- [ ] T6. Binding: no implementer execution, an execution created before the
  run's StartTime, or an `argo_workflow_name` different from
  `completion.run_id`: `already_exists`, zero restart calls.
- [ ] T7. Evidence not configured (nil Completions or nil Executions, and a
  typed-nil `*agentregistry.Store` from the handler): `already_exists`, no
  reads.
- [ ] T8. Restart echo guards on the Failed branch (error, different
  workflow id, same run id): `failed` with PreviousRunID set.
- [ ] T9. Evidence read honours `devLoopEvidenceReadTimeout`. A blocking fake
  yields `failed`, not a hang.
- [ ] T10. Regression: the existing `TestStartDevLoopWorkflow_RestartOnlyAfterAbandon`,
  `..._SkippedRestartIsExplained`, `..._NoRunIDIsNotRestarted` and
  `..._RunningLoopNeverReadsTheMarker` pass unchanged. Terminated, TimedOut
  and Canceled read no evidence.
- [ ] T11. Handler-level: a 202 body has `outcome: restarted_after_failure`
  and `previous_run_id`. The audit entry has `previous_run_id` and a message
  with the Argo run and gitops revision. A wave route test confirms a Failed
  item stays `already_exists` and no evidence is read.

## Rollback

Revert the PR and redeploy the previous mctl-api image tag (for example with
`mctl_rollback_service` or a gitops image-tag revert). The change has no
migrations or persisted state. A run already started through
`restarted_after_failure` is an ordinary DevLoopWorkflow run. Leave it, or end
it with `mctl_abandon_dev_loop` if it should not continue. There is no
separate kill switch. Unsetting `GitReader` or `AgentRegistry` would also
disable the Failed branch, but it disables unrelated endpoints too, so a
revert is the supported rollback.
