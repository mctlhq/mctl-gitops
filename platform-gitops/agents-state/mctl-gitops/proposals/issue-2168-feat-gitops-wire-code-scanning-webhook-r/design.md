# Design: issue-2168-feat-gitops-wire-code-scanning-webhook-r

## Current state

### How mctl-api is deployed

- mctl-api is not a tenant catalogue service. There is no `platform-gitops/services/admins/mctl-api/`.
- It is the Argo CD Application `admins-mctl-api` (project `platform`, namespace `mctl-api`), defined in `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` and rendered by root-app from the bootstrap chart.
- It renders the chart `mctlhq/mctl-api` `helm/` at `targetRevision: main`, with inline `values: |`:
  - `image.tag: "4.125.0"` (main at `2ae16f4`, `chore: bump admins/mctl-api to 4.125.0`);
  - `replicaCount: 2`;
  - ingress `api.mctl.ai` (Traefik, TLS).
- Secrets enter through three mechanisms:
  - `envFromSecret: mctl-api-secrets`;
  - `envFromExtraSecret: mctl-api-events` (holds `GITHUB_WEBHOOK_SECRET` for the org-level pull-request webhook);
  - `envFromOptionalSecrets: [mctl-api-zitadel-hook]`.
- Optional principals use a flag-gated pattern. The Helm value line in `mctl-api.yaml` and a separate ExternalSecret file are both wrapped in `{{- if (default dict .Values.<flag>).enabled }}`, with the flag and owner steps in `platform-gitops/bootstrap/values.yaml`. Example: `evidenceWriter` and `bootstrap/templates/mctl-platform/mctl-api-evidence-writer.yaml`.
- `bootstrap/templates/mctl-platform/mctl-api-secrets.yaml` explains why credentials are split: ESO fails a whole ExternalSecret when one remoteRef does not resolve. It also warns that a Vault value must be written without a trailing newline.
- The env block sets `AUDIT_DB_URL` (shared-pg database `mctl-api`) and `LIFECYCLE_DB_URL` (dedicated `mctl-lifecycle`). It does not set `SECURITY_FINDINGS_DB_URL`, `EVIDENCE_DB_URL`, `SECURITY_FINDINGS_DISABLED`, `SECURITY_PROVIDERS` or `SECURITY_GITHUB_CODE_SCANNING`. A grep of `platform-gitops/` (excluding `agents-state/`) for those names, `securityCodeScanning` and `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` finds nothing.
- `ROLLOUT_MARKER` is the documented way to restart pods when only envFrom content changes.

### Network, metrics and webhook registration

- `bootstrap/templates/mctl-platform/mctl-api-netpol.yaml` (`allow-mctl-api-ingress`) admits Traefik, kube-system, monitoring, argo-workflows and admins.
- Public GitHub deliveries already reach `api.mctl.ai` for the org pull-request webhook.
- `infrastructure/cloudflare/zones/mctl-ai/firewall.tf` has no path rule affecting `/api/v1/security/*`.
- `bootstrap/templates/mctl-platform/mctl-api-monitor.yaml` scrapes `/metrics` on port `http` every 30s.
- Alerts live in `platform-gitops/infra-components/observability/vm-rules/mctl-api-alerts.yaml`, with tests in `vm-rules/tests/mctl-api-alerts_test.yaml`, run by `.github/workflows/validate-manifests.yml`.
- No IaC manages GitHub webhooks: `infrastructure/` contains only `cloudflare`, `k3s-preview` and `k3s-prod`, with no `github_*_webhook` resource. The org webhook is set by hand. The repository webhook here is too, through the runbook.

### What mctl-api 4.125.0 expects

Read at tag `4.125.0` via `gh api`: `docs/security-findings.md`, `helm/values.yaml`, `helm/templates/deployment.yaml`, `cmd/api/main.go`, `internal/auth/security_provider.go`, `internal/api/handlers_security_code_scanning.go`.

Chart values (also present on chart `main`, which the Application tracks):
- `securityProviders: []`, rendered as `SECURITY_PROVIDERS`.
- `securityCodeScanning: {}`, rendered as `SECURITY_GITHUB_CODE_SCANNING` only when non-empty.
- `securityProviderTokensSecret: ""`.

