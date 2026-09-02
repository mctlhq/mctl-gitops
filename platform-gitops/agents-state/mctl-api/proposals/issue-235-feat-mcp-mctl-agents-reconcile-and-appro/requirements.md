# Add MCP tools for mctl-agents-approve and mctl-agents-reconcile, plus a registry-to-MCP parity test

## Context

`internal/operations/registry.go` declares nine `mctl-agents-*` operations,
all of them fully implemented and working server-side through the generic
`POST /api/v1/operations/{name}/execute` path. `internal/mcp/server.go`
exposes seven of the nine as MCP tools (`mctl_trigger_agents_run`,
`mctl_trigger_mentor_only`, `mctl_trigger_single_service`,
`mctl_trigger_incident_responder`, `mctl_trigger_implementer`,
`mctl_trigger_shepherd`, `mctl_trigger_issue`). Two operations —
`mctl-agents-approve` (`registry.go:608`) and `mctl-agents-reconcile`
(`registry.go:640`) — have no MCP tool at all. An MCP client (an operator's
Claude Code session, or an agent) that needs either operation has no
supported path and is pushed to an undocumented `curl` + `gh auth token`
side channel that bypasses the tool schema's parameter validation, enums,
and risk/confirm metadata.

The issue also identifies a systemic gap: nothing asserts that every
registry operation has a corresponding MCP tool, which is exactly how these
two went unnoticed. `server_test.go` already guards per-operation *parameter*
drift (`TestToolDeployService_ExposesEveryOperationParameter`,
`TestToolCreateTenant_ExposesEveryOperationParameter`) but has no equivalent
guard for *operation* drift (a registry entry missing a tool entirely).

## User stories

- AS an operator using an MCP client I WANT a tool that triggers
  `mctl-agents-reconcile` on demand SO THAT I can verify a change to the
  reconcile ClusterWorkflowTemplate without waiting for the next autonomous
  tick (which can be hours away).
- AS an operator using an MCP client I WANT a tool that triggers
  `mctl-agents-approve` SO THAT I can flip a proposal's `.status.yaml` from
  `proposed` to `accepted` atomically through the API instead of hand-editing
  the file and pushing a PR to satisfy `mctl-gitops`'s branch-protection
  ruleset.
- AS a maintainer of `mctl-api` I WANT an automated test that fails when a
  registry operation has no MCP tool SO THAT the next operation added to
  `registry.go` cannot silently ship without MCP coverage the way these two
  did.

## Acceptance criteria (EARS)

- WHEN an MCP client calls a new `mctl_trigger_reconcile` tool THE SYSTEM
  SHALL POST to `/api/v1/operations/mctl-agents-reconcile/execute` with the
  `service` and `dry_run` parameters extracted from the tool arguments,
  mirroring the `extractStringParams` -> `apiPost` shape used by
  `toolTriggerShepherd` (`server.go:2446-2487`).
- WHEN an MCP client calls a new `mctl_trigger_approve` tool THE SYSTEM
  SHALL POST to `/api/v1/operations/mctl-agents-approve/execute` with the
  `service`, `slug`, and `approver` parameters extracted from the tool
  arguments, using the same `extractStringParams` -> `apiPost` shape.
- WHEN `mctl_trigger_reconcile`'s or `mctl_trigger_approve`'s underlying
  `apiPost` call returns an error THE SYSTEM SHALL return an
  `mcplib.NewToolResultError` describing the failure, matching every other
  `toolTrigger*` handler's error-handling convention (e.g.
  `server.go:2481-2483`).
- WHEN both new tools are registered THE SYSTEM SHALL add them to
  `NewMCPServer()`'s "mctl-agents triggers" block (`server.go:150-158`)
  alongside the existing seven, so `mctl_list_recent_agent_runs` and the
  rest of the group stay adjacent for discoverability.
- THE SYSTEM SHALL declare each new tool's `service` and `dry_run` (for
  reconcile) or `service`, `slug`, and `approver` (for approve) parameters
  in its `WithString(...)` schema with the same `Enum` values as the
  matching `operations.Registry` entry (`registry.go:614-616` and
  `registry.go:660-663`), so `TestToolDeployService_ExposesEveryOperationParameter`-style
  drift cannot recur silently for these two tools either.
- THE SYSTEM SHALL word each new tool's description to state Cost/Duration
  the way every sibling `toolTrigger*` description does, plus the
  `mctl-agents-approve` description SHALL clarify the distinction from
  `mctl_approve_dev_loop` (`server.go:2537`, which signals a running
  `DevLoopWorkflow`) so a caller does not use the standalone operation on an
  issue that has a live DevLoop, per the issue's "Related #228" note.
