# Design: issue-1114-fix-devloop-refuse-an-unknown-service-be

## Current state

- `config/settings.py` defines `SERVICES` (line 93), `NON_ROTATING_SERVICES`
  (line 156) and `ROTATING_SERVICES`. It has no helper for "is this a known
  service" and no shared refusal message.
- `orchestrator/run_issue_investigator.py` (around line 3525, inside
  `investigate()`): after `gh_issue_view(issue_url)` it does
  `if service not in SERVICES: raise SystemExit(f"Repo '{service}' is not a known service. Add it to config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues. Known: ...")`.
  A `SystemExit` with a string exits with code 1, indistinguishable from any
  other failure. It runs after the GitHub read. Covered by
  `tests/test_run_issue_investigator.py::test_investigate_rejects_unknown_service`
  (asserts only `SystemExit`).
- `orchestrator/run_issue_poller.py` (around lines 360-380) already checks
  `known_service` and skips with `WARN: <repo> is not a known service ... label kept.`
  before calling `start_dev_loop_workflow`.
- `orchestrator/temporal/start.py::start_dev_loop_workflow` starts or attaches
  to `dev-loop-<owner>-<repo>-<n>` with no service check.
  `dispatch_start_operation` (dispatcher Update-with-Start) and
  `restart_if_restartable` likewise do not check. `orchestrator/temporal/cli.py::start`
  validates only the URL shape (`parse_issue_url`, exit 2 on error).
- `orchestrator/run_issue_directive_poller.py` only scans repos in `SERVICES`
  for `@MCTL investigate`, so it cannot reach an unknown repo today.
- `orchestrator/temporal/workflows/dev_loop.py`: every CWFT submit goes through
  `_run_cwft` (line 1324), which schedules the `submit_and_wait` activity
  (`orchestrator/temporal/activities/argo.py`, `SubmitAndWaitInput(operation, params)`);
  the investigate submit is `_run_cwft("mctl-agents-investigate", investigate_params)`
  (line 3943) and its continuation (line 4106). `submit_and_wait` POSTs to
  mctl-api without validating the target repo.
- `orchestrator/temporal/issue_ref.py::parse_issue_url` is the single
  temporalio-free parser of `https://github.com/mctlhq/<repo>/issues/<n>`.
- The CWFT `mctl-agents-investigate` is NOT in this repository; it is
  `mctl-gitops/platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`.
  Its `investigate-issue` steps: `investigate` (continueOn failed/error),
  `investigate-fallback` with `when: "{{steps.investigate.status}} != Succeeded"`,
  `commit`, then `assert-produced` (template `assert-attempt`, params `primary`
  and `fallback` statuses) whose failure text always says "Most often the
  Claude five_hour usage limit / HTTP 429 on both accounts ... Re-run once
  quota resets." The `run-investigator` wrapper captures the investigator's
  exit code (`RC=$?`, `echo "investigator exited ${RC}"`) and re-raises it
  after collecting proposal files (`sys.exit(rc)`); `entrypoint.sh` uses
  `exec "$@"`, so the code reaches the container exit.

Deployed state checked:

- `mctl_get_workflow_status(mctl-agents-investigate-79927b83)`: audit record
  shows `operation: mctl-agents-investigate`, `userId: mashkovd`,
  `userAgent: Go-http-client/1.1`, parameters `execution_id: ""`,
  `work_item_id: ""`, `issue_url: https://github.com/mctlhq/mctl-glovo/issues/42`.
  Nodes: `investigate` Failed (exit code 1, 27 s), `investigate-fallback`
  Failed (exit code 1, 25 s), `commit` Succeeded, `assert-produced` Failed
  (exit code 1). So this particular run was submitted by mctl-api's direct
  investigate operation, not by a DevLoopWorkflow's `_run_cwft`.