The chart does not set `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`.

`codeScanningReceiver` (main.go):
- If both the secret and the config are empty, the receiver is off with no error.
- If the secret is shorter than 32 characters or equals `GITHUB_WEBHOOK_SECRET`, it logs an error and disables the receiver.
- If `ParseCodeScanningConfig` fails, it disables the receiver.

`ParseCodeScanningConfig` requires:
- a `SECURITY_PROVIDERS` entry `github-code-scanning` with a parseable `max_strength`;
- non-empty `repositories`, `tools` and `actions`;
- every mapped tenant to be within the provider's `tenants`;
- actions from `created`, `appeared_in_branch`, `reopened`, `reopened_by_user`, `fixed`, `closed_by_user`.

Tools are lowercased. `provider_ref` defaults to and must equal `github-code-scanning`.

`HandleGitHubCodeScanningWebhook`:
- answers 503 when not ready;
- checks HMAC, then event type (a `ping` gets 202 `ignored`);
- applies the repository, tool and action allowlists;
- maps the alert to one observation;
- answers 202 `accepted`/`duplicate` only after the store recorded it, or 503 `store_unavailable`.

The metric `mctl_security_webhook_deliveries_total{provider,result}` is pre-initialised for every result. The "not configured" 503 does not increment it.

Store selection: `SECURITY_FINDINGS_DB_URL`, else `EVIDENCE_DB_URL`, else `AUDIT_DB_URL`. In production that resolves to `AUDIT_DB_URL`, the `mctl-api` database. `SECURITY_FINDINGS_DISABLED` is a kill switch.

The scanner side is done. At 4.125.0, mctl-api `.github/workflows/security.yml` job `trivy` runs Trivy `v0.69.3` (`format: sarif`, `severity: CRITICAL,HIGH`, `ignore-unfixed`, `exit-code: "0"`) and uploads with `github/codeql-action/upload-sarif` `category: trivy-fs`, under `security-events: write`. It skips fork and Dependabot PRs. The SARIF tool driver name is `Trivy`.

Superseded proposal: `agents-state/mctl-gitops/proposals/issue-2103-.../` (status `needs-triage`, `no_commits`). Its design predated the receiver and guessed names. This design replaces those guesses with the released names: no provider token, receiver config key `securityCodeScanning`.

Deployed state checked:
- `mctl_get_service_status(team=admins, service=mctl-api)`: Argo CD `admins-mctl-api` is Healthy and Synced, updatedAt `2026-10-26T15:46:50Z`. `service: null`, as expected for a bootstrap app.
- `$MCTL_GITOPS_ROOT/services/admins/`: `mctl-agents-worker`, `mctl-agents-worker-exec`, `mctl-agents-worker-implement`, `mctl-design`, `mctl-docs`, `mctl-web`, `umami`. There is no mctl-api, which confirms that its config is the bootstrap template.
- `$MCTL_GITOPS_ROOT/tenants/` contains `admins`, so the tenant used in config exists.
- `mctl_get_service_logs(admins, mctl-api, since=6h)`: returned 0 lines. Not observed. The store init log and `SECURITY_FINDINGS_*` runtime state are unknown (see Open questions; verified in task 1).
- `gh api repos/mctlhq/mctl-api`: visibility `public`, so Code Scanning is available.
- `gh api .../code-scanning/alerts`, `.../code-scanning/analyses` and `.../hooks`: 403 for this run's token. Not observed (task 1).
- `gh api` `helm/values.yaml` at `ref=main`: `securityProviders` and `securityCodeScanning` are present.

## Proposed solution

Wire the released receiver with configuration only, in two merges, following the flag-gated pattern already used for mctl-api principals.

### Bootstrap flag (`platform-gitops/bootstrap/values.yaml`)

```yaml
# GitHub Code Scanning -> SecurityFinding receiver (mctlhq/mctl-gitops#2168,
# mctl-api >= 4.125.0, docs/runbooks/security-finding-ingestion.md).
# Vault: secret/platform/mctl-api/github-code-scanning-webhook, property
# secret: >= 32 chars, different from platform/mctl-api/github-webhook, no
# trailing newline. Two merges, in order:
#   1. owner writes Vault; externalSecret: true; confirm the Secret synced.
#   2. receiver: true (the env change rolls the pods, which then read it).
#   3. owner registers the repository webhook (runbook).
securityCodeScanning:
  externalSecret: false
  receiver: false
```

