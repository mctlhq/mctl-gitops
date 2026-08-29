# Design: issue-197-syncrepos-use-authenticated-user-ignore

## Current state

`Handlers.SyncRepos` in `internal/api/handlers_repos.go` (lines 113-169)
implements `POST /api/v1/repos/sync`:

```go
user := auth.UserFromContext(r.Context())

var req struct {
    Team string `json:"team"`
    User string `json:"user"`
}
if err := json.NewDecoder(r.Body).Decode(&req); err != nil { ... }
if req.Team == "" { ... 400 ... }
// Default to the authenticated user's GitHub login.
if req.User == "" && user != nil {
    req.User = user.ID
}
if req.User == "" { ... 400 "missing required field: user" ... }
if user != nil && !user.HasTenantAccess(req.Team) { ... 403 ... }

upstream := fmt.Sprintf("%s/api/github-app-connect/repos/sync?team=%s&user=%s",
    baseURL, url.QueryEscape(req.Team), url.QueryEscape(req.User))
```

The bug: `req.User` is only overwritten when the body's `user` is empty. Any
caller who knows another user's ID/login can set `"user": "<other-id>"` in
the body and have Backstage's `github-app-connect/repos/sync` execute (and
attribute) the sync as that other identity, regardless of who is actually
authenticated. The only real access control applied is
`user.HasTenantAccess(req.Team)`, which gates the *team*, not the *identity*
forwarded to Backstage.

Two other places reference the same contract and would go stale if only the
handler changed:
- `internal/mcp/server.go`, `toolSyncRepos` (around line 1347-1383): the
  `mctl_sync_repos` MCP tool declares a `user` string parameter
  ("GitHub username (defaults to authenticated user)") and forwards it
  verbatim as a POST param via `s.apiPost(ctx, "/api/v1/repos/sync", params)`.
- `internal/openapi/openapi.yaml` (around line 960-981): documents the
  `POST /api/v1/repos/sync` request body schema with a `user` string
  property, with no indication it is ignored.

For comparison, `internal/api/handlers_domains.go` shows the platform's
existing convention for mutating, identity-sensitive endpoints: `VerifyDomain`
and `DeleteDomain` fail closed with `401 Unauthorized` when
`auth.UserFromContext` returns `nil`, rather than falling back to a
request-supplied value (see `TestVerifyDomainNilUserUnauthorized` /
`TestDeleteDomainNilUserUnauthorized` in
`internal/api/handlers_domains_test.go`). `SyncRepos` currently diverges from
this: with a nil user it falls through to "missing required field: user"
only if the body also omits `user` — otherwise it would silently trust the
body's value, which is exactly the bug.

There is no existing `handlers_repos_test.go`; `SyncRepos` currently has no
unit test coverage at all (the e2e suite only asserts that the
`mctl_sync_repos` MCP tool name is registered, not its behavior).

## Proposed solution

