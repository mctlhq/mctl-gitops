# Design: issue-457-mcp-work-items-refuse-non-string-optiona

## Current state
- `internal/mcp/server.go` `stringArg(req, name)` (around line 2362) does
  `req.GetArguments()[name].(string)` and returns "" on a failed assertion. It cannot distinguish
  "absent" from "present with the wrong type". It is shared by many tools.
- `internal/mcp/workitems.go`:
  - `idArg(req, name, required)` (line ~232) trims `stringArg(req, name)`, refuses "" when required
    ("missing required argument: <name>"), and refuses a non-empty value that does not match
    `workItemIDPattern` (`^[A-Za-z0-9_-]{1,128}$`).
  - `requiredPathArg(req, name)` (line ~244) is `return idArg(req, name, true)`.
  - Callers: `toolGetWorkItem` and `toolListWorkItemExecutions` (`requiredPathArg("work_item_id")`),
    `toolListWorkItemSnapshots` (`requiredPathArg("work_item_id")`, `idArg("snapshot_id", false)`),
    `toolListWorkItemExecutionRequests` (`requiredPathArg("work_item_id")`, `idArg("request_id", false)`),
    `toolRequestWorkItemExecution` (`requiredPathArg("work_item_id")`,
    `idArg("resumed_from_execution_id", false)`; the field is only added to the body when non-empty).
  - So `snapshot_id: 5` yields "" -> the tool hits `GET /api/v1/work-items/{id}/snapshots` (list)
    instead of `/snapshots/{sid}`; same for `request_id`. `resumed_from_execution_id: 5` is dropped.
- `internal/mcp/workitems_test.go` has `TestWorkItemToolsRefuseIDsThatAreNotOneSegment`
  (string-shaped bad ids) and `TestRequestWorkItemExecutionRefusesBadArgumentsWithoutCalling`
  (table of mutations, asserts no API call); neither covers non-string ids.
- `requiredPathArg` / `idArg` are referenced only in `internal/mcp/workitems.go` (grep over the repo).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/*/mctl-api`: no such path in the checkout; mctl-api's deployed values
  were not found under tenant services (it is likely deployed as a platform component elsewhere). Not
  needed for this change: it is a pure input-validation change inside the MCP handlers, with no env var,
  config, or resource dimension. No mctl MCP read tools were called for the same reason.

## Proposed solution
Change only `idArg` in `internal/mcp/workitems.go`, so every work-item id (required and optional) gets
the same type check:

```go
func idArg(req mcplib.CallToolRequest, name string, required bool) (string, *mcplib.CallToolResult) {
    raw, present := req.GetArguments()[name]
    s, isString := raw.(string)
    if present && !isString {
        return "", mcplib.NewToolResultError(name + " must be a string id")
    }
    v := strings.TrimSpace(s)
    switch { ... unchanged: required-empty and pattern checks ... }
    return v, nil
}
```

- "present" is decided by the map lookup, so an explicit JSON `null` (decoded as a nil interface
  stored under the key) counts as present-but-not-a-string and is refused, as the issue asks.
- Absent keys and "" / whitespace strings behave exactly as before.
- `stringArg` is not touched, so no other tool changes behaviour.
- Rename `requiredPathArg` to `requiredIDArg` (doc comment: "requiredIDArg is idArg for a required
  argument.") and update all five call sites in `workitems.go`.

The refusal happens before `workItemCall`, so no HTTP request is made, matching the existing
"refuse without calling" contract the tests assert.

## Alternatives
1. Make `stringArg` return `(string, bool)` or refuse non-strings globally. Dropped: `stringArg` is
   used by dozens of tools in `server.go`; changing it widens the blast radius far beyond the issue
   and could break clients that rely on lenient handling elsewhere.
2. Add a separate `optionalIDArg` helper with the type check, leaving `idArg` lenient. Dropped: it
   would leave required ids with a misleading "missing required argument" for a mistyped value and
   adds a third helper where one parameterised helper already exists.
3. Treat `null` as absent and only refuse numbers/booleans/objects/arrays. Dropped as the default
   because the issue explicitly lists `snapshot_id: null` as something to refuse; recorded as an open
   question.

## Platform impact
- No migrations, no API/route change, no config or resource change; MCP tool count unchanged.
- Backward compatibility: a client that sent a non-string optional id previously got a (wrong) full
  listing or a silently dropped resume source; it now gets an error result. This is the intended
  behaviour change. Clients that send `null` for unset optionals would now be refused on these three
  tools only — the main risk. Mitigation: error text names the argument; relaxing null to absent is a
  one-line follow-up if needed.
- Required `work_item_id` with a non-string value: still refused, only the message changes.
