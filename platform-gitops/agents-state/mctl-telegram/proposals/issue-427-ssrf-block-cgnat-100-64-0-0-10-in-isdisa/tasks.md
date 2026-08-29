# Tasks: issue-427-ssrf-block-cgnat-100-64-0-0-10-in-isdisa

- [ ] 1. Add the `cgnatBlock` package-level `*net.IPNet` constant
      (`100.64.0.0/10`) to `internal/telegram/fetchmedia.go`, next to the
      existing sentinel errors / `maxFetchRedirects` const block — DoD: the
      package compiles (`go build ./...`); the value is a package-level
      `var`, not computed inside `isDisallowedIP`.
- [ ] 2. Extend `isDisallowedIP` in `internal/telegram/fetchmedia.go` with
      `|| cgnatBlock.Contains(ip)`, and update its doc comment
      (fetchmedia.go:59-62) to list CGNAT alongside the ranges it already
      documents (depends on 1) — DoD: `go vet ./...` and `golangci-lint run`
      pass with no new findings; the doc comment names `100.64.0.0/10` /
      RFC 6598 explicitly.
- [ ] 3. Extend the `TestIsDisallowedIP` table in
      `internal/telegram/fetchmedia_test.go` with `100.64.0.1` (want=true),
      `100.127.255.254` (want=true), `100.63.255.255` (want=false),
      `100.128.0.0` (want=false) (depends on 2) — DoD: `go test
      ./internal/telegram/... -run TestIsDisallowedIP -v` passes and fails
      if the CGNAT term in task 2 is reverted.
- [ ] 4. Add `TestFetchGuardedURL_DisallowedIP_CGNATViaHostname` to
      `internal/telegram/fetchmedia_test.go`, mirroring
      `TestFetchGuardedURL_DisallowedIP_ViaHostname` with the fake `lookup`
      returning `net.ParseIP("100.64.0.1")`, asserting `ErrFetchDisallowedIP`
      and that `dial` is never invoked (depends on 2) — DoD: the new test
      fails against pre-fix code (verify by temporarily reverting task 2
      locally) and passes with the fix in place.
- [ ] 5. Re-run the full existing `fetchmedia_test.go` suite, in particular
      `TestFetchGuardedURL_Success` (uses allowed test IP `93.184.216.1`)
      and `TestFetchGuardedURL_DisallowedIP_Direct` /
      `_ViaHostname` (depends on 2, 3, 4) — DoD: `go test
      ./internal/telegram/...` passes with zero regressions, demonstrating
      public media fetch is unaffected and the pre-existing disallowed-range
      coverage (loopback, link-local incl. `169.254.169.254`, RFC 1918,
      unspecified, multicast) is unchanged.

## Tests

- [ ] T1. `isDisallowedIP(100.64.0.1)` == true (issue's literal acceptance
      criterion).
- [ ] T2. `isDisallowedIP(100.127.255.254)` == true (top boundary of the
      /10).
- [ ] T3. `isDisallowedIP(100.63.255.255)` == false and
      `isDisallowedIP(100.128.0.0)` == false (both boundaries just outside
      the /10, guarding against an off-by-one mask).
- [ ] T4. `isDisallowedIP(169.254.169.254)` == true (already present in the
      table; confirm it still passes — this is the issue's explicit
      "verify metadata... ranges are covered" ask).
- [ ] T5. `isDisallowedIP(93.184.216.1)` == false and
      `isDisallowedIP(8.8.8.8)` == false (already present; confirm public
      IPs are unaffected).
- [ ] T6. `fetchGuardedURL` against a hostname whose injected `lookup`
      resolves to `100.64.0.1` returns `ErrFetchDisallowedIP` and never
      calls `dial` (new `TestFetchGuardedURL_DisallowedIP_CGNATViaHostname`)
      — proves the post-DNS-resolution path, not just the raw predicate.
- [ ] T7. `TestFetchGuardedURL_Success` (public `httptest.NewTLSServer`
      fetch via the existing `93.184.216.1` fake-resolved address) still
      passes unmodified — proves public media fetch unaffected.
- [ ] T8. `TestFetchGuardedURL_RedirectToDisallowedIP` still passes
      unmodified — confirms the redirect-hop re-check path (shared code with
      the new CGNAT check) is untouched by this change.

## Rollback

This is a single, additive change confined to one predicate function and its
tests in `internal/telegram/fetchmedia.go` / `fetchmedia_test.go`, with no
config, schema, or external state changes. To roll back:
- Revert the merge commit (this repo squash-merges one commit per PR per
  `CLAUDE.md`, so a single `git revert <sha>` on `main` fully undoes the
  change) and redeploy.
- No data migration, cache invalidation, or downstream service coordination
  is needed — the change only affects which addresses `FetchGuardedURL`
  will dial to on future requests; no session, database, or on-disk state is
  touched.
- If reverted, media fetches to `100.64.0.0/10` addresses would once again
  succeed instead of being rejected, restoring pre-fix (vulnerable)
  behavior — acceptable only as a temporary measure while investigating a
  regression, not a long-term option.

## Operator decisions (approve, 2026-08-29)

- Accepted as proposed. One correction: current line numbers on main are
  59-64 (doc comment) and 65-72 (isDisallowedIP), not 63-71 — re-anchor
  before editing. No other changes; callers need no modification.
