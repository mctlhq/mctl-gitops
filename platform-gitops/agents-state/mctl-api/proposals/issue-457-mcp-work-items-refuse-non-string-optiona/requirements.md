# Refuse non-string optional ids in the work-item MCP tools; rename requiredPathArg

## Context
Issue #457 collects two deferred P3 findings from the #456 review. The work-item MCP tools
(`internal/mcp/workitems.go`) read id arguments through `idArg`, which calls `stringArg`
(`internal/mcp/server.go`). `stringArg` returns "" for any value that is not a JSON string, so an
optional id that is present but mistyped (`snapshot_id: 5`, `snapshot_id: null`, `request_id: true`,
`resumed_from_execution_id: {}`) is indistinguishable from an absent one. On the read tools that
silently widens the answer: `mctl_list_work_item_snapshots` lists every snapshot instead of the one
asked for, and `mctl_list_work_item_execution_requests` lists every request. On
`mctl_request_work_item_execution` a mistyped `resumed_from_execution_id` is dropped from the body.
A caller that asked for one specific record must get a refusal, not a different answer.

Second, `requiredPathArg` is now a one-line wrapper over `idArg(req, name, true)` and no longer has
anything path-specific about it; it should be renamed `requiredIDArg`.

## User stories
- AS an MCP client (human or agent) I WANT a mistyped optional id to be refused SO THAT I never
  mistake a full listing for the single record I asked for.
- AS a maintainer of mctl-api I WANT the helper name to say what it does SO THAT the id-validation
  helpers read consistently.

## Acceptance criteria (EARS)
- IF `snapshot_id` is present in the arguments of `mctl_list_work_item_snapshots` and its value is not a
  JSON string (number, boolean, null, object, array) THEN THE SYSTEM SHALL return an MCP error result
  naming `snapshot_id` and SHALL NOT call the mctl API.
- IF `request_id` is present in the arguments of `mctl_list_work_item_execution_requests` and its value
  is not a JSON string THEN THE SYSTEM SHALL return an MCP error result naming `request_id` and SHALL
  NOT call the mctl API.
- IF `resumed_from_execution_id` is present in the arguments of `mctl_request_work_item_execution` and
  its value is not a JSON string THEN THE SYSTEM SHALL return an MCP error result naming
  `resumed_from_execution_id` and SHALL NOT call the mctl API.
- IF the required `work_item_id` is present but not a JSON string THEN THE SYSTEM SHALL return an MCP
  error result and SHALL NOT call the mctl API (behaviour already holds today via "missing required
  argument"; the message becomes the type-specific one).
- WHEN an optional id argument is absent from the arguments map THE SYSTEM SHALL behave exactly as today
  (list mode for the read tools, no `resumed_from_execution_id` in the request body).
- WHEN an optional id argument is a string that is empty or whitespace-only THE SYSTEM SHALL behave
  exactly as today (treated as absent).
- WHEN an id argument is a string THE SYSTEM SHALL continue to trim it and validate it against
  `workItemIDPattern`, refusing anything that is not one safe path segment.
- WHILE validating id arguments THE SYSTEM SHALL use a single helper named `requiredIDArg` for required
  ids; the identifier `requiredPathArg` SHALL no longer exist in the codebase.

## Out of scope
- Changing `stringArg` itself or its behaviour for any other MCP tool in `internal/mcp/server.go`.
- Type-strict handling of the non-id string arguments of `mctl_request_work_item_execution`
  (`kind`, `idempotency_key`); both already refuse a non-string value via their own checks.
- Any change to the REST API, its routes, or the work-item store.
- Changes to tool names, descriptions, or the MCP tool count.

## Open questions
- Should an explicit empty string optional id (`snapshot_id: ""`) also be refused? This proposal keeps
  today's behaviour (treated as absent) because the issue only names non-string values and some clients
  send "" for unset optional fields. Reviewer may tighten this.
- JSON `null` is treated as "present but not a string" and refused, as the issue explicitly lists
  `snapshot_id: null`. Some MCP clients serialize unset optionals as null; if that turns out to be common,
  null could be relaxed to "absent" later.
