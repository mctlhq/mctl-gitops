# Design: issue-765-dev-loop-restart-a-failed-run-whose-impl

## Current state

- `internal/api/handlers_dev_loop.go`
  - `startDevLoop(ctx, c DevLoopClient, issueURL, workflowID)` runs
    `classifyDevLoop`. Anything that classifies `already_exists` goes to
    `restartIfAbandoned`.
  - `classifyDevLoop` calls `DescribeDevLoopExecution` and maps any non-Running
    status to `already_exists` with `Status` and `RunID`. It discards
    `DevLoopExecution.StartTime`.
  - `restartIfAbandoned` returns `existing` unchanged unless
    `existing.Status == devLoopStatusCompleted && existing.RunID != ""`. It
    then reads the result through `DevLoopEnded` (bounded by
    `devLoopResultReadTimeout`, 5s) and restarts through
    `RestartAbandonedDevLoopWorkflow` only on an `abandoned: ` result with
    `implement == null`. It has echo guards for a mismatched workflow id and
    for the restart returning the same run id. A skipped restart is explained
    in `devLoopStartResult.NotRestarted`.
  - `StartDevLoopWorkflow` (the handler) switches on the outcome. Each case
    writes one `dev-loop-start` audit entry. The `already_exists` message
    says "Only a run abandoned before it reached the implement step is
    restarted."
  - Outcome constants live in the `devLoopOutcome*` block. The wave route
    (`handlers_roadmap_wave.go`) aliases them and composes `classifyDevLoop`
    and `startDevLoopAfterNotFound` directly, so it never restarts.
- `internal/temporalclient/client.go`
  - `RestartAbandonedDevLoopWorkflow` is `startDevLoop` with
    `WORKFLOW_ID_REUSE_POLICY_ALLOW_DUPLICATE` and `USE_EXISTING`. The doc
    comment says it must only be called right after the caller observed an
    abandoned run.
  - `DevLoopEnded` documents that a non-Completed run has no result: `Get`
    returns the failure. So a Failed run's completion cannot come from the
    workflow result.
  - `issueURLPattern` / `WorkflowIDForIssueURL` and
    `proposalSlugPattern = ^issue-([0-9]+)-` already encode the
    issue-to-workflow-id and slug-to-issue mappings.
- `internal/api/interfaces.go`
  - `DevLoopClient` holds the Temporal methods.
  - `GitReader` is the gitops.Reader subset used by handlers. It already
    exposes `ListHumanInputRequests`, which walks
    `platform-gitops/agents-state/<service>/proposals/<proposal>/` with Lstat
    and regular-file checks (`internal/gitops/reader.go`).
- `internal/gitops/reader.go`: `ReadFiles` and `revisionLocked` show the
  pattern for reading under `r.mu.RLock()` together with the checkout
  revision.
- `internal/agentregistry/store.go`:
  `ListExecutions(ctx, agent, workflowID, limit)` returns `AgentExecution`
  rows newest first. Each row has `TemporalWorkflowID`, `ArgoWorkflowName`,
  `Phase` and `CreatedAt`. The handler reaches it through
  `h.opts.AgentRegistry *agentregistry.Store`, which may be nil.
- Tests: `internal/api/handlers_dev_loop_test.go` (`fakeDevLoopClient`,
  `TestStartDevLoopWorkflow_RestartOnlyAfterAbandon`,
  `..._SkippedRestartIsExplained`,
  `..._RunningLoopNeverReadsTheMarker`). The wave test fake is
  `internal/api/handlers_roadmap_wave_test.go`.
- Docs: `internal/openapi/openapi.yaml` (the dev-loop/start description and
  the 202 `outcome` enum `[started, restarted_after_abandon]`) and the
  `mctl_trigger_issue` description in `internal/mcp/server.go` (around line
  2921).

Deployed state checked:
- `mctl_get_dev_loop(workflow_id=dev-loop-mctlhq-mctl-agents-746)`: status
  `Failed`, `shepherd_in_loop_known: true`. This matches the issue.
