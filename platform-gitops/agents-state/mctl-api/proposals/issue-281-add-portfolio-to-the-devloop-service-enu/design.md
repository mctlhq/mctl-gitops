# Design: issue-281-add-portfolio-to-the-devloop-service-enu

## Current state

**The operation registry.** `internal/operations/registry.go` declares every platform
operation as a static `Operation` literal with a `[]ParameterDef`. Four of them carry a
hard-coded DevLoop service list on their `service` parameter:

| Operation | Line | Shape |
| --- | --- | --- |
| `mctl-agents-implement` | 596 | optional filter, enum starts with `""` |
| `mctl-agents-shepherd` | 628 | optional filter, enum starts with `""` |
| `mctl-agents-approve` | 671 | `Required: true`, no `""` |
| `mctl-agents-reconcile` | 707 | optional filter, enum starts with `""` |

All four end with `..., "mctl-agents", "mctl-telegram", "mctl-design", "mctl-pairdesk",
"mctl-academy"`. Two further `service` parameters exist and are deliberately different:
`mctl-agents-single-service` (line 557) lists only the eight rotating service-agent
targets (`mctl-web` … `mctl-agents`), and `mctl-agents-incidents` (line 577) declares
`service` with no `Enum` at all ("Unused for incident-responder mode").

**How the enum becomes a 400.** `Registry.ValidateInput`
(`internal/operations/registry.go:109`) loops the declared parameters; for any present,
non-empty value it linearly scans `p.Enum` and, on no match, appends
`service: must be one of ...`. The generic execute handler
(`internal/api/handlers_write.go`) turns that list into a 400 before anything reaches
Argo. `mctl-agents-approve` is the operation the Temporal `DevLoopWorkflow` approve
activity submits (`POST /api/v1/operations/mctl-agents-approve/execute`, mirrored by
`internal/mcp/server.go:2799`), so an unknown `service` is exactly the "approve fails,
proposal stays `proposed`, workflow ends `Failed`" symptom in the issue.

**The MCP mirror.** `internal/mcp/server.go` re-declares the same lists by hand as
`mcplib.Enum(...)` arguments inside the tool constructors:
`toolTriggerImplementer` (2658), `toolTriggerShepherd` (2699), `toolTriggerReconcile`
(2744), `toolTriggerApprove` (2787), plus the untouched single-service enum at 2601.
The MCP handlers do not validate: `extractStringParams` forwards any string through to
the REST operation, so the MCP enum is purely the schema the model/client sees — it can
drift from the registry without any runtime error, which is why both halves must change.

**Existing guards.** `internal/operations/registry_test.go:26`
(`TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`) holds a `wantServices`
literal mirroring mctl-agents' `config/settings.py` and asserts, for the same four
operation names, that every wanted service is present in the enum (subset check, order
insensitive). Its doc comment records the live mctl-design incident this design is a
repeat of. On the MCP side, `internal/mcp/server_test.go:845` has the
`operationToTool` fixture mapping each non-`HandlerOnly` operation to its tool name, and
`TestMCPToolsCoverEveryNonHandlerOnlyOperation` (874) reads live `tools/list` JSON —
but nothing today compares *enum contents* between registry and MCP. That missing check
is the "eight sites cannot drift again" guard the issue asks for.

`.golangci.yml` enables errcheck/govet/staticcheck/unused/ineffassign/gocritic/gosec/
bodyclose/nilerr — no line-length linter, so extending the existing single-line enum
literals is lint-safe. `docs/portal-allowlist.json` records tool *names* only and needs
no change; tool count stays 74.

## Proposed solution

A literal, mechanical extension of the eight lists plus one new parity test.

1. **Registry (4 edits).** Append `"portfolio"` as the last element of the `Enum` slice
   on the `service` parameter of `mctl-agents-implement`, `mctl-agents-shepherd`,
   `mctl-agents-approve` and `mctl-agents-reconcile`. Existing order preserved; no other
   field, description, or operation touched. `mctl-agents-single-service` and
   `mctl-agents-incidents` are left alone by design.

2. **MCP (4 edits).** Append `"portfolio"` to the `mcplib.Enum(...)` call for the
   `service` property in `toolTriggerImplementer`, `toolTriggerShepherd`,
   `toolTriggerReconcile` and `toolTriggerApprove`. The `mctl-agents` inclusion comment
   above the shepherd enum stays valid and unedited.

