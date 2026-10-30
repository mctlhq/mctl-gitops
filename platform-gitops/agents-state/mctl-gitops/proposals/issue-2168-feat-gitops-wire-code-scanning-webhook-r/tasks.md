# Tasks: issue-2168-feat-gitops-wire-code-scanning-webhook-r

- [ ] 1. Pre-rollout verification (no GitOps change). Record each of the following in the PR description:
  - `image.tag` in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` is `4.125.0` or later.
  - An admin `GET https://api.mctl.ai/api/v1/security/findings` answers 200, which means the #774 store is up on the `AUDIT_DB_URL` fallback.
  - `mctlhq/mctl-api` Code Scanning shows `trivy-fs` analyses from `security.yml`.
  - No existing repository hook targets `/api/v1/security/webhooks/github-code-scanning`.

  — DoD: if the store answers 503 `security_findings_store_unavailable`, a blocking step is recorded with its cause (init failure, kill switch, schema), and tasks 3 and 7 do not proceed until it is fixed.
- [ ] 2. Merge 1. Add the `securityCodeScanning` block (`externalSecret: false`, `receiver: false`, with owner steps) to `platform-gitops/bootstrap/values.yaml`. Add `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-security-code-scanning.yaml`:
  - gated by `{{- if (default dict .Values.securityCodeScanning).externalSecret }}`;
  - ExternalSecret `mctl-api-security-code-scanning` in `mctl-api`, store `vault-backend`;
  - one key, `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`, from `platform/mctl-api/github-code-scanning-webhook` property `secret`.

  — DoD: with both flags false, `helm template` of `platform-gitops/bootstrap` is identical to main. With `externalSecret: true`, it adds only that ExternalSecret. `validate-manifests.yml` passes, and no secret value appears in the diff.
- [ ] 3. Owner: write the Vault value with no trailing newline (`printf '%s' ... | vault kv put`), at least 32 characters and different from `platform/mctl-api/github-webhook`. Set `externalSecret: true` (depends on 1, 2). — DoD: ExternalSecret `mctl-api-security-code-scanning` is `SecretSynced`. `mctl-api-secrets` and `mctl-api-events` are still synced.
- [ ] 4. Merge 2 (depends on 3). In `mctl-api.yaml`, gated by `{{- if (default dict .Values.securityCodeScanning).receiver }}`:
  - append `mctl-api-security-code-scanning` to `envFromOptionalSecrets`;
  - add `securityProviders` (`github-code-scanning`, `provider_claim`, `[admins]`);
  - add `securityCodeScanning` (`repositories: {mctlhq/mctl-api: admins}`, `tools: [Trivy]`, the six actions), in YAML form;
  - add comments covering the `provider_claim` ceiling, config-derived tenant, no provider token, the `AUDIT_DB_URL` store fallback, and rollback.

  Do not set `securityProviderTokensSecret`. The flag default stays `false`, and the owner flips it to `true` in the same or a follow-up PR. — DoD: a rendered `helm template` of the mctl-api chart (main) with these values contains `SECURITY_PROVIDERS` and `SECURITY_GITHUB_CODE_SCANNING` JSON matching the design, and the optional secretRef. Render is unchanged with the flag false.
- [ ] 5. Add alert `MctlApiSecurityWebhookFailures` (group `mctl.api.security`, `warning`) to `platform-gitops/infra-components/observability/vm-rules/mctl-api-alerts.yaml`, with firing and non-firing cases in `vm-rules/tests/mctl-api-alerts_test.yaml`. — DoD: the vm-rules unit test in `validate-manifests.yml` passes.
- [ ] 6. Write `docs/runbooks/security-finding-ingestion.md` and link it from `CLAUDE.md` "Secrets Management". It covers:
  - the trust model and response codes;
  - the Vault write and rotation (rotate together, bump `ROLLOUT_MARKER`, redeliver the 401s);
  - hook registration (Code scanning alerts only, JSON, SSL on);
  - manual redelivery;
  - the absence-of-event gap;
  - the uncounted "not configured" 503;
  - rollback.

  — DoD: the runbook contains no secret value and no customer name.