### Merge 1: ExternalSecret

New file `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-security-code-scanning.yaml`, wrapped in `{{- if (default dict .Values.securityCodeScanning).externalSecret }}`:
- ExternalSecret `mctl-api-security-code-scanning`, namespace `mctl-api`, `refreshInterval: 1h`, ClusterSecretStore `vault-backend`;
- target `mctl-api-security-code-scanning`, `creationPolicy: Owner`;
- one entry: `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` from `platform/mctl-api/github-code-scanning-webhook`, property `secret`.

The header comment states why this is its own file, matching `mctl-api-evidence-writer.yaml`:
- a missing property degrades only the receiver;
- the credential is deliberately distinct from `mctl-api-events`.

Root-app owns ExternalSecrets in this namespace, so the inert ExternalSecret `ignoreDifferences` rule in `mctl-api.yaml` needs no change.

### Merge 2: receiver config

In `mctl-api.yaml`, inside the inline values, gated by `{{- if (default dict .Values.securityCodeScanning).receiver }}`:

```yaml
envFromOptionalSecrets:
  - mctl-api-zitadel-hook
  {{- if (default dict .Values.securityCodeScanning).receiver }}
  - mctl-api-security-code-scanning
  {{- end }}
```

Top-level chart values, in YAML form (no inline JSON):

```yaml
securityProviders:
  - ref: github-code-scanning
    max_strength: provider_claim
    tenants: [admins]
securityCodeScanning:
  repositories:
    mctlhq/mctl-api: admins
  tools: [Trivy]
  actions: [created, appeared_in_branch, reopened, reopened_by_user, fixed, closed_by_user]
```

Comments next to the values record the decisions:
- `max_strength: provider_claim`: a webhook only claims. `fixed` must never resolve an occurrence, and verification stays with #809.
- Tenant from config, not payload: this answers #774's "tenant attribution" open point for this provider.
- `securityProviderTokensSecret` stays unset: the receiver writes in-process, and a token would open `POST /api/v1/security/observations` to a second credential.
- No `SECURITY_FINDINGS_DB_URL`: the store uses the `AUDIT_DB_URL` fallback (database `mctl-api`).
- Rollback steps.

Merge 2 adds env vars, which changes the pod template, so Argo CD rolls the two replicas and the new containers read the already-synced optional Secret. `ROLLOUT_MARKER` is not bumped; its comment stays accurate. The rollout is the same kind as every env change here, with the PDB in `mctl-api-pdb.yaml`.

Merge 2 is separate from merge 1 for the reason recorded for `LIFECYCLE_DB_URL`: root-app and `admins-mctl-api` reconcile independently. If both landed at once, a pod could start before ESO created the Secret. It would then hold an empty secret and log "receiver disabled" until the next restart.

### Owner steps (runbook, not GitOps)

1. Write the Vault value: `printf '%s' "$(openssl rand -hex 32)" | vault kv put secret/platform/mctl-api/github-code-scanning-webhook secret=-`. Check it with `t == t.strip()`, and confirm it differs from `platform/mctl-api/github-webhook`.
2. After merge 2, register a repository webhook on `mctlhq/mctl-api`:
   - URL `https://api.mctl.ai/api/v1/security/webhooks/github-code-scanning`;
   - content type `application/json`;
   - SSL verification on;
   - the same secret;
   - only the "Code scanning alerts" event.

   The automatic `ping` must get 202 `ignored`.

### Alert

Add to `mctl-api-alerts.yaml` (new group `mctl.api.security`):

```yaml
- alert: MctlApiSecurityWebhookFailures
  expr: sum by (result) (increase(mctl_security_webhook_deliveries_total{provider="github-code-scanning",result=~"signature_invalid|rejected|store_unavailable"}[15m])) > 0
  labels: {severity: warning, service: mctl-api}
```