3. **Extend the existing registry guard.** Add `"portfolio"` to `wantServices` in
   `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`
   (`internal/operations/registry_test.go:29`) and update the neighbouring comment to
   name issue #281 alongside the mctl-design incident. Because that test is a subset
   check over the same four operations, this single line turns criterion 2 ("approve
   accepts `service=portfolio`") into a compile-time-visible failure if any of the four
   registry edits is missed.

4. **Add a direct approve-validation test.** In `internal/operations/registry_test.go`,
   assert `NewRegistry().ValidateInput(approveOp, map[string]string{"service":
   "portfolio", "slug": "issue-281-add-portfolio"})` returns no errors. This exercises
   the exact code path that produced the 400, not just the enum literal, and covers the
   `slug` `Pattern` at the same time.

5. **Add the registry-to-MCP enum parity test.** In `internal/mcp/server_test.go`, next
   to the existing `operationToTool` fixture, add
   `TestServiceEnumsMatchRegistry`: for each of the four DevLoop operation/tool pairs,
   read the tool's `service` enum from live `tools/list` JSON (the same
   `mcpSrv.HandleMessage` + `json.Unmarshal` shape already used at
   `server_test.go:879`, unmarshalling `tools[].inputSchema.properties.service.enum`
   into `[]string`) and compare it element-by-element, order included, with the
   registry `ParameterDef.Enum` from `operations.NewRegistry()`. Reading through
   `tools/list` rather than poking `tool.InputSchema.Properties` (a `map[string]any`
   needing nested type assertions) also directly satisfies acceptance criterion 3.
   The test explicitly excludes, with an inline comment, `mctl-agents-single-service`
   (intentionally the shorter rotating list) and `mctl-agents-incidents` (no enum) so a
   reader knows the omission is a decision, not an oversight.

Order-sensitive equality is chosen deliberately: the two lists are maintained by hand in
lockstep, an appended-at-the-end convention is already established, and exact equality
is the only check that catches a value added to one side and a *different* value added
to the other.

## Alternatives

- **Derive the enum from a single exported constant** (e.g.
  `operations.DevLoopServices` consumed by both files). This is the right long-term
  shape and would make seven of the eight sites impossible to forget — but it is exactly
  the structural refactor #274 owns, and the issue explicitly says not to attempt it
  here. Dropped to keep this change reviewable and conflict-free with #274.
- **Drop the enum on `mctl-agents-approve` and validate service names elsewhere**
  (e.g. accept any `^[a-z0-9-]+$`). This would end the class of failure outright, but it
  removes the fail-closed property that keeps a typo'd service from reaching the gitops
  commit workflow, and it silently widens an admin-only, RiskMedium operation. Dropped.
- **Registry-only change, leaving the MCP schemas behind.** The REST path would work,
  since `extractStringParams` never validates against the schema. But MCP clients would
  never be able to *select* `portfolio` (the model sees the enum as the closed set of
  legal values), and the eight-site invariant would be broken on purpose. Dropped.
- **Fetch the list from mctl-agents at startup.** Introduces a runtime dependency and a
  failure mode (what does the enum contain when the fetch fails?) for a list that
  changes a few times a year. Dropped.

## Platform impact

- **Migrations:** none. No database, no gitops schema, no Helm value changes.
- **Backward compatibility:** strictly additive. Adding a value to an allowlist cannot
  reject anything previously accepted, and no existing caller passes `portfolio` today.
  MCP clients see one extra enum member; tool count and tool names are unchanged, so
  `TestNewMCPServer_ToolCount` (74), `TestAllToolsHaveTitleAnnotation` and
  `TestPortalAllowlist_CoversEveryRegisteredTool` stay green untouched.
- **Resource impact:** none — `ValidateInput`'s linear scan grows by one element.
- **Risk: the string does not match mctl-agents.** If `config/settings.py` registers
  `mctl-portfolio` rather than `portfolio`, the 400 persists with a now-misleading enum.
  Mitigation: the implementer should confirm the literal against mctlhq/mctl-agents
  `config/settings.py` before merging; the fix is a one-word edit in eight places.
- **Risk: only some of the eight sites are edited.** Mitigation: the extended
  `wantServices` guard covers the four registry sites, and the new parity test covers
  the four MCP sites by construction (any MCP list missing `portfolio` no longer equals
  its registry list).
- **Risk: the parity test is too strict and blocks a legitimate future divergence.**
  Mitigation: it is scoped to exactly the four DevLoop pairs and documents the two
  intentionally-divergent operations inline, so a future divergence is an explicit edit
  to a named list rather than a mystery failure.
- **Deployment:** ships with the next mctl-api image; approval for a `portfolio`
  proposal works from the moment the new pod serves traffic. No coordination window is
  needed with mctl-agents in either direction.
