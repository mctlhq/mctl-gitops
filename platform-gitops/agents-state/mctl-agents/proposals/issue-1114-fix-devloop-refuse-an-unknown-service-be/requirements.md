# Refuse an unknown service before any investigator pod runs, skip the fallback for it, and stop blaming quota

## Context

When an investigation is requested for an issue in a repository that is not in
`config/settings.py` `SERVICES` (observed 2026-11-22 for
`https://github.com/mctlhq/mctl-glovo/issues/42`, Argo run
`mctl-agents-investigate-79927b83`), the refusal happens only inside the
investigator pod (`orchestrator/run_issue_investigator.py`,
`if service not in SERVICES: raise SystemExit(...)`). That refusal exits with
code 1, which the `mctl-agents-investigate` ClusterWorkflowTemplate treats like
any transient failure: it runs `investigate-fallback` on the second Claude
account, which fails identically, and `assert-produced` (template
`assert-attempt`) then tells the operator the cause is "most often the Claude
five_hour usage limit / HTTP 429 ... Re-run once quota resets". The real cause
is a deterministic configuration refusal that no re-run can fix.

`orchestrator/run_issue_poller.py` already skips an unknown repo before it
starts anything. The other start paths in this repository
(`orchestrator.temporal.start.start_dev_loop_workflow`, used by the operator
CLI, the directive poller and the dispatcher, and the DevLoop's own
investigate submit through `submit_and_wait`) do not. This proposal makes the
refusal happen before any Argo workflow is created on every path this
repository owns, gives the in-pod refusal a distinct exit code and outcome
(`unknown-service`) so the CWFT can skip the fallback and name the real reason,
and leaves the paths owned by other repositories (mctl-api's direct
`mctl-agents-investigate` operation, the CWFT itself in mctl-gitops) as
explicit companion changes.

## User stories

- AS a platform operator I WANT a DevLoop start on an unregistered repo to be
  refused immediately with the registration instruction SO THAT no pod runs
  and I know what to fix.
- AS a platform operator I WANT a deterministic configuration refusal not to
  consume the fallback account's attempt SO THAT pods and the second account's
  quota are not wasted.
- AS an on-call reader of a failed investigate run I WANT the failure message
  to name the actual cause SO THAT I do not wait for a quota reset that cannot
  help.

## Acceptance criteria (EARS)

- WHEN `start_dev_loop_workflow(issue_url)` is called for an issue whose repo
  is not in `SERVICES` THE SYSTEM SHALL raise `UnknownServiceError` carrying
  the same message text the investigator prints, before connecting to or
  calling Temporal, so no DevLoopWorkflow and no Argo workflow is created.
- WHEN the operator CLI `python -m orchestrator.temporal.cli start <url>` is
  given an unknown-service issue THE SYSTEM SHALL print that message to stderr
  and exit with code 2 without starting a workflow.
- WHEN the `submit_and_wait` activity is asked to submit
  `mctl-agents-investigate` with an `issue_url` whose repo is not in `SERVICES`
  THE SYSTEM SHALL raise a non-retryable `ApplicationError` of type
  `UnknownService` with that message and SHALL NOT POST to mctl-api.
- WHEN `run_issue_investigator` is run for an issue whose repo is not in
  `SERVICES` THE SYSTEM SHALL print the refusal message to stderr and exit with
  the distinct code `EXIT_UNKNOWN_SERVICE` (78), before reading the issue from
  GitHub or invoking any model.
- IF the CWFT primary attempt exits with code 78 THEN THE SYSTEM SHALL record
  the attempt outcome `unknown-service` and SHALL NOT run
  `investigate-fallback` (companion mctl-gitops change).
- IF neither attempt succeeded and the primary outcome is `unknown-service`
  THEN `assert-attempt` SHALL state that the repo is not a registered service,
  name `config/settings.py SERVICES` / `NON_ROTATING_SERVICES`, and state that
  a re-run cannot succeed, and SHALL NOT mention quota (companion mctl-gitops
  change).
- IF neither attempt succeeded and the primary outcome is anything else THEN
  `assert-attempt` SHALL keep today's quota-oriented text unchanged.
- WHILE a repo is in `SERVICES` THE SYSTEM SHALL behave exactly as today on
  every path (no new refusal, same exit codes, fallback still runs on a
  non-78 failure).
- THE SYSTEM SHALL build the refusal message in exactly one function so the
  poller, the start path, the activity and the investigator cannot drift.

## Out of scope

- Deciding whether `mctl-glovo` should be registered in `SERVICES` /
  `NON_ROTATING_SERVICES` (issue item 4; owner decision).
- mctl-api changes: its direct `mctl-agents-investigate` operation (the path
  that actually submitted `mctl-agents-investigate-79927b83`) and its own
  Temporal start of DevLoopWorkflow. A companion mctl-api issue is filed as a
  task here; this repository cannot edit mctl-api.
- Changing the fallback policy for any other failure class.
- Reclassifying other investigator `SystemExit` refusals (bad flags, missing
  execution context) to distinct exit codes.

## Open questions

- mctl-api has no access to the Python `SERVICES` list. Should it refuse by
  reading a published list (for example a generated `config/services.json`
  shipped in the image or mirrored to gitops), or rely on the activity gate in
  this proposal for DevLoop starts and on the CWFT exit-code handling for its
  direct operation? This proposal assumes the latter as the minimum and files
  the mctl-api question as a companion issue.
- The CWFT lives in mctl-gitops
  (`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`),
  not in this repository. The Tier 2 implementer for mctl-agents may not be
  able to open the companion PR there; if not, a human or a separate
  mctl-gitops proposal must carry tasks 6-7.
- Exit code 78 (`EX_CONFIG` from sysexits.h) is assumed free; no other code
  path in `run_issue_investigator.py` uses it today.