- [ ] 7. Owner rollout (depends on 1, 3, 4, 5, 6 merged): set `receiver: true`, wait for both pods to roll, then register the repository webhook on `mctlhq/mctl-api`. — DoD: the GitHub `ping` delivery shows 202 `ignored`. The `mctl_security_webhook_deliveries_total{provider="github-code-scanning"}` series is scraped.
- [ ] 8. E2E proof (depends on 7). Open a same-repo draft PR on `mctlhq/mctl-api` that adds a test-only fixture, pinning one dependency version with a known fixed HIGH/CRITICAL CVE at two different paths (for example `testdata/security-e2e/a/` and `.../b/`). Let `security.yml` upload SARIF. Then push a commit removing one path to produce `fixed`. Close the PR and delete the branch afterwards. — DoD: evidence for T3-T10 is attached to #2168, and the fixture never reaches `main`.

## Tests

- [ ] T1. Render. Flags false: identical to main. `externalSecret` only: adds just the ExternalSecret. `receiver` also true: adds just the envFrom entry and the two values. Run `helm lint` and `helm template` for `platform-gitops/bootstrap`.
- [ ] T2. Secret hygiene. `git grep` for the secret value finds nothing in this repo. The mctl-api logs for the E2E window and the Argo CD rendered manifests contain only references. The Kubernetes Secret value equals its stripped form.
- [ ] T3. Identity. Each observation has `provider_ref=github-code-scanning`, tenant `admins`, `source_finding_id` `github:mctlhq/mctl-api/code-scanning/<n>`, the alert path and location, and `observed_revision` equal to the alert's commit.
- [ ] T4. Distinctness. The same CVE at the two fixture paths yields two occurrences under one finding.
- [ ] T5. Redelivery. Redeliver one accepted delivery from the hook's Recent Deliveries. The response is 202 `duplicate`, and the observation and occurrence counts are unchanged.
- [ ] T6. Multi-finding. The fixture upload's N alerts produce N `accepted` deliveries and N observations.
- [ ] T7. Bad signature. A POST with a missing or wrong `X-Hub-Signature-256`, or signed with the org webhook secret, gets 401 `signature_invalid`, creates no observation, and fires the alert.
- [ ] T8. Spoofing and untrusted text. Evidence comes from the mctl-api 4.125.0 receiver tests (`internal/api/handlers_security_code_scanning_test.go`) plus a live check. The live check: an owner-signed synthetic delivery (secret read from Vault into a variable, never echoed) containing `"provider":"mctl-assurance"` and an inflated severity is recorded under `github-code-scanning`, at most `provider_claim`, with the text only in `untrusted`. A signed delivery for another repository or tool gets 202 `ignored`.
- [ ] T9. Downstream unavailable. With owner approval and before #809 consumes the store, set `SECURITY_FINDINGS_DISABLED: "true"` for a bounded window. A redelivery gets 503 `store_unavailable`, GitHub shows it failed, and the alert fires. Revert, redeliver, and confirm it is recorded exactly once. If the owner declines, record the unit-test evidence and the gap.
- [ ] T10. No side effects. No WorkItem, DevLoop or remediation attempt is created for the E2E occurrences (`mctl_list_agent_executions`, the #774 attempts read).

## Rollback

- Immediate: set the repository webhook on `mctlhq/mctl-api` inactive, or delete it. Ingestion stops.
- GitOps: set `securityCodeScanning.receiver: false`. The env vars and the optional secretRef disappear and the pods roll, so the route answers 503 to any straggler. Then set `externalSecret: false`, and root-app prunes the ExternalSecret and its Secret. Reverting the PRs is equivalent.
- Store-wide emergency: `SECURITY_FINDINGS_DISABLED: "true"` in `mctl-api.yaml` makes all `/api/v1/security*` routes answer 503 without touching data.
- Data: recorded observations are immutable #774 evidence and are not deleted. A human can dismiss occurrences through #774 if needed.
- Secret: if exposure is suspected, rotate or delete `secret/platform/mctl-api/github-code-scanning-webhook` and the hook secret together.
- The SARIF upload in mctl-api is harmless without the webhook and stays.
