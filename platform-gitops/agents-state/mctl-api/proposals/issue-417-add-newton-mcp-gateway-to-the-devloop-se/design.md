# Design: issue-417-add-newton-mcp-gateway-to-the-devloop-se

## Current state

`mctl-api` validates DevLoop operation inputs against a hand-written operation
registry. The relevant declarations live in
`internal/operations/registry.go`, inside the package-level operation slice:

| Line (current HEAD) | Operation | `service` parameter |
| --- | --- | --- |
| 620 | `mctl-agents-single-service` | 8 rotating service-agent targets — **not** part of this change |
| 661 | `mctl-agents-implement` | optional filter, enum starts with `""` |
| 695 | `mctl-agents-shepherd` | optional filter, enum starts with `""` |
| 753 | `mctl-agents-approve` | `Required: true`, enum has no `""` |
| 789 | `mctl-agents-reconcile` | optional filter, enum starts with `""` |

Each of the four DevLoop enums is the identical 15-value literal, in order:
`mctl-web, mctl-openclaw, mctl-docs, mctl-api, mctl-portal, mctl-agent,
mctl-gitops, mctl-agents, mctl-telegram, mctl-design, mctl-pairdesk,
mctl-academy, seerrsense, portfolio, .github` (the three optional ones prefix
it with `""`, the "all services" default). Each literal is a single long line
in a `[]ParameterDef` composite literal.

`internal/mcp/server.go` declares the MCP tool schemas that clients and models
actually see. The four mirrors are `mcplib.Enum(...)` calls at lines 2800
(`mctl_trigger_implementer`), 2841 (`mctl_trigger_shepherd`), 2886
(`mctl_trigger_reconcile`) and 2985 (`mctl_trigger_approve`). A fifth,
unrelated `mcplib.Enum` at line 2743 belongs to `mctl_trigger_single_service`
and carries the eight rotating targets.

Two tests hold the copies together:

- `internal/operations/registry_test.go` — `wantServices` (line 24-27) is a
  hand-kept mirror of mctl-agents' `config/settings.py` SERVICES list.
  `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` checks all four
  registry enums against it in *both* directions (missing entry, and stale
  entry not in `wantServices`), and `TestApproveAcceptsEveryMctlAgentsService`
  drives `registry.ValidateInput("mctl-agents-approve", ...)` once per
  `wantServices` entry — the exact code path that produced the 400 for
  `portfolio` and `seerrsense`.
- `internal/mcp/server_test.go` — `TestServiceEnumsMatchRegistry` (line 894)
  boots a real MCP server, issues `tools/list`, and compares each tool's
  `service` enum against the registry's `ParameterDef.Enum` **by length, then
  index by index**. Order equality is deliberate (`serviceEnumOperationToTool`,
  line 875, lists exactly the four pairs; single-service and incidents are
  explicitly excluded).

The net effect today: an investigator run against a `newton-mcp-gateway` issue
succeeds — `mctl-agents-investigate` (line 710) takes only `issue_url` with
pattern `^https://github\.com/mctlhq/[A-Za-z0-9_.-]+/issues/[0-9]+$` and has no
service enum — and the resulting proposal is then un-approvable, because
`mctl-agents-approve` requires `service` and rejects the unlisted value.

A repo-wide grep confirms these nine sites are the only places the DevLoop
service list is spelled out: there is no OpenAPI document, Helm value, docs
page or e2e fixture carrying a second copy. (Matches elsewhere for
`seerrsense` are unrelated — `internal/roadmap/testdata/*` snapshots and a
`handlers_domains_test.go` tenant name.)

## Proposed solution

Append the literal string `"newton-mcp-gateway"` as the **last** element of
each of the nine lists, preserving all existing values and their order:

1. `internal/operations/registry.go` line 661 — `mctl-agents-implement`
2. `internal/operations/registry.go` line 695 — `mctl-agents-shepherd`
3. `internal/operations/registry.go` line 753 — `mctl-agents-approve`
4. `internal/operations/registry.go` line 789 — `mctl-agents-reconcile`
5. `internal/mcp/server.go` line 2800 — `mctl_trigger_implementer`
6. `internal/mcp/server.go` line 2841 — `mctl_trigger_shepherd`
7. `internal/mcp/server.go` line 2886 — `mctl_trigger_reconcile`
8. `internal/mcp/server.go` line 2985 — `mctl_trigger_approve`
9. `internal/operations/registry_test.go` line 26 — `wantServices`

Nothing else changes: no new parameter, no new operation, no new MCP tool (so
the tool-count expectation in `server_test.go` is unaffected), no handler, no
route, no schema version. The edit is textual and append-only.

