# Document `status=active` Virtual Filter and Audit env_vars Redaction in MCP Tools Reference

> version-status: unverified, see commit SHA a8cdba5 (mctl-api 4.18.4 confirmed via mctl-gitops a61f047 2026-05-13)

## Context

Commit `a8cdba5` in `mctl-api` (2026-05-07, shipped in version 4.18.4) introduced
two user-visible behavioural changes to the MCP tools surface. First, the alerts
and incidents listing endpoint now defaults to `status=active` when no status
filter is provided. The `active` value is a new virtual status that expands to all
non-terminal alert states (i.e. everything that is not resolved or closed). Before
this change, omitting the status parameter would return no results or an unfiltered
list — behaviour that is now different. Second, workflow audit entries returned by
`GetWorkflow` and related endpoints now have their `env_vars` fields redacted
before being serialised; callers who previously read raw secret values from those
fields will now receive redacted placeholders.

The current `docs/mcp/tools-reference.md` documents neither the `active` virtual
status nor the `env_vars` redaction policy. Any developer or operator calling
`mctl_list_incidents` without a status filter today gets different results than
they would expect from the docs. Any automation that parses `env_vars` from audit
payloads will silently break — the fields are no longer populated with real values.
Both changes are in production and need to be reflected in the MCP Tools Reference.

## User stories

- AS a developer calling `mctl_list_incidents` via the MCP server I WANT to know
  that omitting the `status` parameter returns all active (non-terminal) incidents
  by default SO THAT I understand why my results changed after the 4.18.4 upgrade
  and can adjust my queries accordingly.
- AS a developer I WANT to know what the `active` virtual status value means (all
  non-terminal states) SO THAT I can use it explicitly in my queries and rely on
  its documented semantics.
- AS an operator building automation on top of the MCP tools I WANT to know that
  `env_vars` fields in workflow audit entries are redacted SO THAT I do not write
  code that depends on raw secret values being present in those fields.
- AS a security-minded developer I WANT the docs to state the audit redaction
  policy clearly SO THAT I can satisfy a security review question about where
  secret values appear in API responses.

## Acceptance criteria (EARS)

- WHEN a reader opens `docs/mcp/tools-reference.md` and reads the
  `mctl_list_incidents` (or equivalent alerts listing tool) documentation THE
  SYSTEM SHALL describe the `status` parameter including the `active` virtual
  value and its meaning (all non-terminal states).
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL state that
  `status=active` is the default when the parameter is omitted.
- IF a reader wants to list only unresolved incidents THEN THE SYSTEM SHALL show
  an example call using `status=active` explicitly.
- WHEN a reader opens `docs/mcp/tools-reference.md` and reads the workflow or
  audit-related tool documentation THE SYSTEM SHALL state that `env_vars` fields
  in audit entries are redacted and will not contain raw secret values.
- WHEN a reader opens `docs/mcp/tools-reference.md` THE SYSTEM SHALL NOT imply
  that `env_vars` audit fields contain real environment variable values.

## Out of scope

- Documenting the internal `RedactEntry()` function or the `internal/audit/`
  package — implementation detail, not user-facing.
- Documenting the `host` and `port` fields added to service responses in the
  same commit — these are part of the REST API surface, not the MCP tool
  interface. If needed, that belongs in `docs/api/index.md` under a separate
  proposal.
- Documenting all non-terminal status values individually — only the `active`
  virtual alias needs documentation; the list of underlying states is an
  implementation detail.
- Migration guide for automations that relied on unredacted `env_vars` — that is
  a support concern.
- Video tutorial or localisation.