- `mctl_get_dev_loop(dev-loop-mctlhq-mctl-glovo-42)`: refused ("outside the
  investigate scope of this agent run"). Whether that DevLoop exists, and
  whether it submitted its own investigate, could not be observed (see Open
  questions).
- Gitops path read: `argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`
  (steps, `run-investigator` wrapper, `assert-attempt` text quoted above).

## Proposed solution

### 1. One shared refusal (config/settings.py)

Add to `config/settings.py` (pure data module, already imported by the poller,
the investigator and the directive poller; no new dependency):

- `EXIT_UNKNOWN_SERVICE = 78` (sysexits `EX_CONFIG`).
- `UNKNOWN_SERVICE_OUTCOME = "unknown-service"`.
- `is_known_service(repo: str) -> bool`.
- `unknown_service_message(repo: str) -> str` returning today's exact text
  (`Repo '<repo>' is not a known service. Add it to config/settings.py SERVICES (NON_ROTATING_SERVICES if it has no agents/<svc>/ scaffold) before investigating its issues. Known: ...`).

`run_issue_poller.py` keeps its WARN line but uses `is_known_service`.

### 2. Investigator: distinct exit code, before the GitHub read

In `orchestrator/run_issue_investigator.py` add
`class UnknownServiceExit(SystemExit)` whose `code` is `EXIT_UNKNOWN_SERVICE`
and which prints `unknown_service_message(repo)` to stderr when raised (the
message is printed explicitly because `SystemExit(78)` would not print it).
Raise it in `investigate()` from the repo derived by `parse_issue_url(issue_url)`
before `gh_issue_view`, keeping the post-read check as a second guard (same
exception). Subclassing `SystemExit` keeps the existing test and every caller
that catches `SystemExit` unchanged.

### 3. Start path: refuse before Temporal

In `orchestrator/temporal/start.py` add `class UnknownServiceError(ValueError)`
and a `_require_known_service(issue_url)` call at the top of
`start_dev_loop_workflow`, `restart_if_restartable` and
`dispatch_start_operation`, before any `connect()` or client call.
`orchestrator/temporal/cli.py::start` catches it next to the existing
`ValueError` handling, prints the message and exits 2. The intake poller
already filters, so its behaviour is unchanged; the dispatcher's call site
must turn the error into its existing non-retryable request refusal (the
`refuse(...)` helper pattern in `dev_loop.py` around line 2973 / the
dispatcher's error mapping) rather than crash the dispatch tick.

### 4. Activity gate: refuse before the Argo submit

In `orchestrator/temporal/activities/argo.py::_submit_and_wait`, before the
resume-or-submit branch, when `input.operation == "mctl-agents-investigate"`
and `parse_issue_url(input.params["issue_url"]).repo` is not known, raise
`ApplicationError(unknown_service_message(repo), type="UnknownService", non_retryable=True)`.
Only when no `workflow_name` heartbeat exists: a resumed attempt of an
already-submitted run must keep polling it. This covers every DevLoopWorkflow
regardless of who started it (including mctl-api's Temporal start, which this
repository cannot change). It lives in the activity, not the workflow code, so
no `workflow.patched` marker is needed and replays of existing histories are
unaffected (activity results are recorded). The DevLoop's existing exception
path in `DevLoopWorkflow.run` ends its canonical execution `Failed`.

### 5. CWFT (companion mctl-gitops change)

In `cwft-mctl-agents-investigate.yaml`:

- `run-investigator` wrapper: after `RC=$?`, write `/tmp/attempt-outcome`
  containing `unknown-service` when `RC` is 78, otherwise an empty file; add an
  output parameter `outcome` (`valueFrom.path: /tmp/attempt-outcome`,
  `default: ""`). The `default` makes the reference resolve even when the pod
  errored before the script ran.
- `investigate-fallback`: `when: "{{steps.investigate.status}} != Succeeded && '{{steps.investigate.outputs.parameters.outcome}}' != 'unknown-service'"`.
  The primary always runs, so referencing its output never hits a skipped step.
- `assert-produced`: pass `primary-outcome: "{{steps.investigate.outputs.parameters.outcome}}"`.
  `assert-attempt` branches: for `unknown-service` print "The repository is not
  a registered service (config/settings.py SERVICES / NON_ROTATING_SERVICES).
  A re-run cannot succeed until it is registered; see the investigate step log
  for the exact message." and exit 1; otherwise print today's text unchanged.

Exit code 78 is the contract between the two repositories; it is pinned by a
test in this repository (T2) and documented next to `EXIT_UNKNOWN_SERVICE`.

### 6. Companion mctl-api issue

File an issue in mctlhq/mctl-api asking its `mctl-agents-investigate` operation
and its DevLoop start to refuse unknown repos before submit, and recording the
open question of how mctl-api learns the list.

## Alternatives

- **Check inside `DevLoopWorkflow._run_loop` before `_run_cwft`.** Rejected:
  a new early return changes command sequences for in-flight histories and
  would need a `workflow.patched` gate; the activity gate gives the same
  "no Argo workflow" result with no determinism risk.
- **Use `{{steps.investigate.exitCode}}` directly in the CWFT `when`.**
  Rejected as the primary mechanism: for a step that errors without a
  container exit code the reference may not resolve and fail the `when`
  evaluation. An output parameter with a default is robust; the exit code
  stays the in-pod signal that feeds it.
- **Investigator exits 0 with an "unknown-service" marker.** Rejected: the run
  must still report Failed (no proposal was produced), and a zero exit would
  mask that in every consumer that reads the step status.
- **Only fix the start path.** Rejected: the observed run came from mctl-api's
  direct operation, which never touches `start_dev_loop_workflow`; without the
  exit code and CWFT changes the fallback and the quota hint would remain.

## Platform impact

- No migrations, no schema or Temporal history changes. No new dependency.
- Backward compatible for every registered service: all new branches are taken
  only when the repo is unknown.
- Exit code change 1 -> 78 for the unknown-service refusal only. Until the
  companion CWFT change lands, 78 is still "not Succeeded", so the current CWFT
  behaves exactly as today (fallback runs, quota text). Deploy order does not
  matter; benefit is complete once both are deployed.
- Resource impact: one fewer pod per such run (fallback skipped), and zero pods
  for DevLoop-submitted investigates of unknown repos.
- Risk: an intentionally unregistered repo previously "worked" through the
  DevLoop until the pod refused; now it fails earlier with the same message.
  No behaviour that ever succeeded is removed.
- Risk: the activity gate reads `SERVICES` from the worker image, which can lag
  the agent image. Mitigation: both are built from this repository; a service
  added to `SERVICES` is honoured by whichever image ships it, and the pod-side
  check remains authoritative.

## Open questions

- `dev-loop-mctlhq-mctl-glovo-42` could not be read (tool refused as out of
  scope), so whether the DevLoop itself also submitted an investigate is
  unobserved. The activity gate covers that path either way.
- How mctl-api should learn the service list (companion issue, task 8).
- Whether the mctl-agents implementer can open the mctl-gitops CWFT PR
  (tasks 6-7) or a human must carry it.
