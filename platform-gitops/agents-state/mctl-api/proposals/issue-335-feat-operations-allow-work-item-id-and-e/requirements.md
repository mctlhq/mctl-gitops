# Accept optional work_item_id and execution_id on mctl-agents-investigate

## Context

`mctlhq/mctl-agents#267` teaches the issue-investigator to resume from a
canonical `WorkItem` instead of restarting from the issue alone. To do that the
caller has to hand the investigator two correlation identifiers — the work item
it belongs to and the execution it is resuming — when it submits the operation.
Today the mctl-api operation registry declares exactly one parameter for
`mctl-agents-investigate` (`issue_url`, in `internal/operations/registry.go`),
so those two identifiers never survive the generic execute path: they are
silently stripped by `Registry.StripUndeclared` before
`operations.Executor.Submit` builds the Argo workflow arguments
(`internal/api/handlers_write.go`).

This proposal is the mctl-api half of the prerequisite. It adds the two
identifiers to the operation definition as optional, un-defaulted,
pass-through parameters. It is inert on its own: nothing in mctl-api reads the
values, and the ClusterWorkflowTemplate that will consume them is
`mctlhq/mctl-gitops#1279`. Landing it first is what lets the CWFT and the
agent-side resume logic land without a coordinated three-repo release.

## User stories

- AS the mctl-agents orchestration I WANT to submit
  `mctl-agents-investigate` with `work_item_id` and `execution_id` SO THAT the
  investigator run can be correlated to the work item it resumes instead of
  being an anonymous re-run.
- AS a platform admin I WANT the two identifiers to stay optional SO THAT every
  existing caller (the MCP tool `mctl_trigger_issue`, the Temporal DevLoop
  path, a manual `curl`) keeps working unchanged.
- AS a platform operator I WANT undeclared request fields to keep being
  discarded before Argo SO THAT the parameter-injection hardening from
  `gitops#997` is not weakened by this change.

## Acceptance criteria (EARS)

- WHEN a caller POSTs `/api/v1/operations/mctl-agents-investigate/execute` with
  `issue_url`, `work_item_id` and `execution_id` THE SYSTEM SHALL accept the
  request (HTTP 202) and forward all three values unchanged as Argo workflow
  parameters.
- WHEN a caller POSTs the same endpoint with only `issue_url` THE SYSTEM SHALL
  behave exactly as it does today: accepted, submitted to the
  `mctl-agents-investigate` ClusterWorkflowTemplate in the `argo-workflows`
  namespace, with no invented value for either new parameter.
- WHEN a request body carries a key that the operation does not declare THE
  SYSTEM SHALL keep dropping it before submission, so it never reaches Argo,
  and SHALL log it at warn level — the behaviour
  `TestExecuteOperation_UndeclaredParamNeverReachesArgo` pins today.
- IF `work_item_id` or `execution_id` is present but not a plausible
  identifier (outside `^[A-Za-z0-9_.-]{1,128}$`) THEN THE SYSTEM SHALL reject
  the request with HTTP 400 and a `validationErrors` entry naming the
  parameter.
- WHILE either parameter is absent or empty THE SYSTEM SHALL apply no pattern
  check and no substituted value to it — `Registry.ValidateInput` skips empty
  values and the `ParameterDef` declares no `Default`.
- WHEN the operation is submitted THE SYSTEM SHALL keep its existing gating
  unchanged: `AdminOnly` (admin group membership required), `RiskLow`,
  namespace `argo-workflows`, workflow template `mctl-agents-investigate`.

## Out of scope

- Any CWFT change that reads the two values — that is
  `mctlhq/mctl-gitops#1279`.
- Any investigator behaviour change (resume semantics, context snapshots) —
  that is `mctlhq/mctl-agents#267`.
- Implementing `internal/workitems`, the `WorkItem` store, or the
  `/api/v1/work-items` routes described in `docs/work-context-contract.md`.
  Nothing here validates that the supplied IDs refer to a real work item;
  they are opaque correlation strings on this hop.
- Exposing the two identifiers on the MCP tool `mctl_trigger_issue`
  (`internal/mcp/server.go`) or on the Temporal dev-loop start path
  (`internal/api/handlers_dev_loop.go`). The consumer in `#267` submits the
  REST operation machine-to-machine.
- Changing `StripUndeclared` from "drop" to "reject with 400". That tightening
  is discussed in the comment at `internal/api/handlers_write.go:78` and is a
  separate decision with its own blast radius.

## Open questions

- **Which namespace do the IDs come from?** `docs/work-context-contract.md`
  defines `wi_<uuid>` for `WorkItem` and `we_<uuid>` for `WorkItemExecution`,
  but that package does not exist in this repo yet, and `execution_id` could
  equally be relayed as an engine reference (e.g.
  `dev-loop-mctlhq-mctl-api-227`). Proceeding with a deliberately loose
  charset pattern that admits both rather than pinning the `wi_`/`we_`
  prefixes; if `#267` settles on the prefixed form, tightening later is a
  one-line change.
- **Empty-string forwarding.** `Registry.ApplyDefaults` writes
  `result[p.Name] = p.Default` for every declared-but-absent parameter, so
  after this change every investigate submission carries
  `work_item_id: ""` and `execution_id: ""` as Argo arguments. This already
  happens for `approver` on `mctl-agents-approve`. The CWFT in `#1279` must
  therefore treat the empty string as "absent" rather than relying on its own
  Argo-side default winning. Recorded here so the gitops side is not surprised.
- **Should the MCP tool follow?** `toolTriggerIssue` forwards every string
  argument it receives, so exposing the two identifiers there is a two-line
  follow-up. Left out because no human operator should be typing raw
  correlation IDs; revisit if `#267` wants a manual resume path.
