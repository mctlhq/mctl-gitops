# Add portfolio to the DevLoop service enums (all eight sites)

## Context

`mctlhq/portfolio` is being registered as a DevLoop service in mctl-agents
(`config/settings.py` SERVICES). mctl-api holds an independent, hard-coded copy of
that service list in two places: the `service` parameter `Enum` of four operations in
`internal/operations/registry.go` (`mctl-agents-implement`, `mctl-agents-shepherd`,
`mctl-agents-approve`, `mctl-agents-reconcile`) and the four matching MCP tool schemas
in `internal/mcp/server.go` (`mctl_trigger_implementer`, `mctl_trigger_shepherd`,
`mctl_trigger_approve`, `mctl_trigger_reconcile`). Every list today ends
`..., "mctl-telegram", "mctl-design", "mctl-pairdesk", "mctl-academy"`.

Without a matching entry here, a DevLoop run for `portfolio` dies at approval:
`DevLoopWorkflow`'s approve activity calls
`POST /api/v1/operations/mctl-agents-approve/execute`, and
`Registry.ValidateInput` (`internal/operations/registry.go:109`) rejects any value not
in `p.Enum` with `service: must be one of ...` — a 400 that ends the workflow in
`Failed` with the proposal stuck at `proposed`. This is the same failure mode already
recorded in `internal/operations/registry_test.go:19-25` (mctl-design, caught live
2026-08-05) and documented in #274 for `seerrsense`. This proposal is the minimal,
targeted fix for `portfolio` only; #274 remains open for the structural fix of deriving
the list from a single source.

## User stories

- AS the mctl-agents DevLoop orchestrator I WANT `mctl-agents-approve` to accept
  `service=portfolio` SO THAT a `portfolio` proposal can be approved instead of failing
  parameter validation and stranding the workflow.
- AS a platform admin I WANT `mctl_trigger_implementer`, `mctl_trigger_shepherd`,
  `mctl_trigger_reconcile` and `mctl_trigger_approve` to offer `portfolio` in their
  `service` enum SO THAT I can filter or drive `portfolio` work from an MCP client.
- AS a maintainer I WANT an automated guard comparing the registry enums with the MCP
  enums SO THAT the eight sites cannot drift apart again silently.

## Acceptance criteria (EARS)

- WHEN `Registry.ValidateInput` is called for `mctl-agents-approve` with
  `service: "portfolio"` and a valid `slug` THE SYSTEM SHALL return no validation
  errors.
- WHEN `Registry.ValidateInput` is called for `mctl-agents-implement`,
  `mctl-agents-shepherd` or `mctl-agents-reconcile` with `service: "portfolio"`
  THE SYSTEM SHALL return no validation errors.
- WHEN an MCP client issues `tools/list` THE SYSTEM SHALL include `"portfolio"` in the
  `service` enum of `mctl_trigger_approve`, `mctl_trigger_implementer`,
  `mctl_trigger_shepherd` and `mctl_trigger_reconcile`.
- WHILE the four DevLoop operations declare a `service` enum THE SYSTEM SHALL keep each
  registry enum exactly equal (same values, same order, including the leading `""` on
  the three optional filters) to the enum of its mapped MCP tool.
- IF a future service is added to only one of the eight sites THEN THE SYSTEM SHALL fail
  `go test ./internal/operations/... ./internal/mcp/...` naming the operation or tool
  that is out of sync.
- WHILE the change is in effect THE SYSTEM SHALL leave the
  `mctl-agents-single-service` enum (`internal/operations/registry.go:557` and
  `internal/mcp/server.go:2601`, the eight rotating service-agent targets) unchanged.
- WHEN `grep -c '"portfolio"' internal/operations/registry.go` and
  `grep -c '"portfolio"' internal/mcp/server.go` are run THE SYSTEM SHALL report `4`
  for each file.
- WHEN `golangci-lint run` executes against the repository THE SYSTEM SHALL pass.

## Out of scope

- Deriving the service list from mctl-agents, configuration or a shared constant
  (tracked in #274). This proposal keeps the literals hard-coded.
- Any service name other than `portfolio` (notably `seerrsense`).
- Adding `portfolio` to the `mctl-agents-single-service` / `mctl_trigger_single_service`
  rotating-service enum, or to `mctl-agents-incidents` (whose `service` parameter has no
  enum at all, `internal/operations/registry.go:577`).
- Changes to the Temporal `DevLoopWorkflow`, to `internal/api/handlers_write.go`
  approver handling, or to mctl-agents itself.
- Any new MCP tool: tool count stays 74, so
  `TestNewMCPServer_ToolCount` / `TestAllToolsHaveTitleAnnotation`
  (`internal/mcp/server_test.go:66,171`) and `docs/portal-allowlist.json` are untouched.

## Open questions

- Naming: every existing entry carries the `mctl-` prefix; the issue specifies the bare
  literal `"portfolio"` (repo `mctlhq/portfolio`). Proceeding with `"portfolio"`
  verbatim as instructed — if mctl-agents' `config/settings.py` registers it as
  `mctl-portfolio`, the strings must match exactly or the same 400 returns.
- Whether the mctl-agents-side registration has already merged. Not blocking: adding a
  value to the enum is inert until a `portfolio` proposal exists.
- The parity guard cannot cover `mctl-agents-single-service` (deliberately a shorter
  list) or `mctl-agents-incidents` (no enum); those two are explicitly excluded with an
  inline comment rather than silently skipped.