1. **Handler (`internal/api/handlers_repos.go`, `SyncRepos`)**: remove the
   `User` field from the anonymous request struct entirely, so the decoded
   struct only has `Team`. `encoding/json` ignores unknown JSON keys by
   default (no `DisallowUnknownFields` is set anywhere in this codebase, per
   grep), so a client that still sends `{"user": "..."}` in the body keeps
   working — the value is simply dropped, never read.
   - Require `user != nil` up front and return `401 Unauthorized` if it is
     nil (matching `VerifyDomain`/`DeleteDomain`'s fail-closed pattern for
     mutating identity-sensitive endpoints). This subsumes the old
     "missing required field: user" 400 case: previously that branch only
     fired when both the body and the auth context lacked a user; now the
     nil-user check is the single, first gate.
   - Keep the existing `user.HasTenantAccess(req.Team)` 403 check unchanged,
     now unconditionally reachable (since `user` is guaranteed non-nil past
     the new check) — this also lets us drop the now-redundant `user != nil
     &&` guard on that line.
   - Build the upstream Backstage URL with `user.ID` directly instead of
     `req.User`.
   - Update the handler's doc comment (currently `// POST /api/v1/repos/sync
     body: {"team": "admins", "user": "mashkovd"}`) to drop the misleading
     `user` example and note that identity comes from the auth context.

2. **MCP tool (`internal/mcp/server.go`, `toolSyncRepos`)**: keep the `user`
   parameter (removing it would be a breaking change for any existing MCP
   client configuration) but update its description to state plainly that it
   is accepted for backward compatibility and ignored by the server, which
   always uses the authenticated caller's identity. This keeps the MCP
   surface truthful without forcing a client-facing schema change in this
   proposal.

3. **OpenAPI spec (`internal/openapi/openapi.yaml`)**: mark the `user`
   property under `POST /api/v1/repos/sync` as `deprecated: true` with a
   description noting it is ignored server-side.

4. **Tests (new `internal/api/handlers_repos_test.go`)**: follow the
   established pattern in `handlers_domains_test.go` (`captureBackstage`-style
   httptest server, `withUser` helper) to add:
   - A test posting `{"team": "labs", "user": "someone-else"}` with
     `auth.User{ID: "real-caller", Groups: []string{"labs"}}` in context, and
     asserting the upstream Backstage request's `user` query parameter is
     `real-caller`, not `someone-else`.
   - A test with no `user` field in the body (today's default-fill path)
     asserting the same authenticated-ID behavior, so both call shapes are
     pinned.
   - A test with no user in context asserting `401 Unauthorized` and zero
     upstream calls.
   - A test asserting the existing cross-tenant 403 (`HasTenantAccess` false)
     still produces zero upstream calls.

## Alternatives

1. **Keep `req.User` and just stop honoring it (e.g. `_ = req.User`).**
   Rejected: leaves a decoded-but-discarded field in the struct that invites
   a future contributor to "fix" the seemingly-unused field by wiring it back
   up. Removing the field entirely is more resistant to regression and is
   the issue's own preferred option.

2. **Reject any request whose body includes a non-empty, mismatched `user`
   field with 400 Bad Request** (explicit rejection instead of silent
   ignore). Rejected for this proposal: it requires decoding into a struct
   that still contains `User string` (reintroducing the field the issue asks
   to remove), and it breaks any existing client that has been sending its
   own `user` field as a no-op label. Silent ignore is simpler, matches the
   issue's first suggested option, and is fully sufficient to close the
   authorization gap (the acceptance criterion is "handler behavior depends
   only on the auth context", not "the endpoint validates the body's user
   field").

3. **Preserve the old "missing required field: user" 400 for nil user
   instead of moving to fail-closed 401.** Rejected: with `req.User` removed,
   a nil-user request has no identity source at all, so "missing field"
   framing no longer fits: the honest response is "you are not authenticated"
   (401), and it makes `SyncRepos` consistent with the other mutating,
   identity-sensitive handlers in `handlers_domains.go` instead of a
   one-off case.

## Platform impact

- **Backward compatibility**: clients that send `{"user": "..."}` in the
  body continue to get `200`/whatever Backstage returns — the field is just
  silently ignored, not rejected. Clients that relied on impersonating
  another user via this field lose that (intended) capability; this is the
  security fix.
- **Migrations**: none. No schema, no persisted state.
- **Resource impact**: none — same call shape to Backstage, one query
  parameter's value source changes.
- **Risk**: deployments that run without `AuthMiddleware` configured
  (`opts.AuthMiddleware == nil` in `internal/api/router.go`, e.g. certain
  local/dev setups) will now get `401` from `SyncRepos` instead of a
  best-effort body-derived sync, since there is no longer any identity
  source when `user` is nil. Mitigation: this matches how `VerifyDomain` and
  `DeleteDomain` already behave in the same no-auth-middleware scenario, so
  it does not introduce a new inconsistency — it removes one. If a
  legitimate no-auth deployment mode needs `SyncRepos` to keep working, that
  is a separate, explicit product decision, not an accidental side effect of
  this security fix.
- **Rollback risk**: low; the change is confined to one handler, one MCP
  tool description string, and one OpenAPI annotation. See `tasks.md` for
  the rollback procedure.
