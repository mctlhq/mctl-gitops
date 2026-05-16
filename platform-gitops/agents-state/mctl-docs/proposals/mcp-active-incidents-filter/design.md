# Design: mcp-active-incidents-filter

> version-status: unverified, see commit SHA a8cdba5

## Source commits

- `mctl-api:a8cdba5` — fix(mcp): redact audit env_vars + active incidents default + service host/port

Key diff evidence from the inbox analysis:
- New `internal/audit/redact.go` (+115 lines) with `RedactEntry()` applied to
  audit entries before serialisation in `handlers_read.go`.
- New `StatusActive = "active"` constant in `internal/alerts/types.go` as a
  virtual filter covering all non-terminal states.
- The alerts handler now defaults to `status=active` when no status is specified.

## Current state of documentation

Existing page: `docs/mcp/tools-reference.md` (MCP Tools Reference)

The page documents the MCP tool set available via the mctl-api MCP server. Based
on the inbox analysis:

- The `mctl_list_incidents` tool entry (or equivalent alerts-listing tool) does
  not document the `status` parameter's `active` virtual value, and does not
  state that `status=active` is now the default when the parameter is omitted.
  A reader would not know that their query results changed semantics in 4.18.4.
- Workflow / audit-related tool entries (e.g. `mctl_get_workflow` or equivalent)
  do not mention the `env_vars` redaction policy. A reader might still expect
  raw secret values to appear in audit payloads, and write code accordingly.

<TODO: confirm exact tool names for the incidents-listing and workflow-retrieval
tools with the author of mctl-api:a8cdba5 — the inbox analysis refers to
`mctl_list_incidents` and `GetWorkflow` but the public MCP tool names may differ.>

## Proposed solution

Update `docs/mcp/tools-reference.md` with two targeted additions:

### 1. Update the incidents / alerts listing tool entry

In the parameter table for the incidents-listing tool:
- Add a row for `status` (if not already present) or update the existing row.
- Document the `active` virtual value: "Matches all non-terminal incident states
  (open, acknowledged, escalated, etc.). This is the **default** when `status`
  is not specified."
- List any other known status values if already documented; keep `active` clearly
  marked as the default.
- Add a short example invocation with `status=active` explicitly set.

### 2. Add an audit redaction note to workflow tool entries

In the description of any tool that returns workflow audit data (e.g. the
`GetWorkflow`-equivalent MCP tool):
- Add a callout or note: "Audit entries returned by this tool have their
  `env_vars` fields redacted. The field will not contain raw secret values.
  This is a deliberate security measure (mctl-api 4.18.4+)."

### No structural changes

Both additions are updates to the body of an existing page. No new pages, no new
sidebar entries, no nav changes.

## Alternatives

**Option A (adopted): in-place update of `docs/mcp/tools-reference.md`.**
Minimal, targeted. Two additions in the right places. Easy to review.

**Option B: add a dedicated "Security behaviour of MCP tools" section at the top
of the tools reference.**
A single section documenting all security-relevant tool behaviours (redaction,
defaults, rate limits). Dropped for now — there is currently only one redaction
case; a dedicated section would be premature. Can be reconsidered when a second
redaction or policy applies.

**Option C: document the redaction in `docs/security/authentication.md`.**
Dropped — audit redaction is about API response content, not authentication.
The tools reference is the correct home.

## Impact

- VitePress sidebar / nav config: no change required (page already in sidebar).
- Mermaid diagrams: not needed for this update — the change is a parameter
  table update and a callout note.
- Documentation versioning: applies to mctl-api 4.18.4 and later. No multi-
  version setup exists; add `> Available from mctl-api 4.18.4.` callouts to
  make the version boundary explicit for readers.
