# Design: issue-2103-feat-gitops-code-scanning-webhook-endpoi

## Current state

mctl-api deployment
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml` defines the
  Argo CD Application `admins-mctl-api` (project `platform`). It renders the
  chart from `mctlhq/mctl-api` `helm/` with inline values: image tag `4.124.0`,
  `replicaCount: 2`, ingress `api.mctl.ai` (Traefik, TLS), and env such as
  `GITHUB_ORG: mctlhq`, `SELF_URL`, `TRUSTED_PROXY_CIDRS`. Secrets enter
  through `envFromSecret: mctl-api-secrets`, `envFromExtraSecret: mctl-api-events`
  and `envFromOptionalSecrets: [mctl-api-zitadel-hook]`. An optional secret lets
  the pod start without it, and its route answers 503.
- mctl-api already receives GitHub webhooks. In `mctl-api.yaml` (around the
  `EVENTS_VALKEY_URL` comment), pull-request events (mctl-api#323) are verified
  with `GITHUB_WEBHOOK_SECRET`, enqueued into the audit DB outbox and relayed to
  Valkey stream `mctl:events:github`. The secret comes from the separate
  ExternalSecret `mctl-api-events` in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`
  (Vault `platform/mctl-api/github-webhook`, property `secret`). The secret is
  "also configured on the mctlhq organization webhook", which is a manual
  setting with no IaC. A grep of `infrastructure/` finds no
  `github_repository_webhook` or `github_organization_webhook` resources.
- Isolation pattern: optional principals and credentials each get their own
  ExternalSecret file, gated by a flag in `platform-gitops/bootstrap/values.yaml`.
  Examples are `evidenceWriter.enabled`, which renders
  `mctl-api-evidence-writer.yaml` under `{{- if (default dict .Values.evidenceWriter).enabled }}`,
  and `usageWriter`, `registryPublisher`, `surfaceTelegramToken`. The comments
  explain why: ESO fails a whole ExternalSecret when one remoteRef is missing.
  They also warn about trailing newlines in Vault values.
- Network: `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-netpol.yaml`
  (`allow-mctl-api-ingress`) admits Traefik, kube-system, monitoring,
  argo-workflows and admins. Public webhooks already arrive through Traefik.
  Cloudflare `infrastructure/cloudflare/zones/mctl-ai/firewall.tf` fronts
  `api.mctl.ai`, and the existing org webhook reaches it today.
- Alerts: `platform-gitops/infra-components/observability/vm-rules/mctl-api-alerts.yaml`
  with unit tests under `vm-rules/tests/mctl-api-alerts_test.yaml`.

Scanner workflows
- This repo's `.github/workflows/security.yml` runs `aquasecurity/trivy-action`
  v0.36.0 (`scan-type: fs`, `severity: CRITICAL`, `exit-code: "1"`) with
  `permissions: contents: read` and no SARIF output or `upload-sarif` step.
  Trivy emits no SARIF here.
- The issue reports that `mctl-api/.github/workflows/security.yml` runs
  `govulncheck` and Trivy fail-closed and does not upload SARIF. That repository
  is not cloned in this run, so this design takes the claim from the issue and
  re-checks it as a prerequisite (tasks 1 and 2).

The #774 contract (from `platform-gitops/agents-state/mctl-api/proposals/issue-774-feat-api-securityfinding-v1-store-and-ap/design.md`, status `merged`, PR mctl-api#799)
- `POST /api/v1/security/observations`: a batch `{delivery_id, observations[]}`
  of at most 100 items. Each item is `{tenant, identity, aliases[], subject{},
  source_finding_id, claimed_action, observed_revision,
  observed_artifact_digest, evidence_refs[], observed_at, untrusted{}}`.
- Provider config: `SECURITY_PROVIDERS` (non-secret JSON, from Helm value
  `securityProviders`) is `[{"ref","max_strength","tenants"}]`.
  `MCTL_SECURITY_PROVIDER_TOKENS` (Secret, `ref=token` lines) mints
  `service:security-provider:<ref>`. A payload `provider` field goes into
  `untrusted.claimed_provider`.
- Dedup: `observation_hash` covers identity, subject fingerprint,
  source_finding_id, claimed_action, revision, artifact digest, delivery_id and
  evidence digest, unique per `provider_ref`. Subject minimum: repository plus
  one of purl, path, location or artifact digest. Revision is not part of the
  fingerprint.