The description points to the runbook. The metric is pre-initialised, so `increase` is well defined. A matching case goes in `vm-rules/tests/mctl-api-alerts_test.yaml`.

### Runbook

New `docs/runbooks/security-finding-ingestion.md`, linked from `CLAUDE.md` "Secrets Management". It covers:
- Trust model: identity comes from the route and secret, and payload text is untrusted.
- Response codes and what each means.
- The Vault write and rotation. Rotate the Vault value and the hook secret together, then bump `ROLLOUT_MARKER`, because envFrom is read at start. Deliveries fail with 401 during the gap, and failed deliveries are redelivered afterwards.
- Registration.
- Manual redelivery: GitHub does not redeliver automatically, so use the repository hook deliveries UI or API for deliveries answered 401 or 503.
- The absence-of-event gap.
- The "not configured" 503 not being counted.
- Rollback.

### Failure and retry

| Condition | Behaviour |
|---|---|
| Store down | 503 `store_unavailable`. GitHub marks the delivery failed, the alert fires, an operator redelivers. Bounded, never silent. |
| Redelivery | Same `X-GitHub-Delivery` and content, so #774's `observation_hash` answers `duplicate`. |
| Multiple findings | One alert per delivery, so N alerts mean N deliveries and N observations. There is no first-only collapse. |
| Same rule at two paths | Different `subject_fingerprint`, so distinct occurrences. |

### Pre-rollout check of the #774 store

Task 1 runs an admin `GET https://api.mctl.ai/api/v1/security/findings`. A 200 confirms the store is up. If it returns 503 `security_findings_store_unavailable`, the receiver flag is not enabled. The cause (init failure, kill switch, schema) becomes a recorded blocking step, typically fixed by a pod restart through `ROLLOUT_MARKER`.

## Alternatives

A. One flag and one merge (ExternalSecret and receiver env together). Dropped. Root-app and `admins-mctl-api` sync independently, so the pods could roll before ESO creates the Secret. The receiver would then stay disabled until another restart, a silent 503 that the metric does not count.

B. Reuse the org webhook and `GITHUB_WEBHOOK_SECRET`. Not possible. mctl-api 4.125.0 refuses a code-scanning secret equal to `GITHUB_WEBHOOK_SECRET`. An org-wide hook would also make the repository allowlist the only scope limit.

C. Add the key to `mctl-api-secrets` or `mctl-api-events`. Dropped. A missing Vault property would fail the whole ExternalSecret and take down `DB_PASSWORD` or the pull-request webhook with it.

D. Dedicated `SECURITY_FINDINGS_DB_URL` database now. Deferred. It needs a CNPG Database CR in its own merge (the `LIFECYCLE_DB_URL` precedent), and moving data later is the #774 owner's call. The released fallback is what #774 specified for v1. Recorded as an open question.

E. Provider token (`securityProviderTokensSecret`) or a standalone adapter. Dropped. The released receiver is in-process, so a token adds a second credential with ingest authority for no benefit.

## Platform impact

- Backward compatibility: both flags default to `false`, so the render is unchanged until the owner enables them. An enabled ExternalSecret without its Vault value only marks that ExternalSecret SecretSyncedError.
- Migrations: none here. The #774 schema is applied at mctl-api startup.
- Resources: one Secret and two env vars. Load is about one request per alert transition.
- Exposure: no new hostname, ingress, Cloudflare rule or NetworkPolicy. The route is under the existing `api.mctl.ai`.

Risks and mitigations:

| Risk | Mitigation |
|---|---|
| Secret leak | Vault and ESO only. Write without a newline. T2 greps Git and logs. |
| Forged or spoofed provider | HMAC with a dedicated secret. Server-fixed `github-code-scanning`. `provider_claim` ceiling. Allowlists for repository, tool and action. |
| Silent misconfiguration | `ping` check, T-checks and the startup error log. The not-configured 503 is not counted, recorded as a gap. |
| Lost deliveries | No 2xx without a store write. Alert plus runbook redelivery. |
| Pod roll on merge 2 | Two replicas, PDB and topology spread. |
| Kill-switch test (T9) disables all `/api/v1/security*` routes | Bounded window, only before #809 consumes the store, with owner approval. |
