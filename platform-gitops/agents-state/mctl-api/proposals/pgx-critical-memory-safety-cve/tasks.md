# Tasks: pgx-critical-memory-safety-cve

- [ ] 1. Mark `proposals/pgx-upgrade-v592` as superseded by this proposal in review notes — DoD:
      cross-reference added in both proposals; no duplicate parallel merge risk.
- [ ] 2. Bump `github.com/jackc/pgx/v5` to `v5.9.2` in `go.mod`, run `go mod tidy` — DoD: `go.sum`
      updated, build succeeds locally.
- [ ] 3. Audit all SQL call-sites for simple-protocol usage combined with dollar-quoted literals
      (depends on 2) — DoD: written confirmation (PR description or code comment) that either (a)
      no call-site uses the simple protocol with attacker-controlled dollar-quoted values, or (b)
      any such call-site is migrated to the extended protocol.
- [ ] 4. Run `govulncheck ./...` (depends on 2) — DoD: zero findings for CVE-2026-33815,
      CVE-2026-33816, CVE-2026-41889.
- [ ] 5. Run full Postgres integration test suite (depends on 2) — DoD: all tests pass, no
      regression in query semantics or connection-pool behaviour.
- [ ] 6. Deploy via mctl-gitops → ArgoCD to `admins` tenant (depends on 2, 4, 5) — DoD: ArgoCD
      reports `Healthy`/`Synced` for `admins-mctl-api`; version bump visible in
      `current-version.md` update.

## Tests
- [ ] T1. `govulncheck ./...` reports zero findings for all three CVE IDs.
- [ ] T2. Full existing integration test suite passes against a live Postgres instance.
- [ ] T3. Manual smoke test: identity read/write and audit-log append flows function correctly
      post-upgrade.
- [ ] T4. Simple-protocol / dollar-quoted-literal audit (Task 3) documented and signed off.

## Rollback
Revert the `go.mod`/`go.sum` change to pin `pgx/v5` back to `5.8.x` and redeploy via ArgoCD
(previous image tag is retained by mctl-gitops history). Since no schema or data-format changes
are introduced, rollback is a pure code revert with no data-migration concerns.
