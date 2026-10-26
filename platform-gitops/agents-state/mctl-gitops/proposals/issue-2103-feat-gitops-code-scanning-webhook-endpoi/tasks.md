# Tasks: issue-2103-feat-gitops-code-scanning-webhook-endpoi

- [ ] 1. Verify the dependency gate (P1). — DoD: the PR description records
  the mctl-api tag that contains #774 (PR #799) and shows that this tag is
  deployed on `admins-mctl-api` (`mctl_get_service_config` / the
  `image.tag` in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`).
  If the tag is not deployed, stop here and leave everything else unchanged.
- [ ] 2. Record the scanner and provider facts. — DoD: the PR description
  states the following for `mctlhq/mctl-api`:
  - whether Code Scanning is available (visibility, Code Security);
  - the current `security.yml` steps;
  - whether Trivy emits SARIF anywhere.

  If Code Scanning is unavailable, switch to design Alternative B, record why,
  and do not continue with tasks 5-8 as written.
- [ ] 3. File prerequisite P2 in mctl-api (depends on 2): the Trivy SARIF
  upload. Use `upload-sarif`, `security-events: write`, `if: always()` and
  category `trivy-fs`, and keep the fail-closed gate unchanged. — DoD: the
  issue is linked from #2103. After it merges, a scan on mctl-api shows Trivy
  alerts in Code Scanning with path, line and commit_sha.
- [ ] 4. File prerequisite P3 in mctl-api (depends on 1): the receiver route
  `POST /api/v1/security/webhooks/github-code-scanning`. It must implement the
  HMAC check, the allowlists, the mapping table in design.md, provider binding
  to `github-code-scanning`, 5xx when the store is unavailable, the
  `mctl_security_webhook_deliveries_total` metric (or equivalent), no secret
  logging, and the chosen provider-credential option. — DoD: the issue is
  linked, the route is released in an mctl-api tag, and the final env and
  metric names are recorded.
- [ ] 5. Add the `securityCodeScanning` flag (`enabled: false`) with owner
  steps to `platform-gitops/bootstrap/values.yaml`. — DoD: `helm template` of
  bootstrap renders identically to main while the flag is false.
- [ ] 6. Add
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-security-code-scanning.yaml`
  (depends on 5): ExternalSecret `mctl-api-security-code-scanning`, key
  `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` from
  `platform/mctl-api/github-code-scanning-webhook` property `secret`, plus
  `MCTL_SECURITY_PROVIDER_TOKENS` only if P3 chose the token option. The file
  is gated by the flag. — DoD: renders only when enabled, contains no secret
  value, and passes yamllint and `validate-manifests.yml`.
- [ ] 7. Gated edits to `mctl-api.yaml` (depends on 4, 5, 6):
  - append to `envFromOptionalSecrets`;
  - set `securityProviders` to
    `[{"ref":"github-code-scanning","max_strength":"provider_claim","tenants":["admins"]}]`;
  - add the receiver config env (repositories `{"mctlhq/mctl-api":"admins"}`,
    tools `["Trivy"]`, the action allowlist);
  - bump `ROLLOUT_MARKER` with a reason.

  — DoD: rendered values match the P3 names. There is no diff when the flag is
  disabled.
- [ ] 8. Add alert `MctlApiSecurityWebhookFailures` to
  `platform-gitops/infra-components/observability/vm-rules/mctl-api-alerts.yaml`
  and a test to `vm-rules/tests/mctl-api-alerts_test.yaml` (depends on 4). —
  DoD: the vmalert unit test passes.
- [ ] 9. Write `docs/runbooks/security-finding-ingestion.md` and link it from
  `CLAUDE.md` "Secrets Management". — DoD: the runbook covers the trust model,
  Vault write without a trailing newline, rotation, hook registration (Code
  scanning alerts only), manual redelivery, the absence gap and rollback.
- [ ] 10. Owner rollout (depends on 3-9 merged): write the Vault value, set the
  flag true, wait for the ESO sync and the pod roll, then register the repo
  webhook on `mctlhq/mctl-api`. — DoD: the GitHub ping delivery is answered as
  ignored (2xx), and the Secret exists in `mctl-api` with a value equal to its
  stripped form.
- [ ] 11. E2E proof (depends on 10). Open a draft PR on mctl-api with a
  synthetic fixture: a throwaway lockfile under a test-only directory, pinning a
  module version with a known CRITICAL CVE in two different paths. Run the tests
  below, then close the PR and delete the fixture. — DoD: evidence is attached
  to #2103 for every test T1-T10.

## Tests

- [ ] T1. Render: with the flag false, the bootstrap render equals main. With
  the flag true, it adds only the ExternalSecret, the optional envFrom entry,
  `securityProviders` and the config env.
- [ ] T2. Secret hygiene: `git grep` for the secret value is empty. Workflow
  and Loki logs for mctl-api over the E2E window do not contain it. The
  `values.yaml` and rendered manifests contain only references.
- [ ] T3. Identity: every created occurrence carries repository
  `mctlhq/mctl-api`, the alert path and line, and `observed_revision` equal to
  the PR merge commit_sha.
- [ ] T4. Distinctness: the same CVE in two fixture paths yields two
  occurrences under one finding.
- [ ] T5. Redelivery: redeliver one delivery through the repo hook deliveries
  API. Confirm the same `X-GitHub-Delivery` GUID, that #774 answers
  `duplicate`, and that the observation count is unchanged.
- [ ] T6. Multi-finding: one SARIF upload with N alerts produces N
  observations. None are missing.
- [ ] T7. Bad signature: a request with a wrong or absent
  `X-Hub-Signature-256` gets 401 and no observation. A request signed with the
  org webhook secret is also rejected.
- [ ] T8. Spoofing: a correctly signed synthetic payload containing
  `"provider":"mctl-assurance"` and inflated severity or verification text is
  recorded with `provider_ref=github-code-scanning`, strength at most
  `provider_claim`, and the text only in `untrusted`. Payloads with a repository
  or tool outside the allowlist record nothing.
- [ ] T9. Downstream unavailable: with the store disabled
  (`SECURITY_FINDINGS_DISABLED` on a preview or test deployment of mctl-api),
  a delivery gets a non-2xx response, GitHub shows it failed, the alert fires,
  and runbook redelivery after recovery records it once.
- [ ] T10. No side effects: no mctl-agents DevLoop, WorkItem or remediation
  attempt is created by the receiver during the E2E (`mctl_list_agent_executions`
  and #774 attempts list are empty for the occurrences).

## Rollback

- Fast: delete the repository webhook on `mctlhq/mctl-api`, or set it
  inactive. Ingestion stops immediately.
- GitOps: set `securityCodeScanning.enabled: false` (or revert the PR). The
  ExternalSecret, env and provider entry are no longer rendered, and Argo CD
  prunes the Secret. Bump `ROLLOUT_MARKER` so the pods drop the env. Without
  the provider entry, #774 disables `github-code-scanning`, and the route
  answers 503 for any straggling delivery.
- Data: observations already recorded are immutable evidence in #774 and are
  not deleted by rollback. Occurrences can be dismissed by a human through
  #774 if needed.
- Secret: after rollback, rotate or delete
  `secret/platform/mctl-api/github-code-scanning-webhook` if exposure is
  suspected.
- Scanner: the P2 SARIF upload can stay. It is harmless without the webhook.
  Revert it in mctl-api if needed.