Why append rather than insert alphabetically: `TestServiceEnumsMatchRegistry`
compares index-by-index, and the comment on it documents the "append-at-the-end
convention" precisely so that a divergent insertion point in one of the eight
sites fails loudly instead of drifting. Following the convention keeps the diff
one token wide per line and matches how `portfolio`, `seerrsense` and `.github`
were added.

Why `wantServices` is edited in the same commit: it is the fixture that turns
the eight production edits into assertions. Editing it alone would make the
membership test red; editing the production sites alone would leave
`TestApproveAcceptsEveryMctlAgentsService` never exercising the new value — the
precise gap that let the `seerrsense` outage run green. The reverse-direction
check in `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices` (a value
in an enum but not in `wantServices` is an error) makes the two halves
mutually enforcing within a single commit.

Line-count and lint: the four `registry.go` enum lines and the four
`server.go` enum lines are already very long single lines. Appending one value
keeps them single lines; `gofmt` will not rewrap them and no `lll`-style limit
is enforced on them today (they pass lint at their current length). Run
`go fmt ./...` and `golangci-lint run` to confirm rather than assume.

## Alternatives

1. **Do the #274 refactor now** — hoist the list into one exported
   `var devLoopServices = []string{...}` in `internal/operations` and have both
   `registry.go` and `internal/mcp/server.go` spread it. This is the correct
   long-term fix and is what #274 tracks. Dropped because the issue explicitly
   scopes it out, because it would change `internal/mcp`'s import graph and the
   meaning of `TestServiceEnumsMatchRegistry` (which would become tautological
   and would have to be redesigned), and because it converts a one-token,
   zero-risk change into a reviewable refactor while a proposal is blocked.
2. **Validate against mctl-agents' `config/settings.py` at runtime** — fetch or
   vendor the upstream SERVICES list so the copies cannot drift at all. This is
   what `registry_test.go`'s own comment identifies as the only real fix for
   the "nobody mirrored it here" class. Dropped: it introduces a cross-repo
   runtime or build-time dependency, needs a failure policy for when the fetch
   fails (fail-closed blocks every approve; fail-open re-creates today's bug),
   and is far beyond a minimal unblock.
3. **Drop the enum from `mctl-agents-approve` and let mctl-agents reject bad
   names** — the widest change: the 400 moves from the API edge to a dispatched
   Argo workflow that dies later. `TestImplementAndShepherdServiceEnumCoversMctlAgentsServices`
   documents exactly why that direction "fails worse, not better". Dropped.
4. **Add the value only to `mctl-agents-approve`** (the operation actually
   blocking the proposal). Dropped: it would immediately fail the
   reverse-direction membership check unless `wantServices` also changed, and
   would then fail it for the other three operations — and the implementer,
   shepherd and reconcile sweep hit the same wall a day later.

## Platform impact

- **Migrations:** none. No database schema, no GitOps manifest, no Helm value.
- **Backward compatibility:** strictly additive. Every previously accepted
  `service` value keeps working and keeps its position; no caller can observe a
  removal. The MCP tool schema gains one enum member, which clients treat as a
  widened union. No MCP tool is added or removed, so the tool-count expectation
  in `internal/mcp/server_test.go` is untouched.
- **Resource impact:** none — four extra strings in a static schema.
- **Security / authorization:** unchanged. All four operations remain
  `AdminOnly: true` with their current `RiskLevel` (`RiskMedium` for implement,
  shepherd, approve and reconcile). Widening the enum does not widen who may
  call them; it only lets an already-authorized admin name one more repo. The
  `approver` field's provenance rules on `mctl-agents-approve` are untouched.
- **Risks and mitigations:**
  - *Partial edit (fewer than nine sites).* Mitigated by
    `TestServiceEnumsMatchRegistry` (catches a missed `server.go` mirror or a
    wrong insertion index) and by the two-directional membership test in
    `registry_test.go` (catches a missed `registry.go` enum or a missed
    `wantServices` entry). The grep counts in the acceptance criteria are a
    cheap manual backstop.
  - *Wrong enum edited.* Touching the `mctl-agents-single-service` enum
    (`registry.go` line 620 / `server.go` line 2743) would silently add a
    rotating service-agent target. Mitigated by an explicit review check that
    the 8-value lists still have 8 values, and by the per-file grep count of
    exactly 4.
  - *mctl-agents has not in fact registered the repo.* Then mctl-api would
    accept a service the agent side rejects, turning an edge 400 into a failed
    Argo run. Mitigated by confirming the name appears in mctl-agents'
    `config/settings.py` before merge; out of this repo's test reach by design.
  - *Name typo (`newton-mcp-gateway` vs. a variant).* A typo mirrored into all
    nine sites would pass every test in this repo and still 400 at the agent
    side. Mitigated by copying the name verbatim from the issue and the
    upstream registration.
