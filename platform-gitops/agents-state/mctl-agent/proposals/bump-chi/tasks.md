# Tasks: bump-chi

- [ ] 1. Update `go.mod` — change `github.com/go-chi/chi/v5` from `v5.2.1` to `v5.2.5` —
  DoD: `grep chi go.mod` shows `github.com/go-chi/chi/v5 v5.2.5`; no other module versions are
  changed unexpectedly.

- [ ] 2. Run `go mod tidy` to update `go.sum` (depends on 1) —
  DoD: `go mod tidy` exits 0; `go.sum` is updated to include the v5.2.5 checksums; `go build ./...`
  exits 0.

- [ ] 3. Review router configuration for `RedirectSlashes` and `RouteHeaders` usage (depends on 2) —
  DoD: a code comment or PR note documents whether `RedirectSlashes` is active and confirms that
  no handler is expected to be invoked more than once per request via `RouteHeaders`.

- [ ] 4. Run the full test suite (depends on 2) —
  DoD: `go test ./...` exits 0; no previously-passing tests fail.

- [ ] 5. Open a PR with the changes; ensure CI passes (depends on 3, 4) —
  DoD: CI is green; PR description references CVE-2025-69725 (GHSA-mqqf-5wvp-8fh8) and this
  proposal; PR is tagged as a security patch.

## Tests

- [ ] T1. Run the existing HTTP-layer integration tests (if any) against the updated chi version
  and confirm all routing, middleware, and response-code assertions pass —
  DoD: no test regressions introduced by the chi version change.

- [ ] T2. Add a test `TestNoOpenRedirectOnTrailingSlash` that sends a request with a crafted URL
  designed to trigger the CVE-2025-69725 redirect and asserts that the response `Location` header
  (if present) does not point to an external host —
  DoD: test exists, passes with chi v5.2.5, and is documented with a reference to
  GHSA-mqqf-5wvp-8fh8.

- [ ] T3. Confirm `govulncheck ./...` (or equivalent) reports no outstanding chi CVEs after the
  upgrade —
  DoD: scanner exits 0 or flags only informational findings unrelated to chi.

## Rollback
Revert the `go.mod` and `go.sum` changes via `git revert <merge-commit>` and redeploy the previous
image via ArgoCD sync. No database or configuration changes need to be undone. Because v5.2.1
pre-dates the CVE-2025-69725 regression (the vulnerability was introduced in v5.2.2), rolling back
to v5.2.1 does not re-expose the open-redirect bug — however, the `RouteHeaders` double-invocation
bug would be re-introduced. Rollback should be treated as temporary and re-attempted promptly.
