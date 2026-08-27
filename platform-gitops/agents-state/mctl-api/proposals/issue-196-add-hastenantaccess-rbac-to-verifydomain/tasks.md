# Tasks: issue-196-add-hastenantaccess-rbac-to-verifydomain

- [ ] 1. Add a `backstageDomainIDs(ctx, baseURL, team string) (map[string]struct{}, error)`
      helper in `internal/api/handlers_domains.go` that calls
      `GET {baseURL}/api/custom-domains/domains?team=<team>` via
      `backstageDomainsClient` + `authorizeBackstage` (same pattern as
      `ListDomains`), decodes the `{"domains":[{"id": "..."}]}` shape (same
      fields the MCP tool already decodes at `internal/mcp/server.go:1550`),
      and returns the set of ids owned by `team`. Returns an error on
      transport failure or non-2xx upstream status. — DoD: helper compiles,
      is unit-testable with an `httptest.Server` stand-in for Backstage, and
      is not yet called from anywhere (no behavior change).

- [ ] 2. Update `VerifyDomain` (handlers_domains.go:157) (depends on 1):
      read `team := r.URL.Query().Get("team")`; if empty, `400` with
      `{"error":"missing required param: team"}`. Read `user :=
      auth.UserFromContext(r.Context())`; if `user != nil &&
      !user.HasTenantAccess(team)`, `403` with
      `{"error":"access denied to team"}`. Call `backstageDomainIDs(ctx,
      baseURL, team)`; on error, `502` with `{"error":"backstage
      unavailable"}`; if the URL's `id` is not in the returned set, `404`
      with `{"error":"domain not found"}`. Only then proceed with the
      existing proxy call to `POST {baseURL}/api/custom-domains/domains/{id}/verify`,
      unchanged. — DoD: `go build ./...` passes; behavior for a
      same-team/admin/nil-user caller with a valid id is byte-identical to
      today's response.

- [ ] 3. Update `DeleteDomain` (handlers_domains.go:191) (depends on 1) with
      the identical guard sequence as task 2, ending in the existing
      `DELETE {baseURL}/api/custom-domains/domains/{id}` proxy call. — DoD:
      same as task 2, applied to delete.

- [ ] 4. Update `toolVerifyDomain` in `internal/mcp/server.go` (line ~1561)
      to send `POST /api/v1/domains/` + `d.ID` + `/verify?team=` +
      `url.QueryEscape(team)` instead of the current teamless call, since
      `team` is already in scope from the tool's args. (depends on 2) —
      DoD: `go build ./...` passes; the tool still verifies every domain
      returned by its own list-by-team-and-service call.

- [ ] 5. Run `go fmt ./...`, `go vet ./...`, and `golangci-lint run` per
      `CLAUDE.md` conventions, fixing any new findings in the touched
      files. (depends on 2, 3, 4) — DoD: all three commands exit 0.

## Tests

- [ ] T1. `VerifyDomain`/`DeleteDomain`, cross-tenant: user in group
      `team-a` calls verify/delete with `?team=team-b` (a team they lack
      access to) -> `403`, and assert zero calls reached the stub Backstage
      verify/delete route (only the list-by-team call, if any, may have
      fired — assert it did NOT, since the 403 must short-circuit before
      any upstream call).
- [ ] T2. `VerifyDomain`/`DeleteDomain`, id/team mismatch: user in group
      `team-a` calls verify/delete with `?team=team-a` (own team, allowed)
      but `id` is only present in the stub Backstage's `team-b` domain
      list -> `404`, and assert the verify/delete route was never called
      upstream (only the list call was).
- [ ] T3. `VerifyDomain`/`DeleteDomain`, own tenant success: user in group
      `team-a` calls verify/delete with `?team=team-a` and `id` present in
      the stub's `team-a` list -> proxied call fires, response status/body
      from the stub is passed through unchanged (extend the existing
      `TestDomainProxiesSendBearerToken` table or add a sibling test using
      the same `captureBackstage` helper, now also stubbing the list
      endpoint).
- [ ] T4. `VerifyDomain`/`DeleteDomain`, missing `team` param -> `400`,
      zero upstream calls.
- [ ] T5. `VerifyDomain`/`DeleteDomain`, nil user in context (handler
      invoked directly as `TestDomainProxiesSendBearerToken` does today) ->
      tenant check is skipped; existing test behavior (bearer token
      attached, call succeeds) must keep passing unmodified, proving no
      regression for that existing coverage.
- [ ] T6. `VerifyDomain`/`DeleteDomain`, admin user (`Groups:
      []string{"admins"}`) -> allowed regardless of `team`/`id` ownership,
      matching `HasTenantAccess`'s admin short-circuit
      (`internal/auth/oidc.go:56`).
- [ ] T7. `ListDomains`/`AddDomain` existing tests
      (`TestDomainProxiesSendBearerToken`,
      `TestDomainProxiesOmitEmptyToken`) continue to pass unmodified,
      proving no regression to the two handlers this proposal does not
      touch.
- [ ] T8. `toolVerifyDomain` MCP tool: verify call includes `team` in the
      proxied path/query (unit test against the mock HTTP client the MCP
      server tests already use, if one exists for this tool — otherwise a
      focused test asserting the constructed request path).

## Rollback

Revert the commit(s) touching `internal/api/handlers_domains.go` and
`internal/mcp/server.go`. Both changes are additive gating logic in front
of unchanged proxy calls — no data migration, no schema change, no state
to unwind. If a partial rollback is needed under pressure, reverting just
`VerifyDomain`/`DeleteDomain` back to their pre-change form (drop the
`team` requirement and the ownership check) immediately restores the prior
(vulnerable) behavior, so prefer a full revert plus a fast-follow rather
than a partial one. No feature flag is introduced; there is nothing to
toggle off short of redeploying the previous image tag
(`mctl_rollback_service` to the prior git tag is sufficient).
