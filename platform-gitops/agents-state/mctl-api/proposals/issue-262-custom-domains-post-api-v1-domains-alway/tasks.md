# Tasks: issue-262-custom-domains-post-api-v1-domains-alway

Tasks 1-9 and 12-13 are in `mctlhq/mctl-api`. Tasks 10-11 are in
`mctlhq/mctl-gitops` and must be opened as a companion PR; task 14 is a
follow-up issue in `mctlhq/mctl-portal`.

- [ ] 1. Add `internal/domains/types.go` — `Domain` struct (id, team, service,
      domain, status, verification_token, created_by, created_at, updated_at,
      verified_at, last_error) plus status constants
      `pending|verified|active|failed`, following `internal/alerts/types.go`.
      DoD: `go build ./...` passes; JSON tags match the response fields named in
      design.md.
- [ ] 2. Add `internal/domains/store.go` — pgx pool store with the
      `domainSchema` constant from design.md and `NewStore(ctx, connStr)`,
      copying the shape of `internal/alerts/store.go` (idempotent
      `CREATE TABLE IF NOT EXISTS`, `slog` init line). Methods: `Create`
      (idempotent on `(team, service, domain)`, `ErrDomainConflict` when the
      hostname belongs to another team), `ListByTeam`, `Get`, `GetByDomain`,
      `SetStatus`, `MarkVerified`, `Delete`. (depends on 1) — DoD: `go vet` and
      `golangci-lint` clean; errors wrapped as `fmt.Errorf("domains store: ...: %w", err)`.
- [ ] 3. Add `internal/domains/verify.go` — `Verifier` over `net.Resolver` with
      a configurable resolver address; `Verify` checks
      `TXT _mctl-challenge.<domain>` for `mctl-domain-verification=<token>`,
      then falls back to `LookupCNAME` matching `{team}-{service}.<platform_domain>`.
      Returns a `Result{Verified bool, Method string, Reason string}`; never
      returns an error for "not configured yet". (depends on 1) — DoD: resolver
      is injectable so tests need no real DNS.
- [ ] 4. Wire the store in `cmd/api/main.go`: `DOMAINS_DB_URL` falling back to
      `AUDIT_DB_URL` through `postgresURL`/`initStore` (same block as the alert
      store, lines 169-189), plus `PLATFORM_DOMAIN` (default `mctl.ai`) and
      `DNS_RESOLVER_ADDR` via `envOr`; add `DomainStore`, `PlatformDomain`,
      `DomainVerifier` to `api.Options` in `internal/api/router.go`, with a
      startup `slog.Warn` when the store is nil (mirroring the
      `BACKSTAGE_GITHUB_APP_CONNECT_TOKEN` warning at router.go line 129).
      (depends on 2, 3) — DoD: API starts with and without the env vars; without
      it, domain routes 503.
- [ ] 5. Rewrite `internal/api/handlers_domains.go` reads: `ListDomains` uses
      `DomainStore.ListByTeam`, fails closed on a nil user (401), keeps the
      `HasTenantAccess` 403 and the `{"domains":[...]}` envelope; delete
      `authorizeBackstage`, `backstageDomainIDs`, and `backstageDomainsClient`.
      (depends on 4) — DoD: no reference to `BackstageInternalURL` remains in
      this file; `handlers_write.go`'s `notifyBackstage` use of `BackstageToken`
      is untouched.
- [ ] 6. Rewrite `AddDomain`: nil-user 401, `HasTenantAccess` 403,
      platform-domain rejection 400 reusing the #263 wording (equal to or
      ending in `.<PlatformDomain>`), mint the verification token, `Create`,
      return 201 with `challenge_record`, `challenge_value`, `cname_target`;
      200 on idempotent re-registration, 409 on cross-team conflict with no
      owner disclosure. (depends on 5) — DoD: the issue's exact request body
      for `seerrsense.mctl.ai` returns 400 with the GitOps instruction, and a
      tenant-owned hostname returns 201.
- [ ] 7. Rewrite `authorizeDomainMutation`, `VerifyDomain`, `DeleteDomain`
      against the store; add `POST /api/v1/domains/verify` (body
      `{team, service, domain}`) returning
      `{verified, method, reason, expected_record, expected_value}` with 200 on
      a negative verdict. (depends on 6) — DoD: an id the caller cannot see
      still 404s rather than 403s; admins short-circuit as today.
- [ ] 8. Add `PATCH /api/v1/domains/{id}` restricted to `user.IsService()`,
      accepting `{status, error}` limited to `verified|active|failed`.
      (depends on 7) — DoD: a human admin token gets 403; the service token
      moves the row and updates `updated_at`.
