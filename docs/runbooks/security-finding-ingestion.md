# SecurityFinding ingestion from GitHub Code Scanning

Path: Trivy -> SARIF -> GitHub Code Scanning -> `code_scanning_alert`
webhook -> mctl-api receiver -> SecurityFinding observation (mctlhq/.github#209,
mctlhq/mctl-gitops#2168). Needs mctl-api 4.125.0 or later.

Receiver route: `POST https://api.mctl.ai/api/v1/security/webhooks/github-code-scanning`.

## Trust model

- Provider identity comes from the route and the HMAC secret, never from
  payload text. The provider is fixed to `github-code-scanning`.
- The tenant comes from the `securityCodeScanning.repositories` mapping in
  `platform-gitops/bootstrap/templates/mctl-platform/mctl-api.yaml`.
- Strength is capped at `provider_claim`: a `fixed` alert does not resolve an
  occurrence. Alert text is stored as untrusted.
- Allowlists: repository, tool (`Trivy`) and action.
- The secret is dedicated: not the org pull-request webhook secret, and at
  least 32 characters.

## Response codes

| Code and result | Meaning |
|---|---|
| 202 `accepted` | Recorded as an observation. |
| 202 `duplicate` | Same delivery already recorded; nothing changed. |
| 202 `ignored` | `ping`, or a repository, tool or action outside the allowlists. |
| 401 `signature_invalid` | Missing or wrong `X-Hub-Signature-256`. |
| 503 `store_unavailable` | The store did not record it. Redeliver. |
| 503 (not configured) | Receiver disabled. Not counted by the metric. |

## Enabling (two separate merges)

Flags live under `securityCodeScanning` in `platform-gitops/bootstrap/values.yaml`.

1. Write the Vault value (no trailing newline, different from
   `platform/mctl-api/github-webhook`):
   `printf '%s' "$(openssl rand -hex 32)" | vault kv put secret/platform/mctl-api/github-code-scanning-webhook secret=-`
   Set `externalSecret: true`, and confirm ExternalSecret
   `mctl-api-security-code-scanning` is `SecretSynced`.
2. Set `receiver: true`. Wait for both pods to roll.
3. Register a webhook on `mctlhq/mctl-api`: the URL above, content type
   `application/json`, SSL verification on, the same secret, only the
   "Code scanning alerts" event. The `ping` must get 202 `ignored`.

Before step 2, check an admin `GET https://api.mctl.ai/api/v1/security/findings`
answers 200. A 503 `security_findings_store_unavailable` means the store is not
up; fix that first.

## Rotation

Rotate the Vault value and the hook secret together, then bump
`ROLLOUT_MARKER` in `mctl-api.yaml` (envFrom is read at container start).
Deliveries fail with 401 in the gap; redeliver them afterwards.

## Redelivery

GitHub does not redeliver automatically. For deliveries answered 401 or 503,
use the hook's Recent Deliveries page (or the hook deliveries API). A
redelivery of a recorded delivery answers `duplicate`.

## Known gaps

- Absence of events: no deliveries looks the same as no alerts. Check that
  Code Scanning analyses (`trivy-fs`) are still uploaded.
- The "not configured" 503 is not counted, so a silently disabled receiver
  does not fire `MctlApiSecurityWebhookFailures`. The `ping` check and the
  startup log line are the detection.

## Alert

`MctlApiSecurityWebhookFailures` (warning) fires on `signature_invalid`,
`rejected` or `store_unavailable` results in the last 15 minutes.

## Rollback

- Immediate: set the repository webhook inactive or delete it.
- GitOps: `receiver: false` (env vars and optional secretRef go away, pods
  roll, the route answers 503), then `externalSecret: false`.
- Store-wide: `SECURITY_FINDINGS_DISABLED: "true"` in `mctl-api.yaml` makes all
  `/api/v1/security*` routes answer 503 without touching data.
- Recorded observations are immutable evidence and are not deleted.
- Suspected exposure: rotate or delete the Vault value and the hook secret
  together.