- `fixed` is capped at `provider_claim`. Only `absent` bound to a landed
  revision can verify.

GitHub event (docs.github.com, webhook-events-and-payloads#code_scanning_alert, fetched 2026-10-26)
- Actions: `appeared_in_branch`, `closed_by_user`, `created`, `fixed`,
  `reopened`, `reopened_by_user`, `updated_assignment`. The event is available
  on repository, organization and App webhooks. An App needs "Code scanning
  alerts" read.
- `commit_oid` and `ref` are empty for `*_by_user` actions and can be null for
  `reopened`. Headers are `X-GitHub-Delivery` (GUID) and `X-Hub-Signature-256`.
- "GitHub does not automatically redeliver failed deliveries"
  (handling-failed-webhook-deliveries). Repo hooks have list and redeliver
  delivery endpoints.
- One delivery carries one alert. Several findings from one upload arrive as
  several deliveries.

Deployed state checked:
- `mctl_get_service_status(team=admins, service=mctl-api)`: Argo CD app
  `admins-mctl-api` is Healthy and Synced (updatedAt 2026-10-26T01:29:36Z).
  `service: null`, because it is a bootstrap app, not a catalogue service.
- `$MCTL_GITOPS_ROOT/services/admins/` lists `mctl-agents-worker`,
  `mctl-agents-worker-exec`, `mctl-agents-worker-implement`, `mctl-design`,
  `mctl-docs`, `mctl-web` and `umami`. mctl-api is not a tenant service. Its
  config is the bootstrap template above.
- `$MCTL_GITOPS_ROOT/agents-state/mctl-api/proposals/issue-774-.../.status.yaml`:
  `status: merged`, `merge_commit 8023be0`, `merged_at 2026-10-26T00:34:05Z`.
- Not observed: whether tag `4.124.0` contains PR #799. Also not observed:
  mctl-api repository visibility, Code Scanning enablement, mctl-api's
  `security.yml`, and the event subscriptions of the existing org webhook. All
  are recorded under Open questions.

## Proposed solution

### Path

```text
mctl-api security.yml: Trivy fs -> SARIF -> github/codeql-action/upload-sarif   (prerequisite, mctl-api repo)
  -> GitHub Code Scanning alert (rule id = CVE/GHSA, location path:line, commit_sha, ref)
  -> repository webhook on mctlhq/mctl-api, event "Code scanning alerts" only,
     URL https://api.mctl.ai/api/v1/security/webhooks/github-code-scanning,
     secret from Vault                                                           (registered by owner, runbook)
  -> mctl-api receiver route                                                     (prerequisite, mctl-api repo)
     verify HMAC -> allowlist event/action/repo/tool -> map to one #774 item
  -> #774 ingestion as provider_ref "github-code-scanning" (tenant admins)
```

The receiver is hosted in mctl-api for these reasons:
- mctl-api already runs a signed GitHub webhook receiver behind `api.mctl.ai`,
  so it needs no new hostname, ingress, Cloudflare host entry, image or repo.
- The #774 store is in-process there, so authenticated provider identity is a
  server-side constant bound to the route and its secret. The payload cannot
  reach it.
- Failure semantics are simple: if the store is unavailable the receiver
  answers 5xx, and GitHub records the failure.

The code itself is a narrow prerequisite issue in mctl-api. GitOps carries only
configuration.

### GitOps changes (this repository)

1. Flag. In `platform-gitops/bootstrap/values.yaml`, add a `securityCodeScanning`
   block with `enabled: false` and owner steps in the same style as
   `evidenceWriter`:
   1. Write the secret to Vault with
      `printf '%s' "$(openssl rand -hex 32)" | vault kv put secret/platform/mctl-api/github-code-scanning-webhook secret=-`
      (no trailing newline).
   2. Set `enabled: true`.
   3. Register the repo webhook (runbook).

2. ExternalSecret. Add a new file
   `platform-gitops/bootstrap/templates/mctl-platform/mctl-api-security-code-scanning.yaml`,
   rendered only under `{{- if (default dict .Values.securityCodeScanning).enabled }}`.
   It defines ExternalSecret `mctl-api-security-code-scanning` in namespace
   `mctl-api`, store `vault-backend`, target Secret
   `mctl-api-security-code-scanning`, with one key:
   `GITHUB_CODE_SCANNING_WEBHOOK_SECRET` from `platform/mctl-api/github-code-scanning-webhook`,
   property `secret`. If the mctl-api prerequisite chooses the token option
   (Open questions), add `MCTL_SECURITY_PROVIDER_TOKENS` as a templated
   `github-code-scanning=<token>` line from property `provider-token` in the
   same Vault entry. This file and entry are the only places the receiver's
   credentials live. The file is separate from `mctl-api-secrets` and
   `mctl-api-events`, so a missing property cannot take down DB credentials or
   pull-request events. It uses a distinct secret from the org webhook, so a
   repo-scoped hook cannot be forged with the org secret and rotation is
   independent.

3. mctl-api values (`platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`),
   all inside the same `{{- if }}` gate so a disabled flag renders nothing new:
   - Append `mctl-api-security-code-scanning` to `envFromOptionalSecrets`. The pod
     still starts if the Secret is absent, and the route answers 503.
   - `securityProviders` (the #774 Helm value, which becomes `SECURITY_PROVIDERS`):
     `[{"ref":"github-code-scanning","max_strength":"provider_claim","tenants":["admins"]}]`.
     The ceiling is `provider_claim` because a webhook can only claim. It can
     never deliver a revision-bound `absent`, so verification stays with #778.
   - Non-secret receiver config env, with the name finalised by the
     prerequisite, proposed `SECURITY_GITHUB_CODE_SCANNING`:
     ```json
     {"provider_ref":"github-code-scanning",
      "repositories":{"mctlhq/mctl-api":"admins"},
      "tools":["Trivy"],
      "actions":["created","appeared_in_branch","reopened","reopened_by_user","fixed","closed_by_user"]}
     ```
     The repository-to-tenant map answers the #774 open question on tenant
     attribution for this provider: the tenant comes from config, not the payload.
   - Bump `ROLLOUT_MARKER` with a reason line, per the existing convention, so
     envFrom is re-read after the Secret first syncs.

4. Mapping contract. The mctl-api prerequisite implements it. It is documented
   here and in the runbook so gitops reviewers can check the config against it:

   | #774 field | source |
   |---|---|
   | delivery_id | `X-GitHub-Delivery` header |
   | tenant | `repositories[repository.full_name]` (config) |
   | identity | `alert.rule.id` (CVE-/GHSA- canonicalised by #774, else `rule:`) |
   | subject | `{repository: repository.full_name, path: alert.most_recent_instance.location.path, location: "start_line:end_line", rule_id}` |
   | source_finding_id | `github:<full_name>/code-scanning/<alert.number>@<most_recent_instance.ref>` |
   | claimed_action | created/appeared_in_branch/reopened/reopened_by_user -> present; fixed -> fixed; closed_by_user -> withdrawn |
   | observed_revision | `commit_oid` or `most_recent_instance.commit_sha` (empty for `*_by_user`) |
   | evidence_refs | alert `html_url`, delivery GUID |
   | untrusted | rule description, message text, severity, security_severity_level, tool version, any `provider` text |

   `updated_assignment` and actions outside the allowlist are acknowledged with
   204 and counted as ignored. Each delivery becomes one item. The batch shape
   is kept, so a future provider that delivers several findings per event maps
   to several items, never collapsed.

5. Network and exposure: no change. The route sits under `api.mctl.ai`, which
   already admits Traefik in `allow-mctl-api-ingress` and is already reached
   by the GitHub org webhook. The receiver must not rely on source IP for trust.
   HMAC is the authenticator. The GitHub hook IP allowlist is optional
   hardening, not a substitute.

6. Alerting: add `MctlApiSecurityWebhookFailures` to `mctl-api-alerts.yaml`,
   with a test in `vm-rules/tests/mctl-api-alerts_test.yaml`. It fires on the
   receiver's rejected or failed counter, proposed
   `mctl_security_webhook_deliveries_total{provider="github-code-scanning",result=~"signature_invalid|store_unavailable|rejected"}`
   above 0 over 15m. The metric name is pinned to whatever the prerequisite ships.

7. Runbook: add `docs/runbooks/security-finding-ingestion.md` covering:
   - the trust model (provider identity from channel, payload text untrusted);
   - Vault path and rotation (rotate GitHub hook secret and Vault together, then
     bump `ROLLOUT_MARKER`);
   - webhook registration on `mctlhq/mctl-api` (Code scanning alerts only,
     `application/json`, SSL verification on);
   - manual redelivery of failed deliveries through the repo hook deliveries API
     ("GitHub does not automatically redeliver");
   - the gap that absence produces no event;
   - rollback.

   Link it from `CLAUDE.md` "Secrets Management", as the other runbooks are.

### Failure and retry

- Store unavailable: the receiver answers 503. GitHub marks the delivery
  failed, the alert fires, and an operator redelivers per the runbook. This is
  a bounded failure, never a silent 2xx. If the prerequisite adds a durable
  outbox (as the pull-request path does), it may answer 202 after durable
  enqueue, with bounded relay retries and a dead-letter count in the same
  metric.
- A redelivery carries the same delivery GUID, so #774 answers `duplicate`.
  This is verified in T5.
- The next scheduled or PR scan re-uploads SARIF. That refreshes alerts but
  does not re-emit `created` for unchanged alerts, so the runbook redelivery
  remains the recovery path.

### Prerequisites outside this repository

- P1. mctl-api releases #774 (PR #799) and deploys it to `admins-mctl-api`.
- P2. In the mctl-api repo, `security.yml` gains a Trivy SARIF output and a
  `github/codeql-action/upload-sarif` step with `security-events: write`, run
  `if: always()` so the fail-closed gate is unchanged, and `category: trivy-fs`.
  File it as a narrow mctl-api issue.
- P3. In the mctl-api repo, the receiver route implements HMAC verification
  (constant-time), the allowlists, the mapping table above, provider binding,
  5xx on store unavailability, metrics, and no secret logging. File it as an
  mctl-api issue. It also decides the provider-credential question.

## Alternatives

A. Reuse the existing organization webhook and `GITHUB_WEBHOOK_SECRET`.
Dropped. The org hook spans every org repository, so the repository allowlist
would become the only scope limit. It shares a secret with pull-request
events, so compromise or rotation of one affects the other. Its current
handling of unknown event types is not observed. A repo-scoped hook with its
own secret is narrower at the same cost.

B. A standalone adapter service in tenant `admins`, deployed with
`base-service`, holding the webhook secret and a #774 provider token and
calling `POST /api/v1/security/observations`. Dropped as the default because it
adds a new repo, image, hostname, Cloudflare host entry and ingress, and puts
two credentials in a tenant namespace. It is the fallback if mctl-api declines
P3, and also the shape of the "bounded native adapter" if Code Scanning turns
out to be unavailable.

C. Push from CI directly: the Trivy job posts observations to #774 with a
provider token or GitHub OIDC. Dropped. It needs a native Trivy-JSON mapping
in each scanner workflow, which the issue warns against. It puts an ingest
credential in CI, and #774 accepts provider tokens, not Actions OIDC. It also
gives no `fixed` or `reopened` signals.

D. Argo Events or a Workflow webhook sensor. Dropped. Neither is deployed here,
and both would add a component only for this.

## Platform impact

- Backward compatibility: everything is behind `securityCodeScanning.enabled`
  (default false) and an optional envFrom secret. Disabled, the rendered
  manifests are unchanged. Enabled without the Vault value, only the route
  degrades (503).
- Migrations: none in gitops. #774 owns its DB migrations.
- Resources: one Secret and a few env vars. Load is negligible: one request per
  alert transition.
- Risks and mitigations:
  - Forged deliveries: HMAC with a dedicated secret, plus event, action, repo
    and tool allowlists. The provider identity is a server constant.
  - Provider spoofing or strength inflation: the payload is untrusted, and
    `max_strength: provider_claim`.
  - Secret leakage: Vault/ESO only, no-newline write, no logging (P3
    acceptance).
  - Silent loss: no 2xx without durable acceptance, an alert, and runbook
    redelivery. Automated redelivery is a follow-up.
  - ESO blast radius: a separate ExternalSecret file.
  - False resolution: `fixed` stays a claim. Verification stays with #778.
  - Weak subject (no purl): path plus line meets the #774 minimum. Recorded as
    a gap.
  - Pod restart on enable: the existing `ROLLOUT_MARKER` convention, with 2
    replicas and a PDB.
