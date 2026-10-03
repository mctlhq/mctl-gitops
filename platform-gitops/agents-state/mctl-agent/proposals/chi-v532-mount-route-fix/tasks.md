# Tasks: chi-v532-mount-route-fix

- [ ] 1. Check the status of `go-chi-v5.3.2-router-upgrade` and
      `chi-redirect-cve-boundary-check` — DoD: known whether either is merged,
      in-flight, or not started, to avoid shipping a duplicate `go.mod` bump.
- [ ] 2. IF neither sibling proposal is merged: bump `github.com/go-chi/chi/v5` to
      v5.3.2 in `go.mod`/`go.sum` via
      `go get github.com/go-chi/chi/v5@v5.3.2 && go mod tidy` (depends on 1) — DoD:
      `go build ./...` succeeds.
- [ ] 3. Audit `Mount()`/`Route()` call sites across the AlertManager webhook, Telegram
      webhook, REST API, and MCP endpoint router registration code for any overlapping
      path-prefix pattern that could have triggered the pre-5.3.2 collision bug
      (depends on 2) — DoD: audit findings (collision-prone or clean) documented in the
      PR description.
- [ ] 4. Add or extend regression tests covering `Mount()`/`Route()` registration for
      all four router groups, asserting no handler is silently dropped (depends on 3)
      — DoD: tests pass on v5.3.2 and would have failed (or are documented as
      not-applicable, if no collision pattern exists) on v5.2.1.
- [ ] 5. Add a targeted test confirming 405 `Allow:` headers contain no duplicate HTTP
      methods for a route registered with multiple methods (depends on 2) — DoD: test
      passes.
- [ ] 6. Document that CVE-2025-69725 status is unchanged and closed (fix at v5.2.4+,
      pin was and remains outside the affected `>=5.2.2` range before this bump, and
      v5.3.2 is a superset fix version after it) — no separate audit needed (depends
      on 2) — DoD: note added to the PR description; `chi-redirect-cve-boundary-check`
      and `go-chi-v5.3.2-router-upgrade` marked as closed/superseded once this PR
      merges (or vice versa, per task 1's outcome).
- [ ] 7. Manually spot-check REST API response content types against the new default
      compressible types (`text/markdown`, `text/csv`, `text/vtt`) introduced in
      v5.3.2 (depends on 2) — DoD: no unintended compression behavior change observed
      for existing endpoints.

## Tests
- [ ] T1. Full existing router-registration and middleware test suite passes on
      v5.3.2 with no route, method, or response-contract changes.
- [ ] T2. Mount()/Route() collision regression tests for all four router groups (see
      task 4) pass.
- [ ] T3. 405 `Allow:` header deduplication test (see task 5) passes.
- [ ] T4. Manual content-type/compression spot-check (see task 7) produces no
      surprises.

## Rollback
Revert the `go.mod`/`go.sum` bump back to v5.2.1 in a single commit — this proposal
makes no application-level route or handler changes beyond added test coverage, so
rollback is a pure dependency-version revert. Redeploy via ArgoCD sync to the previous
`admins-mctl-agent` revision if a full rollback is needed. No data migrations involved.
If this proposal was closed as superseded by one of the sibling chi-upgrade proposals
(per task 1/6), follow that proposal's rollback plan instead.