- WHEN the registry-to-MCP parity test runs THE SYSTEM SHALL fail if any
  `operations.Registry` entry with `HandlerOnly: false` has no corresponding
  registered MCP tool, using an explicit opt-out list (not an implicit
  skip) for any future `HandlerOnly: false` operation that is deliberately
  not meant to be MCP-facing.
- IF an `operations.Registry` entry has `HandlerOnly: true` THEN THE SYSTEM
  SHALL exclude it from the parity test's required-tool check, since those
  operations (e.g. `openclaw-skill-save`, `platform-skill-publish`,
  `openclaw-identity-delete`) intentionally bypass the generic
  `/operations/{name}/execute` path and are reachable only through their
  dedicated REST handlers and matching dedicated MCP tools/params, not the
  `extractStringParams` -> `apiPost("/operations/{name}/execute", ...)`
  shape the parity test is checking for.
- WHILE the parity test exists THE SYSTEM SHALL map each covered operation
  name to the MCP tool that submits it (e.g. via a small
  `map[string]string{"mctl-agents-reconcile": "mctl_trigger_reconcile", ...}`
  fixture in the test file) so the check is a real per-operation lookup, not
  just a coarse count comparison that could pass by coincidence.
- WHEN either `toolTriggerReconcile` or `toolTriggerApprove` is deleted from
  `server.go` (verification exercise called out in the issue's Acceptance
  section) THE SYSTEM SHALL fail the parity test, proving the guard actually
  detects the gap it is meant to catch.

## Out of scope

- Changing `mctl-agents-approve` or `mctl-agents-reconcile`'s server-side
  behavior, risk level, or `AdminOnly`/`HandlerOnly` classification in
  `registry.go` — both operations are already correct and working per the
  issue ("Nothing is broken").
- The Temporal `DevLoopWorkflow` approve signal path
  (`mctl_approve_dev_loop`, `/api/v1/agents/dev-loop/{id}/approve`) and
  issue #228's broader ask — this proposal only adds the missing tool for
  the existing GitOps-level `mctl-agents-approve` operation and documents
  the distinction in the tool description; it does not change or extend
  #228's DevLoop-signal tool.
- Any change to `mctl-gitops`'s branch-protection ruleset or the
  `cwft-mctl-agents-reconcile.yaml` / `cwft-mctl-agents-approve.yaml`
  ClusterWorkflowTemplates themselves — those already work, per the issue's
  own successful manual `curl` invocation on 2026-09-02.
- Building a generic/reflective auto-registration mechanism that derives
  MCP tools from `operations.Registry` entries automatically. The issue
  asks for a *test* that catches drift, not a code-generation step; the two
  new tools are added by hand like every existing `toolTrigger*` tool, for
  consistency with the current pattern.
- Adding MCP tools for any operation other than `mctl-agents-approve` and
  `mctl-agents-reconcile`. If the new parity test surfaces other gaps, that
  is either already impossible (every other non-`HandlerOnly` operation
  currently has a tool, per the issue's own table) or is a separate,
  follow-up proposal.

## Open questions

- The issue's proposed parity-test opt-out list names `openclaw-skill-save`
  and `platform-skill-publish` as examples of `HandlerOnly: true` entries.
  Reading `registry.go` shows eight operations with `HandlerOnly: true`
  total (three openclaw-skill/identity save-delete pairs, platform-skill
  enable/disable/publish/deprecate). This proposal treats "opt-out list" and
  "exclude every `HandlerOnly: true` entry" as equivalent, since
  `HandlerOnly` already exists as an explicit, reviewed field for exactly
  this purpose (see the field's doc comment at `registry.go:43-46`) rather
  than inventing a second, separate opt-out list that could drift from the
  first. If a future non-`HandlerOnly` operation needs to be deliberately
  MCP-exempt for some other reason, extending the parity test's fixture map
  with an explicit skip entry (not silently passing) is the intended
  mechanism; none exists today.
- Whether the two new tools should be named `mctl_trigger_reconcile` /
  `mctl_trigger_approve` or something more explicit like
  `mctl_trigger_agents_reconcile` / `mctl_trigger_agents_approve`. The issue
  suggests `toolTriggerReconcile` / `toolTriggerApprove` as Go function
  names (mirroring `toolTriggerShepherd`) without specifying the MCP tool
  name string. This proposal uses `mctl_trigger_reconcile` and
  `mctl_trigger_approve`, matching the existing short-form pattern
  (`mctl_trigger_shepherd`, not `mctl_trigger_agents_shepherd`) used by
  every sibling tool already in the "mctl-agents triggers" block.
