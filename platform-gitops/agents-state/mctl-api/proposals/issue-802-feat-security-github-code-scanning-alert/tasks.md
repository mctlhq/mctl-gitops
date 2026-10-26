# Tasks: issue-802-feat-security-github-code-scanning-alert

- [ ] 1. Add `CodeScanningConfig` and `ParseCodeScanningConfig` in `internal/api/handlers_security_code_scanning.go`. DoD: empty input returns nil; malformed JSON, a foreign `provider_ref`, an unknown action, an empty repository map, an empty tool list or an empty tenant returns an error; repository keys are lowercased.
- [ ] 2. Add the `mctl_security_webhook_deliveries_total{provider,result}` CounterVec, registered in `init()`, with all six results pre-initialized for `github-code-scanning`. DoD: the metric appears at 0 on `/metrics` at startup.
- [ ] 3. Add the pure mapper `mapCodeScanningAlert` and the minimal payload struct (depends on 1). DoD:
  - field mapping exactly as in design.md, including the action-to-claim table, the `commit_oid` then `commit_sha` fallback and the empty revision for `*_by_user` actions;
  - the `source_finding_id` format;
  - untrusted text truncated to the `securityfindings.MaxUntrusted*` caps;
  - errors for a missing GUID, alert number, rule id or path.
- [ ] 4. Add `Options.CodeScanningWebhookSecret`, `Options.CodeScanningConfig` and the optional `Options.SecurityIngester` seam in `internal/api/router.go`. Mount `POST /api/v1/security/webhooks/github-code-scanning` next to `/api/v1/webhooks/github` (depends on 1). DoD: the route is reachable without a bearer token and is unaffected by `securityProviderGate`.
- [ ] 5. Implement `HandleGitHubCodeScanningWebhook` (depends on 2, 3, 4). DoD:
  - steps 1-9 of design.md;
  - reuses `validGitHubSignature` and `maxGitHubWebhookBytes`;
  - `ProviderContext` built only from the constant ref and `SecurityProviders["github-code-scanning"]`;
  - `CodeInternal` and store errors give 503;
  - created or duplicate gives 202 plus an audit entry;
  - every exit except configuration-503 increments exactly one result;
  - no secret, signature or body is logged.
- [ ] 6. Wire `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` and `SECURITY_GITHUB_CODE_SCANNING` in `cmd/api/main.go` (depends on 1, 4). DoD:
  - the secret is disabled with an error log when it equals `GITHUB_WEBHOOK_SECRET` or is shorter than 32 bytes;
  - the config is disabled with an error log when a mapped tenant is outside the `github-code-scanning` `SECURITY_PROVIDERS` tenants;
  - startup never fails because of these values.
- [ ] 7. Helm: add an optional `securityCodeScanning` value rendering `SECURITY_GITHUB_CODE_SCANNING` in `helm/templates/deployment.yaml`, plus a `helm/render_test.go` case (depends on 6). DoD: unset renders nothing; set renders the JSON env.
- [ ] 8. Docs and PR: record in the PR description the provider-auth decision (webhook secret plus `SECURITY_PROVIDERS` entry, no provider token), the final env names and the metric name. Note them in the OpenAPI spec if `internal/openapi` lists public routes. DoD: the PR text contains the decision. After the release tag, a comment on mctl-gitops#2103 lists `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`, `SECURITY_GITHUB_CODE_SCANNING` and `mctl_security_webhook_deliveries_total`.
- [ ] 9. `go fmt`, `go vet`, `golangci-lint` and `go test ./...` pass; cut the mctl-api release tag (depends on 1-8). DoD: the tag exists and contains the receiver.

## Tests
- [ ] T1. Valid delivery: a signed `code_scanning_alert`/`created` for `mctlhq/mctl-api` with tool `Trivy` gives 202 `accepted`. The fake ingester receives one observation with `pc.Ref=="github-code-scanning"`, tenant `admins`, the mapped subject, `source_finding_id`, `claimed_action=present` and `delivery_id` = the GUID. A payload `provider` or `tool` text appears only in `untrusted`. The `accepted` counter is incremented. Also run against the real store when `TEST_DATABASE_URL` is set.
- [ ] T2. Bad signature (wrong HMAC, and no header) gives 401. The ingester is not called and `signature_invalid` is incremented.
- [ ] T3. A body signed with the org `GITHUB_WEBHOOK_SECRET` gives 401 with nothing recorded.
- [ ] T4. Disallowed repository, disallowed tool (for example `CodeQL`), disallowed action (`updated_assignment`) and a `ping` event each give 202 `ignored`. The ingester is not called and `ignored` is incremented.
- [ ] T5. A redelivered GUID with the same body gives 202 `duplicate` the second time. Test it with the real store (`TEST_DATABASE_URL`) and with a fake ingester returning `ItemDuplicate`.
- [ ] T6. Store outage gives 503 and `store_unavailable` in three cases: a nil store, the ingester returning an error, and the ingester returning `rejected/internal_error`.
- [ ] T7. Configuration-503: an unset secret, an unset config, or a missing `SECURITY_PROVIDERS` entry each give 503, and other routes still work. A secret equal to `GITHUB_WEBHOOK_SECRET` is disabled at wiring.
- [ ] T8. Mapper table test covers every allowed action, the `commit_oid`, `commit_sha` and `*_by_user` revision cases, empty-ref suffix omission, untrusted truncation, and the missing-field errors that give 400 `rejected`. A store rejection such as `subject_too_weak` gives 422 `rejected`.
- [ ] T9. Body larger than 1 MiB gives 413. `ParseCodeScanningConfig` table test. The log output in T1-T3 contains neither the secret nor the signature.

## Rollback
The change is additive and has no migration. To disable it quickly without a release,
unset `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` or `SECURITY_GITHUB_CODE_SCANNING` in gitops:
the route then answers 503 and records nothing. GitHub keeps the failed deliveries, which
can be redelivered later. For a full rollback, pin `admins-mctl-api` back to the previous
image tag. Observations already recorded under `github-code-scanning` stay in the #774
store as ordinary provider observations. They can be dismissed through the existing
lifecycle routes if needed.