- `mctl_list_agent_executions(workflow_id=dev-loop-mctlhq-mctl-agents-746)`
  returned two rows:
  - `implementer` 1.91.0, `argo_workflow_name: mctl-agents-implement-70aeec81`,
    phase `Failed`, created 2026-10-23T07:20:10Z.
  - `issue-investigator`, created 2026-10-21T23:57:07Z.
  So the binding this design relies on exists in production.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-agents/proposals/issue-746-spike-runtime-evaluate-a-portable-single/.status.yaml`:
  - `status: needs-triage`, `failure.code: no-commits`,
    `attempt.id: fc6abfff...`.
  - `completion.run_id: mctl-agents-implement-70aeec81`.
  - `completion.authoritative`: `outcome: deterministic_failure`,
    `stop_reason: no_commits`, `head_sha: null`, `attempt_id` equal to
    `attempt.id`, `primary_observed: true`.
  - A second directory, `issue-759-spike-runtime-746-slice-1-...`, exists.
    It does not match the `issue-746-` prefix, which confirms that an exact
    `issue-<N>-` prefix match is required.
- mctl-api's own deployment values: no `services/*/mctl-api/values.yaml`
  exists under `$MCTL_GITOPS_ROOT/services`. The only reference found is
  `infra-components/data/temporal/networkpolicy.yaml`, which names an
  `mctl-api.yaml` with `TEMPORAL_ADDRESS`. I did not observe whether the
  deployed mctl-api has both the gitops reader and the agent registry
  configured. See Open questions.

## Proposed solution

Extend the single-issue route's restart decision with one sibling branch for
`Failed`. Evidence for it comes from two independent sources that must agree.
The Completed/abandon branch, the wave route and the plain start stay as
they are.

### 1. Evidence reader in gitops

Add `gitops.ProposalCompletion` and
`(*Reader).ReadProposalCompletion(repo string, issue int) (*ProposalCompletion, string, error)`
to `internal/gitops/reader.go`, and the method to the `GitReader` interface.

- Under `r.mu.RLock()`, take the revision with `revisionLocked()` (an
  unsynced checkout is an error). List
  `platform-gitops/agents-state/<repo>/proposals/` and keep directories whose
  name has the exact prefix `issue-<N>-`. Validate `repo` with the same
  character class as `issueURLPattern`, and reject separators.
- Zero matches returns `(nil, rev, nil)`: read, and nothing recorded. More
  than one match is an error (ambiguous). Lstat `.status.yaml`. A missing
  file returns `(nil, rev, nil)`. A non-regular file or symlink is an error.
  Apply a size cap like `maxHumanInputRequestBytes`.
- Decode into a `yaml.Node`, then extract:
  - `status`, `attempt.id` and `completion.run_id`
  - `completion.authoritative.{outcome, stop_reason, attempt_id, completion_id}`
  - `head_sha` as a tri-state: `HeadSHAPresent bool` and `HeadSHA *string`,
    where present and null leaves `HeadSHA` nil. A plain `*string` field would
    conflate "null" with "absent", and the issue distinguishes them.
- No `completion` or no `authoritative` block returns
  `(&ProposalCompletion{Proposal: dir, Authoritative: false}, rev, nil)`, so
  the caller can say why. Undecodable YAML is an error.

### 2. Decision in `internal/api/handlers_dev_loop.go`

- Add `devLoopOutcomeRestartedAfterFailure = "restarted_after_failure"`. Like
  `restarted_after_abandon`, only the single-issue route produces it.
- Add `StartTime time.Time` to `devLoopStartResult`. `classifyDevLoop` sets it
  from `exec.StartTime` on `already_running` / `already_exists`.
- Add a small dependency bundle, so tests can inject fakes and nil means "not
  configured":

  ```go
  type devLoopFailureEvidence struct {
      Completions interface{ ReadProposalCompletion(repo string, issue int) (*gitops.ProposalCompletion, string, error) }
      Executions  interface{ ListExecutions(ctx context.Context, agent, workflowID string, limit int) ([]agentregistry.AgentExecution, error) }
  }
  ```

  `startDevLoop` gains an `ev devLoopFailureEvidence` parameter. The handler
  builds it from `h.opts.GitReader` and `h.opts.AgentRegistry`, leaving a
  field nil when its source is nil. A typed-nil `*agentregistry.Store` must
  not become a non-nil interface, so check it explicitly. `startDevLoop`
  passes `ev` to `restartIfAbandoned`.
- `restartIfAbandoned` keeps its name and its Completed logic. Its first
  guard becomes:
  - `RunID == ""` returns `existing`.
  - `Status == Failed` returns `restartIfNoCommitFailure(ctx, c, ev, issueURL, workflowID, existing)`.
  - `Status != Completed` returns `existing` (unchanged).

  This way the issue's requested unit tests "on restartIfAbandoned" cover
  both branches.
- `restartIfNoCommitFailure` checks the evidence in this order. The first
  failing check decides.
  1. If `ev.Completions == nil` or `ev.Executions == nil`, return
     `already_exists` with `NotRestarted = "failure evidence sources are not configured"`.
  2. Parse the repo and issue from `issueURL`. Export a helper from
     temporalclient next to `WorkflowIDForIssueURL` that reuses
     `issueURLPattern`.
  3. Call `ReadProposalCompletion`. On error, return `failed` with
     `could not read the implementer completion for failed run <run>: <err>`.
     A nil result returns `already_exists` with "no proposal recorded for the
     issue". `!Authoritative` returns `already_exists` with "no authoritative
     implementer completion recorded". If `authoritative.attempt_id` and
     `attempt.id` are both set and differ, return `already_exists` with
     "completion attempt does not match the proposal attempt".
  4. Call `ListExecutions(ctx, "implementer", workflowID, 1)`, bounded by a
     new `devLoopEvidenceReadTimeout` (5s, a separate budget like
     `devLoopResultReadTimeout`). On error, return `failed`. If no row
     exists, or `row.CreatedAt.Before(existing.StartTime)`, return
     `already_exists` with "no implementer execution recorded for run <run>".
     If `row.ArgoWorkflowName != completion.RunID`, return `already_exists`
     with "completion belongs to implementer run <A>, the failed run's
     implementer was <B>". This last check rejects a stale completion left by
     an earlier run.
  5. If `outcome != "deterministic_failure"` or `stop_reason != "no_commits"`,
     return `already_exists` with "completion <outcome>/<stop_reason> is not a
     no-commit failure". Quote both values with `quoteForAudit`.
  6. If `!HeadSHAPresent`, return `already_exists` with "completion records no
     head_sha". If `HeadSHA != nil`, return `already_exists` with "the
     implementer left head_sha <sha>".
  7. Restart through the existing `RestartAbandonedDevLoopWorkflow`, using
     the same three echo guards as the abandon branch. Success returns
     `{Outcome: restarted_after_failure, RunID: new, PreviousRunID: failed}`
     plus evidence fields for the audit (`EvidenceRef`: implementer Argo run
     and gitops revision).
- Handler `StartDevLoopWorkflow`:
  - Add a `case devLoopOutcomeRestartedAfterFailure`. It mirrors the abandon
    case: 202, `previous_run_id`, an audit message
    `restarted after failed run <prev> (implementer <argo> produced no commits; gitops <rev>; new run <run>)`,
    and a user message saying the previous run's implementer left no commits,
    so a new run re-investigates and needs approval.
  - Update the `already_exists` message to "Only a run abandoned before the
    implement step, or a failed run whose implementer produced no commits, is
    restarted."
  - The `failed` case already records `previous_run_id` when set. Generalise
    its comment.
- `internal/temporalclient/client.go`: update the
  `RestartAbandonedDevLoopWorkflow` doc comment, and the matching comment in
  `interfaces.go`. It is now called right after the caller observed either an
  abandoned run or a proven no-commit failure. No behaviour change. Keeping
  the method name avoids touching every fake in the wave and dev-loop tests.

### 3. Docs

- `internal/openapi/openapi.yaml`: describe the Failed exception, add
  `restarted_after_failure` to the 202 `outcome` enum, and widen the
  `previous_run_id` description.
- `internal/mcp/server.go`: update the `mctl_trigger_issue` description
  (line ~2921) to mention `restarted_after_failure`. No tool is added or
  removed, so the `server_test.go` tool count is unchanged.

Why this way: the issue asks for the completion record to be authoritative,
and the only durable copy is the gitops `.status.yaml`. That file is keyed
by proposal, not by run, so on its own it could be stale. The agent-registry
execution row is written by the same DevLoopWorkflow for that workflow id
after the run started. Matching its `argo_workflow_name` to
`completion.run_id` binds the completion to the failed run without any new
API or schema. Every check that cannot be completed refuses the restart.

## Alternatives

1. **Read the completion from the Temporal failure.** Use
   `GetWorkflow(...).Get` and decode `ApplicationError` details. Dropped for
   now: nothing in the clone shows that mctl-agents attaches the completion
   to the failure, and `DevLoopEnded`'s comment treats a Failed run as having
   no result. This would be the stronger source if mctl-agents guarantees it.
   It is recorded as an open question and could replace step 3 later without
   changing outcomes.
2. **Restart every Failed run, as mctl-agents' CLI does with
   `ALLOW_DUPLICATE_FAILED_ONLY`.** Dropped: the issue requires that a Failed
   run with `head_sha` set, or with an unreadable completion, is not
   restarted. A blanket restart could start a fresh investigate over a pushed
   branch or PR, which is the reason the mctl-api#640 rule exists.
3. **Gitops evidence only, without the agent-registry binding.** Simpler, and
   it works when the registry is not configured. Dropped: the proposal file
   outlives runs, so a completion from an earlier run could license a restart
   of a later run that failed for a different reason. Requiring both sources
   keeps the "provably" in the issue title.

## Platform impact

- Migrations: none. No schema change; this reuses `agent_executions` and
  existing gitops files.
- Backward compatibility: the response shape is unchanged. One new `outcome`
  value, `restarted_after_failure`, appears on 202. Clients that switch on
  `started` are unaffected. Completed, Terminated, TimedOut and the other
  statuses behave as before. A Failed run whose evidence reads cleanly but
  does not qualify still returns 200 `already_exists`. The one visible
  regression risk is a Failed run whose evidence read errors: it now returns
  502 instead of 200 `already_exists`. The issue asks for this, since an
  unreadable completion must be reported as such. When a source is not
  configured, the old 200 is kept.
- Resource impact: one extra local filesystem walk of one proposals
  directory, plus one indexed PostgreSQL query, only on `Failed` closed runs
  of the admin-only start route. Each is bounded by its own 5s timeout.
- Risks and mitigations:
  - *Stale completion.* Mitigated by the agent-registry binding (created_at
    at or after the run start, same Argo run name) and the
    attempt-id consistency check.
  - *Gitops checkout lag.* The completion is not visible yet, so the result
    is `already_exists`, which is safe. The operator retries after refresh.
  - *TOCTOU.* Same class and window as documented on `restartIfAbandoned`.
    `ALLOW_DUPLICATE` cannot be conditioned on which run closed. The comment
    is extended to cover this branch.
  - *Lifecycle-ownership or `we_` left open by a Failed run.* Not visible
    from mctl-api. The owner-run live acceptance on a throwaway test issue
    (not mctl-agents#746) verifies the new run reaches the approval gate and
    can be approved. If it cannot, a
    follow-up goes to mctl-agents.
  - *Approval semantics.* A restart never approves anything. The new run
    re-investigates and parks at the approval gate.

## Open questions

- Is the completion also carried on the Temporal workflow failure (see
  Alternative 1)? Needs confirmation from mctl-agents.
- Should `primary_observed: true` be required in addition to the issue's
  three fields?
- Whether the deployed mctl-api has both `GitReader` and `AgentRegistry`
  configured was not observed: no mctl-api values file was found under
  `$MCTL_GITOPS_ROOT/services`. If either is missing in production, this
  branch reports `already_exists` ("not configured") and the live acceptance
  fails. `mctl_list_agent_executions` working in production suggests the
  registry is configured. The gitops reader backs `mctl_get_service_config`,
  which suggests it is too, but neither was confirmed as a config value.
- Does a Failed DevLoopWorkflow release its lifecycle row and end its `we_`?
  This determines whether the restarted run can be approved without
  `execution_ambiguous`.
