# Add newton-mcp-gateway to the DevLoop service enums (all nine sites)

## Context

`mctlhq/newton-mcp-gateway` has been registered as a DevLoop target on the
mctl-agents side (tenant `labs`), but `mctl-api` keeps its own hand-maintained
copies of the service list. Four `ParameterDef.Enum` values in
`internal/operations/registry.go` (for `mctl-agents-implement`,
`mctl-agents-shepherd`, `mctl-agents-approve`, `mctl-agents-reconcile`), their
four `mcplib.Enum(...)` mirrors in `internal/mcp/server.go`, and the
`wantServices` fixture in `internal/operations/registry_test.go` all enumerate
the accepted services literally. Until `"newton-mcp-gateway"` is present in
those nine places, `Registry.ValidateInput` rejects
`service=newton-mcp-gateway` with a 400 on `mctl-agents-approve`.

That is exactly the failure mode already recorded in this repository for
`portfolio` (mctl-api#281), `seerrsense` (#306) and `.github` (#313): the
issue-investigator runs fine — `mctl-agents-investigate` takes an `issue_url`
matching `^https://github\.com/mctlhq/[A-Za-z0-9_.-]+/issues/[0-9]+$` and has
no service enum at all — so a proposal lands under
`platform-gitops/agents-state/newton-mcp-gateway/proposals/<slug>/`, and then
nothing can approve it. The existing enum tests do not catch this: as the
comment on `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` states,
`wantServices` is a hand-kept copy, so an omission that lands in all five
places keeps the suite green. This proposal is the minimal, targeted mirror
edit. The structural fix (deriving the list from one source) stays with #274.

## User stories

- AS a platform admin I WANT `mctl-agents-approve` to accept
  `service=newton-mcp-gateway` SO THAT a proposal written for the new repo can
  actually be approved and reach the Tier 2 implementer.
- AS an operator I WANT `mctl_trigger_implementer`, `mctl_trigger_shepherd`,
  `mctl_trigger_approve` and `mctl_trigger_reconcile` to offer
  `newton-mcp-gateway` in their MCP schemas SO THAT an MCP client can scope a
  run to the new repo without a schema-validation rejection.
- AS a maintainer I WANT the repository's own parity tests to cover the new
  name SO THAT a future partial edit of the nine sites still fails the build.

## Acceptance criteria (EARS)

- WHEN a caller invokes `mctl-agents-approve` with `service=newton-mcp-gateway`
  and a slug matching `^[a-z0-9][a-z0-9-]{0,120}$` THE SYSTEM SHALL accept the
  input and return no validation errors from `Registry.ValidateInput`.
- WHEN a caller invokes `mctl-agents-implement`, `mctl-agents-shepherd` or
  `mctl-agents-reconcile` with `service=newton-mcp-gateway` THE SYSTEM SHALL
  accept the value as an in-enum service filter.
- WHEN an MCP client requests `tools/list` THE SYSTEM SHALL expose
  `newton-mcp-gateway` in the `service` enum of `mctl_trigger_implementer`,
  `mctl_trigger_shepherd`, `mctl_trigger_approve` and `mctl_trigger_reconcile`,
  value-for-value and in the same order as the registry enums, so that
  `TestServiceEnumsMatchRegistry` passes.
- WHILE the change is in effect THE SYSTEM SHALL keep the existing order of
  every service enum unchanged, with `"newton-mcp-gateway"` appended after
  `".github"` as the last element.
- WHILE the change is in effect THE SYSTEM SHALL leave the
  `mctl-agents-single-service` enum (`internal/operations/registry.go` around
  line 620 and its mirror in `internal/mcp/server.go` around line 2743)
  untouched at its eight rotating service-agent targets.
- IF `wantServices` in `internal/operations/registry_test.go` lists
  `newton-mcp-gateway` THEN THE SYSTEM SHALL exercise it through both
  `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` (membership in
  all four registry enums, in both directions) and
  `TestApproveAcceptsEveryMctlAgentsService` (end-to-end `ValidateInput`).
- WHEN the repository is built and checked THE SYSTEM SHALL pass
  `go build ./...`, `go vet ./...`, `go test ./...` and `golangci-lint`.
- WHEN `grep -c '"newton-mcp-gateway"'` is run THE SYSTEM SHALL report 4
  occurrences in `internal/operations/registry.go` and 4 in
  `internal/mcp/server.go`.

## Out of scope

- mctl-api#274 — the structural refactor that would derive all nine sites from
  a single declaration. Explicitly deferred by the issue.
- Any service name other than `newton-mcp-gateway`.
- The `mctl-agents-single-service` rotating-services enum (eight entries), and
  the `mctl-agents-incidents` `service` parameter, which carries no enum.
- The Temporal `DevLoopWorkflow`, `internal/workflows`, and anything in
  `mctlhq/mctl-agents` (its `config/settings.py` SERVICES list is assumed
  already updated).
- Tenant (`labs`) provisioning, repo access grants, GitHub App installation, or
  any credential work needed for the private repo to be cloneable.
- MCP tool-count expectations in `server_test.go` — no tool is added or removed.

## Open questions

- The issue states the tenant is `labs` and the repo is private. `mctl-api`'s
  enums are purely name-based and carry no tenant or visibility notion, so
  nothing here depends on it; any clone-credential work for a private repo
  lives in mctl-agents/GitOps and is treated as already handled.
- The exact ordering convention is "append at the end", per the
  `TestServiceEnumsMatchRegistry` comment. This proposal assumes
  `"newton-mcp-gateway"` goes after `".github"` in every list, including
  `wantServices`. If mctl-agents' `config/settings.py` orders it differently,
  only the two sides *inside this repo* must match each other; the tests do not
  compare order against mctl-agents.
- Whether `newton-mcp-gateway` should also be added to the `mctl-agents-run`
  rotating service-agent list is not asked for and is assumed to be no.
