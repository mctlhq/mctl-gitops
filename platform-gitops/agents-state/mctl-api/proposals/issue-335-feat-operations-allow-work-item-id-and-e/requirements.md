# Allow work_item_id and execution_id on mctl-agents-investigate

## Context

`mctlhq/mctl-agents#267` teaches the issue-investigator to resume from a
canonical `WorkItem` instead of starting cold from an issue URL. To do that,
the caller must hand the investigator two correlation identifiers — the work
item it belongs to and the execution attempt it is running as. Those values
reach the investigator as Argo workflow parameters on the
`mctl-agents-investigate` ClusterWorkflowTemplate, and mctl-api is the front
door that submits that template.

Today mctl-api's operation registry declares exactly one parameter for
`mctl-agents-investigate` — `issue_url`
(`internal/operations/registry.go:641-652`). The generic execute path
(`internal/api/handlers_write.go:83`) calls `Registry.StripUndeclared`, which
silently drops every key the operation does not declare before RBAC, before
defaults, and before Argo. So a submit carrying `work_item_id` /
`execution_id` today is not rejected with a clear error: the two identifiers
are quietly discarded and the workflow runs without them, which is worse than
a 400. This proposal is the mctl-api half of the prerequisite; the CWFT half
that consumes the values is `mctlhq/mctl-gitops#1279`.

## User stories

- AS the mctl-agents dev-workflow control plane I WANT to submit
  `mctl-agents-investigate` with `work_item_id` and `execution_id` SO THAT the
  investigator can resume from a canonical `WorkItem` rather than re-deriving
  its context from the issue alone.
- AS a platform admin driving the investigator by hand or through
  `mctl_trigger_issue` I WANT the operation to behave exactly as it does today
  when I omit the two identifiers SO THAT the existing issue-driven entry point
  is unaffected.
- AS a platform operator I WANT any parameter outside the declared set to stay
  unaccepted SO THAT the `StripUndeclared` guarantee from gitops#997 (no
  caller-settable undeclared workflow parameter) is not weakened by this change.

## Acceptance criteria (EARS)

- WHEN a client POSTs `/api/v1/operations/mctl-agents-investigate/execute` with
  `issue_url`, `work_item_id` and `execution_id` THE SYSTEM SHALL accept the
  request and forward all three values unchanged as Argo workflow parameters on
  the submitted `mctl-agents-investigate` Workflow.
- WHEN a client POSTs the same endpoint with only `issue_url` THE SYSTEM SHALL
  behave exactly as it does today: the request is accepted, `issue_url` is
  forwarded, and no invented value for `work_item_id` or `execution_id` is
  produced (both are filled by `ApplyDefaults` with the empty string, which is
  the existing behaviour for every optional parameter in the registry).
- WHEN a client supplies a parameter that the operation does not declare (for
  example `config_patch`) THE SYSTEM SHALL drop it in
  `Registry.StripUndeclared` and log the drop, exactly as before this change.
- IF `work_item_id` or `execution_id` is supplied with a value that does not
  match the declared identifier pattern THEN THE SYSTEM SHALL return HTTP 400
  with a `validationErrors` entry naming that parameter, and SHALL NOT submit a
  Workflow.
- WHILE `work_item_id` and `execution_id` are absent from the request body THE
  SYSTEM SHALL keep `issue_url` required, so an investigate submit with neither
  an issue URL nor resume identifiers is still rejected with 400.
- WHILE the operation remains `AdminOnly` and `RiskLow` THE SYSTEM SHALL keep
  enforcing admin group membership on this path; adding the two parameters
  SHALL NOT change the operation's risk level, `WorkflowTemplate`,
  `ModifiesPaths`, or namespace routing in
  `operations.WorkflowNamespace`.
- WHEN `GET /api/v1/operations` (or `GET /api/v1/operations/{name}`) is served
  THE SYSTEM SHALL list `work_item_id` and `execution_id` as optional
  parameters of `mctl-agents-investigate`, so the parameter contract is
  discoverable by the callers that must construct the submit.

## Out of scope

- Reading, minting, validating or persisting `WorkItem` / `WorkItemExecution`
  rows. `internal/workitems` does not exist yet (see
  `docs/work-context-contract.md`, "Implementation order"); this proposal adds
  no store, no route, no lifecycle, and deliberately does not check that a
  supplied `work_item_id` refers to anything real.
- The CWFT side: declaring the two parameters on the
  `mctl-agents-investigate` ClusterWorkflowTemplate and threading them into the
  investigator container is `mctlhq/mctl-gitops#1279`.
- The investigator's own resume behaviour (`mctlhq/mctl-agents#267`).
- The Temporal path. `POST /api/v1/agents/dev-loop/start`
  (`internal/api/handlers_dev_loop.go:60`) takes only `issue_url`; extending
  `DevLoopStartRequest` and `temporalclient.DevLoopInput` to carry resume
  identifiers is a separate change.
- Exposing the two parameters on the `mctl_trigger_issue` MCP tool
  (`internal/mcp/server.go:2995`). The consumer in mctl-agents#267 submits over
  REST; adding MCP arguments can follow once the CWFT actually reads the values.

## Open questions

- Which resource does `execution_id` name? `docs/work-context-contract.md`
  defines `WorkItemExecution` ids with a `we_` prefix and pairs them with a
  work item in the route
  `GET|POST /api/v1/work-items/{id}/executions/{execution_id}/snapshots`, so
  this proposal reads `execution_id` as a `we_...` identifier, not an Argo or
  Temporal execution reference. Proceeding on that reading; the chosen
  validation pattern is deliberately prefix-agnostic so either reading still
  validates.
- How strictly should the two ids be validated? A strict
  `^wi_<uuid>$` / `^we_<uuid>$` pattern would reject any id shape mctl-agents
  later mints, reintroducing the exact "rejected before it reaches Argo"
  failure this issue removes. This proposal therefore validates shape only
  (a bounded safe character class) and lets the ID scheme live in
  `docs/work-context-contract.md`. Flagged for the reviewer: if mctl-agents#267
  has already frozen the `wi_`/`we_` prefixes, tightening the pattern is a
  one-line change.
- Should the two identifiers be required together (supplying one without the
  other)? The issue says both stay optional with no invented default, so this
  proposal enforces no cross-field rule — `Registry.ValidateInput` has no
  mechanism for one, and inventing one here would be scope the issue did not
  ask for. Recorded rather than blocked.
