# Make the Temporal DevLoop the default for mctl_trigger_issue, and the legacy direct-Argo path explicit

## Context

`mctl_trigger_issue` today has two mechanisms behind one name. Omitting
`use_temporal` submits the legacy direct-Argo investigate
ClusterWorkflowTemplate (`internal/mcp/server.go:3032-3046`, "Defaults to false
… until that slice is proven in production"), which produces a proposal at
`status=proposed` with no durable execution attached: approval becomes a
separate `.status.yaml` mutation, the implementer a separate trigger, and the
PR shepherd is owned by no per-issue execution. Passing `use_temporal=true`
routes through `POST /api/v1/agents/dev-loop/start`
(`internal/api/handlers_dev_loop.go:69-122`), which starts the canonical
`DevLoopWorkflow` — one durable execution per issue, `dev-loop-{owner}-{repo}-{issue}`,
investigate → approve signal → implement → shepherd. The Temporal path has
been proven in production (mctl-agents#461 / #490) but the default was never
flipped, so on 2026-09-26 eight issues "run through DevLoop" with a plain
`mctl_trigger_issue(issue_url)` have no execution at all: `mctl_get_dev_loop`
answers `workflow not found` for every one.

Flipping the default alone is not safe. `temporalclient.StartDevLoopWorkflow`
(`internal/temporalclient/client.go:157-172`) starts with
`WORKFLOW_ID_REUSE_POLICY_REJECT_DUPLICATE` +
`WORKFLOW_ID_CONFLICT_POLICY_USE_EXISTING`, so a re-trigger on an issue whose
deterministic id already exists attaches to that run — and the handler still
answers `202 {"message": "DevLoopWorkflow started"}` (mctl-api#287). Making
that path the default without fixing the report would replace a visible legacy
path with an invisible no-op. The correct vocabulary already exists in this
repo: the governed epic-wave executor reports `started` / `already_running` /
`already_exists` / `failed` per item (`internal/api/handlers_roadmap_wave.go:70-75,
333-380`); the single-issue start must speak the same language.

## User stories

- AS a platform operator I WANT `mctl_trigger_issue(issue_url)` with no further
  arguments to put the issue on a durable DevLoopWorkflow SO THAT approval,
  implementation and shepherding are owned by one resumable execution instead
  of three disconnected triggers.
- AS a platform operator I WANT the response to name the mode and the exact
  execution it refers to SO THAT I can tell "a loop is now driving this issue"
  from "an Argo run was submitted and nothing owns the issue".
- AS a platform operator I WANT a re-trigger on an issue that already has a
  live loop to say it attached, never "started" SO THAT I do not believe work
  began that did not (mctl-api#287).
- AS a platform operator who must fall back to the pre-Temporal mechanism I
  WANT to request it explicitly SO THAT the legacy path can never be reached by
  omission.
- AS an agent or human reading the tool descriptions I WANT the Temporal path
  described as canonical in `mctl_trigger_issue`, `mctl_trigger_approve` and
  `mctl_approve_dev_loop` SO THAT the approval path I pick matches the
  mechanism that actually ran.

## Acceptance criteria (EARS)

Mode selection

- WHEN `mctl_trigger_issue` is called with `issue_url` and no `mode` and no
  `use_temporal` THE SYSTEM SHALL take the Temporal DevLoop path
  (`POST /api/v1/agents/dev-loop/start`) and SHALL NOT submit the
  `mctl-agents-investigate` operation.
- WHEN `mctl_trigger_issue` is called with `mode="legacy-direct"` THE SYSTEM
  SHALL submit `POST /api/v1/operations/mctl-agents-investigate/execute` and
  SHALL NOT start a DevLoopWorkflow.
- WHEN `mctl_trigger_issue` is called with `mode="devloop"` THE SYSTEM SHALL
  take the Temporal DevLoop path.
- WHEN `mctl_trigger_issue` is called with the deprecated `use_temporal=true`
  and no `mode` THE SYSTEM SHALL take the Temporal DevLoop path.
- WHEN `mctl_trigger_issue` is called with the deprecated `use_temporal=false`
  and no `mode` THE SYSTEM SHALL treat that explicit false as
  `mode="legacy-direct"` and SHALL state in its response that `use_temporal` is
  deprecated in favour of `mode`.
- IF both `mode` and `use_temporal` are supplied and disagree THEN THE SYSTEM
  SHALL refuse the call with an error naming both values and SHALL start
  nothing.
- IF `mode` is supplied with a value other than `devloop` or `legacy-direct`
  THEN THE SYSTEM SHALL refuse the call and SHALL start nothing.

Honest reporting of what ran (mctl-api#287)

- WHEN the DevLoop path starts a new execution THE SYSTEM SHALL respond HTTP 202
  with `mode="devloop"`, `outcome="started"`, `workflow_id` and `run_id`.
- IF the deterministic `dev-loop-*` id already has a Running execution THEN THE
  SYSTEM SHALL respond HTTP 200 with `outcome="already_running"`,
  `status="Running"` and that `workflow_id`, SHALL NOT use the word "started"
  in its message, and SHALL NOT start a second execution.
- IF the deterministic id has a closed execution (`Completed`, `Failed`,
  `Canceled`, `Terminated`, `TimedOut`, `ContinuedAsNew`) THEN THE SYSTEM SHALL
  respond HTTP 200 with `outcome="already_exists"` and that status, and SHALL
  NOT restart it.
- IF an execution for the id exists but its status cannot be read THEN THE
  SYSTEM SHALL respond HTTP 502 stating that nothing was started, and SHALL NOT
  report an outcome it did not determine.
- WHEN the legacy path runs THE SYSTEM SHALL report `mode="legacy-direct"`
  together with the `workflow_name` of the submitted Argo run.
- WHILE any DevLoop start is performed THE SYSTEM SHALL record `mode` and
  `outcome` in the `dev-loop-start` audit entry, and SHALL leave
  `WorkflowName` empty on a failed start (the convention asserted by
  `TestStartDevLoopWorkflow_TemporalFailureIs502`).
- WHEN a wave item and a single-issue trigger name the same issue THE SYSTEM
  SHALL report the same outcome vocabulary (`started`, `already_running`,
  `already_exists`, `failed`) for both.

Degraded configuration

- IF the default DevLoop path is taken while no Temporal client is configured
  (`TEMPORAL_ADDRESS` unset; `cmd/api/main.go:584`) THEN THE SYSTEM SHALL fail
  with HTTP 503 and an error that names `mode="legacy-direct"` as the explicit
  fallback, and SHALL NOT silently submit the legacy path.
- IF `issue_url` is not a well-formed `https://github.com/mctlhq/<repo>/issues/<n>`
  URL THEN THE SYSTEM SHALL respond HTTP 400 and SHALL NOT contact Temporal.

Documentation of the canonical path

- WHEN an operator reads the description of `mctl_trigger_issue`,
  `mctl_trigger_approve`, `mctl_approve_dev_loop` or `mctl_get_dev_loop` THE
  SYSTEM SHALL describe the Temporal DevLoop as the canonical lifecycle and the
  direct-Argo/`.status.yaml` mechanism as the legacy fallback, and SHALL NOT
  refer to the Temporal path as opt-in or unproven.
- WHEN the OpenAPI document describes `POST /api/v1/agents/dev-loop/start`
  (`internal/openapi/openapi.yaml:2258`) THE SYSTEM SHALL document the 200
  attach responses and the `mode`/`outcome`/`status` fields alongside the 202.

## Out of scope

- Removing `use_temporal` or the legacy `mctl-agents-investigate` operation.
  Both stay; only the default and the wording change.
- Changing the DevLoopWorkflow definition, its activities or the shepherd, all
  of which live in `mctlhq/mctl-agents` (`orchestrator/temporal/`).
- mctl-agents#289 — making the investigator's proposal comment state the path
  it ran on. The comment text is written by the investigator in mctl-agents;
  this proposal only makes mctl-api's answer unambiguous enough for it to be
  quoted. A follow-up issue in that repo is the deliverable here.
- The `agents:intake` label poller (`orchestrator/run_issue_poller.py`), which
  already starts DevLoopWorkflows.
- Retiring `mctl-agents-approve`, or making the implementer enforce
  `control.requires_human_approval` (the remaining half of gitops#986).
- FinOps correlation itself (mctlhq/.github#50); this proposal only removes the
  cause of missing Temporal ids.

## Open questions

- The issue's "Preferred" option asks for a **required** `mode`, while its
  first acceptance criterion requires a call **without** an explicit mode to
  start a DevLoop. A required parameter cannot satisfy both. This proposal
  takes an optional `mode` defaulting to `devloop`: omission can no longer
  reach the legacy path, which is the stated goal, and no existing caller
  breaks. If reviewers want `mode` strictly required, that is a follow-up that
  also has to update every caller and the MCP schema test.
- Whether an explicit `use_temporal=false` should keep working as an alias for
  `mode="legacy-direct"` (assumed yes, with a deprecation note in the response)
  or be refused outright to force migration.
- Whether `mctl_trigger_issue`'s idempotent hint should flip to true now that
  the default path attaches rather than duplicates. Assumed no: the legacy
  branch still submits a fresh Argo run per call, and the hint describes the
  tool, not one branch.
- Whether an `already_running` result should also return the existing `run_id`.
  Assumed yes when Temporal reports it, because the response is supposed to
  name the execution it refers to.