- [ ] 9. Register the two new routes in `internal/api/router.go` next to lines
      277-281 and update the comment (no longer "proxied to Backstage");
      refresh the `BACKSTAGE_TOKEN` row in `README.md` line 135 to say it is
      catalog-sync only, and document `DOMAINS_DB_URL`, `PLATFORM_DOMAIN`,
      `DNS_RESOLVER_ADDR`. (depends on 8) — DoD: `go test ./...` green;
      `e2e/e2e_test.go` `TestE2E_Domains` still passes (it accepts 200/404/502/503).
- [ ] 10. mctl-gitops: in
      `platform-gitops/argo-workflows/cluster-templates/wft-add-custom-domain.yaml`,
      replace the `dig +short CNAME "${DOMAIN}"` step with a `curl` to
      `POST $MCTL_API_URL/api/v1/domains/verify` using the platform service
      token, failing when `.verified != true` and echoing `reason` and
      `expected_record`. Leave the platform-domain rejection step untouched.
      (depends on 7) — DoD: a Cloudflare-proxied tenant hostname with the TXT
      record verifies; one without it fails with an actionable message.
- [ ] 11. mctl-gitops: add a final workflow step PATCHing the domain row to
      `active` on success and `failed` (with the error) via the onExit handler;
      mount the mctl-api service token in the `argo-workflows` namespace and
      drop `backstage-workflow-token` from this template.
      (depends on 8, 10) — DoD: after a successful run, `GET /api/v1/domains`
      shows the row as `active`.
- [ ] 12. Update `mctl_add_custom_domain` in `internal/mcp/server.go` (line
      1422) to surface `challenge_record` / `challenge_value` from the 201 and
      instruct the user to create the TXT record; update `mctl_verify_domain`
      (line 1534) wording from "CNAME record" to the TXT challenge, keeping the
      CNAME fast path mentioned. Do not add or remove tools. (depends on 7) —
      DoD: `internal/mcp/server_test.go` still asserts `expected 73 tools` and
      passes.
- [ ] 13. Update `add-custom-domain` / `remove-custom-domain` descriptions in
      `internal/operations/registry.go` (lines 349-375) to describe TXT
      verification, keeping the existing platform-domain sentence verbatim.
      (depends on 12) — DoD: `internal/operations/registry_test.go` passes.
- [ ] 14. Open a follow-up issue on `mctlhq/mctl-portal`: repoint the
      `custom-domains` plugin UI at `GET /api/v1/domains` (or retire the
      plugin's table), now that mctl-api is the system of record. — DoD: issue
      filed and linked from #262.

## Tests

- [ ] T1. `internal/domains/store_test.go` — Create/idempotency/cross-team
      conflict/List/Get/SetStatus/Delete against the same test harness
      `internal/alerts/store_test.go` uses (skips when no test DB URL is set).
- [ ] T2. `internal/domains/verify_test.go` — with a stub resolver: TXT match
      verifies; TXT present but wrong token does not; no TXT plus a CNAME to
      the platform host verifies via the fast path; Cloudflare-shaped answer
      (no CNAME, edge A records only) plus a correct TXT verifies — the
      regression the issue reports.
- [ ] T3. `internal/api/handlers_domains_test.go` — rewrite the existing
      Backstage-bearer tests (`TestDomainProxiesSendBearerToken`,
      `TestDomainProxiesOmitEmptyToken`) into store-backed tests; the proxy
      invariant they pinned no longer exists. Add: nil user → 401 on GET and
      POST (today's fail-open gap); non-member → 403; platform-domain hostname
      → 400 with the GitOps instruction; happy path → 201 including
      `challenge_record` and `challenge_value`.
- [ ] T4. Verify-endpoint tests: negative verdict returns 200 with
      `verified:false` and the expected record, not an error status; unknown id
      → 404; `POST /domains/verify` resolves by `{team, service, domain}`.
- [ ] T5. PATCH callback tests: service principal (`auth.NewServiceUser()`)
      may set `active`/`failed`; a human admin gets 403; an invalid status
      value gets 400.
- [ ] T6. Nil-store tests: every `/api/v1/domains*` route returns 503 with
      "domains registry not configured" when `DomainStore` is nil.
- [ ] T7. `go test ./...`, `go vet ./...`, `golangci-lint run`, and
      `cd e2e && go test -v` (domains e2e still passes).

## Rollback

The change is additive at the data layer, so rollback is a redeploy of the
previous mctl-api image tag (`mctl_rollback_service team=platform
component=mctl-api target_tag=<previous>`); the `custom_domains` table is
simply ignored by the old binary, which resumes proxying to Backstage — i.e.
back to the 401 reported in the issue, with no data loss. Revert the mctl-gitops
workflow commit (tasks 10-11) separately to restore the `dig +short CNAME`
step and the `backstage-workflow-token` mount; that revert is independent of
the API rollback as long as the previous image is redeployed at the same time,
since the old API has no `/api/v1/domains/verify` route. If only the DNS
verification proves problematic, set the TXT check aside without a full
rollback by having the workflow keep calling `/domains/verify` while
`DNS_RESOLVER_ADDR` points at a resolver you control.
