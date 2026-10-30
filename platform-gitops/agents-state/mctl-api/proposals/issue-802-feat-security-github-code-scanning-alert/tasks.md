# Tasks: issue-802-feat-security-github-code-scanning-alert

- [ ] 1. Add `CodeScanningConfig` / parser for `SECURITY_GITHUB_CODE_SCANNING`. Validate fixed provider ref, closed action vocabulary, non-empty repository map/tool list/tenants, normalize repository keys, and fail this route closed on malformed config.
- [ ] 2. Add `mctl_security_webhook_deliveries_total{provider,result}` with closed result labels `accepted|duplicate|ignored|signature_invalid|store_unavailable|rejected`, pre-initialized for `github-code-scanning`.
- [ ] 3. Add a minimal GitHub `code_scanning_alert` payload struct plus a pure mapper. Pin supported fields/actions with fixtures/table tests derived from current authoritative GitHub webhook documentation.
- [ ] 4. Make the source identity stable: `source_finding_id = github:<full_name>/code-scanning/<alert.number>`. Branch/ref/commit/action MUST NOT be appended to it; keep such values only as observation/evidence context.
- [ ] 5. Map subject as repository + path + location + rule id; map the six reviewed actions to `present|fixed|withdrawn`; use the event/instance commit only when the webhook actually supplies one; never fabricate a revision.
- [ ] 6. Add `Options.CodeScanningWebhookSecret`, `Options.CodeScanningConfig` and a narrow `SecurityIngester` test seam. Mount `POST /api/v1/security/webhooks/github-code-scanning` outside bearer middleware beside the existing GitHub webhook route.
- [ ] 7. Implement HMAC/body/allowlist handling: dedicated secret, constant-time signature check, 1 MiB cap, signed non-target events/actions/repos/tools ignored, malformed allowlisted events rejected, no secret/signature/body logging.
- [ ] 8. Build the store `ProviderContext` only from server configuration with `Ref="github-code-scanning"` and `PrincipalID="service:security-provider:github-code-scanning"`. Add a test proving payload fields cannot alter Ref, PrincipalID, tenant or strength.
- [ ] 9. Call #774 `IngestBatch` synchronously under a 5 s bound. Only `created`/`duplicate` may return 2xx; nil store, timeout, returned error or `internal_error` -> 503; other store rejection -> 4xx. Audit accepted/duplicate with the same canonical principal id.
- [ ] 10. Wire `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` and `SECURITY_GITHUB_CODE_SCANNING` in `cmd/api/main.go`: secret too short/equal to `GITHUB_WEBHOOK_SECRET` disables receiver; repository tenants must be inside the `SECURITY_PROVIDERS[github-code-scanning]` tenant set; bad config disables receiver without taking down mctl-api.
- [ ] 11. Helm: add optional `securityCodeScanning` rendering for the non-secret config and render tests. Secret material remains external and is wired by mctl-gitops#2103.
- [ ] 12. Update OpenAPI/docs/PR description with the public HMAC route, provider-auth decision, final env names and metric name. Do not add a provider bearer token for the in-process receiver.
- [ ] 13. Run `go fmt`, `go vet`, `golangci-lint`, `go test ./...` and repository-required CI. Open/land the implementation PR only after reviews have no P1/P2.
- [ ] 14. **Release gate, not implementer action:** after merge, observe the normal mctl-api release automation/process produce a tag containing the receiver and its deployment. Then record the released tag plus `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`, `SECURITY_GITHUB_CODE_SCANNING` and `mctl_security_webhook_deliveries_total` on mctl-gitops#2103. Do not manually cut/tag a release from the implementation task.

## Required tests

- [ ] T1. Valid signed allowlisted delivery gives 202 accepted; fake ingester receives one observation with route-bound provider ref, tenant, stable source finding id, mapped subject/action/delivery id, and `ProviderContext.PrincipalID == service:security-provider:github-code-scanning`.
- [ ] T2. Payload attempts to spoof provider/principal/tenant/tool authority do not change ProviderContext or lifecycle inputs; provider prose remains bounded untrusted data.
- [ ] T3. Missing/bad signature and a body signed with `GITHUB_WEBHOOK_SECRET` give 401 and no store call.
- [ ] T4. Non-code-scanning event plus disallowed repo/tool/action each give 2xx ignored and no store call.
- [ ] T5. Mapping table covers every supported action and current GitHub payload revision/ref behavior, including user-only actions with no revision.
- [ ] T6. Stable source identity: created/reopened/fixed/closed observations for alert number N on different refs all use exactly `github:<repo>/code-scanning/N`; ref changes do not create a new source id.
- [ ] T7. Redelivery of the same GUID/body returns duplicate without a second observation; test with fake and real store when `TEST_DATABASE_URL` is available.
- [ ] T8. Nil store, store error, timeout and rejected/internal_error each return 503 `store_unavailable`; allowlisted non-internal rejection returns 4xx rejected.
- [ ] T9. Oversized/malformed/missing required fields are rejected and counted; secret/signature/raw body never appear in captured logs.
- [ ] T10. Unset/invalid receiver config gives 503 while unrelated mctl-api routes remain available; secret equality/short-secret cases are covered at wiring level.
- [ ] T11. Metric series are present from startup and exactly one result is incremented for every handled request after configuration validation.
- [ ] T12. Audit/store provenance uses `service:security-provider:github-code-scanning` consistently on accepted/duplicate deliveries.

## Rollback

Unset the dedicated receiver secret/config or roll back the mctl-api image. The route becomes unavailable without changing #774 data or other API routes. Recorded observations are append-only and remain auditable.
