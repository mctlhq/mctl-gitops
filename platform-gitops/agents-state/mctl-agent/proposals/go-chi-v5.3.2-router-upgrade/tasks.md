# Tasks: go-chi-v5.3.2-router-upgrade

- [ ] 1. Bump `github.com/go-chi/chi/v5` from 5.2.1 to 5.3.2 in
      `go.mod`/`go.sum` (`go get github.com/go-chi/chi/v5@v5.3.2 && go
      mod tidy`) — DoD: `go.mod`/`go.sum` reference 5.3.2, module
      resolves cleanly.
- [ ] 2. Audit all `Mount()`/`Route()` registrations across the REST
      API, AlertManager webhook, Telegram webhook, and MCP endpoint for
      collisions, and add/extend a table-driven test that registers
      the current route tree and asserts no collision errors (depends
      on 1) — DoD: a passing table-driven test enumerating each
      registered route group and its expected handler.
- [ ] 3. Grep the codebase for `RedirectSlashes` usage and resolve
      CVE-2025-69725 exposure (depends on 1) — DoD: one of (a) recorded
      finding "middleware not used, not exposed", or (b) recorded
      verification result "used, confirmed fixed in 5.3.2 by
      [evidence]", or (c) middleware removed/replaced with a safe
      trailing-slash handler and a regression test added for the fix.
- [ ] 4. Add/extend a table-driven test asserting the `Allow` header on
      a 405 response contains no duplicate methods, using an existing
      multi-method route (depends on 1) — DoD: passing test with at
      least one case exercising a route registered for 2+ methods.
- [ ] 5. Confirm whether mctl-agent uses chi's compress middleware with
      wildcard route patterns; if so, add a regression test for the
      wildcard-rejection fix (depends on 1) — DoD: either "not used,
      no-op" recorded, or a passing test confirming the fix behavior.
- [ ] 6. Run the full test suite and smoke-test all API endpoints
      locally (depends on 2, 3, 4, 5) — DoD: `go test ./...` passes;
      manual/scripted smoke test of `/api/v1/alerts`,
      `/api/v1/telegram`, `/api/v1/tickets`, `/api/v1/skills`, `/mcp`,
      `/healthz`, `/readyz` all return expected status codes.
- [ ] 7. Deploy via the normal ArgoCD sync path for
      `admins-mctl-agent` (depends on 6) — DoD: ArgoCD Application
      shows health=Healthy, syncStatus=Synced on the new revision.

## Tests
- [ ] T1. Table-driven test: route registration across all endpoint
      groups produces no Mount()/Route() collision errors.
- [ ] T2. Table-driven test: 405 response `Allow` header has no
      duplicate methods for a route registered with overlapping method
      handlers.
- [ ] T3. Targeted test/verification for CVE-2025-69725 exposure
      (either "not applicable" documentation or a passing
      redirect-safety test if `RedirectSlashes` is in use).
- [ ] T4. Regression test for the compress-middleware wildcard fix, if
      applicable to mctl-agent's route configuration.
- [ ] T5. Full existing test suite (`go test ./...`) passes unchanged.
- [ ] T6. Manual smoke test of all documented API endpoints against a
      locally built binary using chi 5.3.2.

## Rollback
Revert the `go.mod`/`go.sum` chi version pin from 5.3.2 back to 5.2.1
in a single revert commit and redeploy the previous known-good image
tag through ArgoCD. If the `RedirectSlashes` mitigation in task 3
changed application code (not just the dependency version), revert
that commit as well — it is independently revertable since it is
scoped to a single middleware usage site. No data migration was
performed, so no data-level rollback is needed.
