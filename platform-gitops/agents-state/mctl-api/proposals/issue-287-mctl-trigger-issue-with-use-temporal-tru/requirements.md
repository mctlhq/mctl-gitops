# Make the DevLoop start path report whether it actually started anything

## Context

`POST /api/v1/agents/dev-loop/start` (`Handlers.StartDevLoopWorkflow`,
`internal/api/handlers_dev_loop.go`) calls
`temporalclient.Client.StartDevLoopWorkflow`, which deliberately configures
`WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE` plus
`WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING` (`internal/temporalclient/client.go`).
Those two policies make the call idempotent on the deterministic workflow id
`dev-loop-mctlhq-{repo}-{issue}`: a running execution is returned instead of
errored on, and a closed one is not restarted. The handler, however, reports
every one of those outcomes identically — HTTP 202 with
`"message": "DevLoopWorkflow started."` and a `run_id` — so a caller cannot
tell a real start from a no-op that merely handed back the id of an execution
started days ago. Issue #287 observed exactly that on `portfolio#7`: no
`mctl-agents-investigate-*` workflow appeared, no entry showed up in
`mctl_list_recent_agent_runs`, and the operator waited on a run that did not
exist.

The same problem was already solved one route over. `ExecuteRoadmapWave`
(`internal/api/handlers_roadmap_wave.go`, mctl-api#334) calls
`DescribeDevLoop` before `StartDevLoopWorkflow` for each planned item and
reports a per-item `outcome` of `started`, `already_running`, `already_exists`
or `failed`. The single-issue start path never received that treatment. This
proposal brings the single start onto the same discipline, shares the decision
between both handlers so they cannot drift, and adds an explicit
terminate-and-restart flag so an operator can re-investigate an issue without
falling back to `use_temporal=false`.

## User stories

- AS a platform admin calling `mctl_trigger_issue(use_temporal=true)` I WANT the
  response to say whether a DevLoopWorkflow was actually started SO THAT I do
  not wait on an investigate run that was never submitted.
- AS a platform admin I WANT the already-running execution's own `run_id` and
  status in that response SO THAT I can go look at the live execution instead of
  guessing which run the id belongs to.
- AS a platform admin whose DevLoop is parked on a dead branch (implementer
  returned `no-commits`, proposal in `needs-triage`) I WANT an explicit
  restart flag on the same call SO THAT I can re-investigate the issue on the
  Temporal path without hand-picking the legacy `use_temporal=false` workaround.
- AS an operator reading the audit log I WANT a no-op start to be recorded as a
  no-op SO THAT `dev-loop-start` entries are not evidence of runs that never
  happened.
- AS a maintainer I WANT the "is there already an execution for this id"
  decision to live in one function SO THAT the single-start route and the wave
  route cannot disagree about what `already_running` means.

## Acceptance criteria (EARS)

- WHEN `POST /api/v1/agents/dev-loop/start` is called and no execution exists
  for the derived workflow id THE SYSTEM SHALL start a DevLoopWorkflow and
  respond `202` with `started: true`, `outcome: "started"`, `workflow_id` and
  the new `run_id`.
- WHEN the derived workflow id already has a `Running` execution THE SYSTEM
  SHALL NOT report a start, and SHALL respond `200` with `started: false`,
  `outcome: "already_running"`, `status: "Running"`, the existing execution's
  `run_id`, and a message naming that execution and the restart flag.
- WHEN the derived workflow id has a closed execution (`Completed`, `Failed`,
  `Terminated`, `Canceled`, `TimedOut`, `ContinuedAsNew`) THE SYSTEM SHALL
  respond `200` with `started: false`, `outcome: "already_exists"`, that
  `status`, and the closed execution's `run_id`.
- IF the pre-start `DescribeDevLoop` fails with anything other than Temporal's
  NotFound THEN THE SYSTEM SHALL NOT start a workflow and SHALL respond `502`
  with `outcome: "failed"`, because it cannot tell whether an execution already
  exists.
- WHEN `issue_url` is missing or is not a well-formed `https://github.com/mctlhq/{repo}/issues/{n}`
  URL THE SYSTEM SHALL respond `400`, unchanged from today's behaviour
  (`temporalclient.ErrInvalidIssueURL`).
- WHEN the request body carries `restart: true` THE SYSTEM SHALL start a fresh
  execution on the same workflow id, terminating any live execution first, and
  respond `202` with `started: true`, `outcome: "restarted"`, the new `run_id`
  and `terminated_run_id` set to the execution it replaced (empty when there was
  none).
- IF `restart: true` is sent and no execution exists for that id THEN THE SYSTEM
  SHALL start normally and report `outcome: "started"` rather than failing.
- WHILE the Temporal client is not configured (`Options.TemporalClient == nil`)
  THE SYSTEM SHALL respond `503`, and WHILE the caller is not an admin THE
  SYSTEM SHALL respond `403` — both unchanged, via `requireTemporalAdmin`.
- WHEN any start request resolves THE SYSTEM SHALL write exactly one audit entry
  for operation `dev-loop-start` whose parameters carry `outcome` and whose
  `Message` distinguishes a no-op from a start; a `restart: true` request SHALL
  be audited at `operations.RiskHigh` and carry `restart: "true"` plus the
  terminated run id.
- WHILE both `StartDevLoopWorkflow` and `ExecuteRoadmapWave` decide whether to
  start an item THE SYSTEM SHALL use one shared decision function, so the
  outcome vocabulary (`started`, `already_running`, `already_exists`, `failed`)
  is identical on both routes.
- WHEN `mctl_trigger_issue` is invoked with `use_temporal=true` THE SYSTEM SHALL
  forward the optional `restart` argument to `/api/v1/agents/dev-loop/start`,
  and SHALL surface the returned `started`/`outcome` verbatim to the caller.
- IF `restart` is supplied while `use_temporal` is false or absent THEN THE
  SYSTEM SHALL return a tool error stating that `restart` only applies to the
  Temporal path, rather than silently ignoring it (mirroring the
  `approver`-is-not-an-input rejection in `ApproveDevLoopWorkflow`).

## Out of scope

- Ending a DevLoopWorkflow when its proposal reaches a terminal state
  (`needs-triage`, `review-stuck`) — issue #287 item 2. That decision belongs to
  `DevLoopWorkflow` itself in `mctl-agents` (`orchestrator/temporal/workflows/dev_loop.py`);
  mctl-api holds no part of that state machine. Tracked as a cross-repo
  follow-up, see Open questions.
- Reporting *which step* a `Running` execution is on in `mctl_get_dev_loop`.
  That needs a new query handler on the Python worker; `GetDevLoopWorkflow`
  can only expose what `DescribeDevLoop`/`QueryShepherdInLoop` already answer.
- The `mctl_get_workflow_status` gap on `dev-loop-*` ids (the audit entry for
  `dev-loop-start` is found, `auditEntryTenant` yields no team, and
  `operations.WorkflowNamespace` routes the lookup at an Argo namespace that
  never held a Temporal execution). Separate defect in
  `internal/api/handlers_read.go`; this proposal does not touch it beyond
  pointing `dev-loop-start` callers at `mctl_get_dev_loop`.
- Changing the idempotency policies themselves for the non-restart path.
  `REJECT_DUPLICATE` + `USE_EXISTING` stay exactly as they are; this proposal
  only makes their effect legible.
- Any change to the `use_temporal=false` direct-Argo path
  (`/api/v1/operations/mctl-agents-investigate/execute`).

## Open questions

- Should `already_running` be `200` or `409`? A conflict status would be louder,
  but `/dev-loop/start` is documented as idempotent and `ExecuteRoadmapWave`
  returns `200` with per-item outcomes. This proposal picks `200` with
  `started: false` for consistency with the wave route, and keeps `202` reserved
  for "something was actually submitted". Reviewer may prefer `409`.
- Whether `restart: true` should refuse when the existing execution is waiting on
  the human-input gate (`QueryHumanInputState` reports `WAITING_FOR_INPUT`).
  Terminating there discards a sealed request a human may already be answering.
  Proceeding with the simpler reading: restart is explicit, admin-only and
  audited, so it terminates regardless — but the response names the terminated
  run id so the discard is visible. Flagged for the reviewer.
- Whether the mctl-agents-side fix (item 2, ending the loop on a terminal
  proposal state) should land first. This proposal is independently useful and
  does not depend on it; it is filed as a follow-up in `mctlhq/mctl-agents`.
