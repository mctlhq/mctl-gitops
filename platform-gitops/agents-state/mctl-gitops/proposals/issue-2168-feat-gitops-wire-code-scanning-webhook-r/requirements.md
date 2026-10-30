# Wire the GitHub Code Scanning webhook receiver for SecurityFinding (mctlhq/.github#209 slice 3, supersedes #2103)

## Context

mctlhq/.github#209 adds a `SecurityFinding v1` contract in three slices. Slices 1 and 2 have shipped:
- mctl-api `4.124.0` released the store and the authenticated observation API (mctlhq/mctl-api#774).
- mctl-api `4.125.0` released the Trivy SARIF upload into GitHub Code Scanning (mctlhq/mctl-api#801/#808).
- The same release added an HMAC-verified receiver, `POST /api/v1/security/webhooks/github-code-scanning` (mctlhq/mctl-api#802/#809).

`admins-mctl-api` already runs `4.125.0`. The receiver ships disabled by configuration. Nothing in `mctl-gitops` sets the three inputs it needs:
- `SECURITY_PROVIDERS` (helm `securityProviders`);
- `SECURITY_GITHUB_CODE_SCANNING` (helm `securityCodeScanning`);
- the channel credential `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`.

No GitHub webhook targets the route yet. This issue covers only the GitOps plumbing, the operator runbook and the end-to-end proof. The provider path is settled:

```text
Trivy -> SARIF -> GitHub Code Scanning -> code_scanning_alert -> mctl-api receiver -> #774 observation
```

This matters for two reasons. It is the first real provider for the SecurityFinding lifecycle. It is also the first place where provider identity has to come from a verified channel rather than from payload text. A wiring mistake has real costs: a secret in public Git, a receiver that is silently disabled, or a store that answers 2xx without recording anything. Each of these would undermine the trust model that #774 and #809 depend on.

## User stories

- AS the platform owner I WANT `mctl-api` to accept signed `code_scanning_alert` deliveries from `mctlhq/mctl-api` SO THAT Trivy findings become #774 observations without a new service.
- AS a security reviewer I WANT the webhook secret delivered only from Vault through ESO, in its own ExternalSecret, SO THAT the public repo never holds it and a missing key cannot take other mctl-api credentials down.
- AS the #809 remediation runner I WANT observations from this provider capped at `provider_claim` and attributed to a tenant from server configuration SO THAT a webhook can never resolve or re-scope an occurrence on its own.
- AS an on-call operator I WANT an alert on rejected, unauthenticated or store-unavailable deliveries, plus a runbook for redelivery SO THAT a failed delivery is noticed and recovered, never silently lost.

## Acceptance criteria (EARS)

Configuration and secrets
- WHEN `securityCodeScanning.externalSecret` is `true` in `platform-gitops/bootstrap/values.yaml` THE SYSTEM SHALL render ExternalSecret `mctl-api-security-code-scanning` in namespace `mctl-api`. It maps exactly one key, `GITHUB_CODE_SCANNING_WEBHOOK_SECRET`, from Vault `platform/mctl-api/github-code-scanning-webhook`, property `secret`.
- WHILE both `securityCodeScanning` flags are `false` THE SYSTEM SHALL render the bootstrap chart byte-identical to the render before this change.
- WHEN `securityCodeScanning.receiver` is `true` THE SYSTEM SHALL render the `admins-mctl-api` Helm values with these additions:
  - `securityProviders` with exactly one entry: `ref: github-code-scanning`, `max_strength: provider_claim`, `tenants: [admins]`;
  - `securityCodeScanning` with `repositories: {mctlhq/mctl-api: admins}`, `tools: [Trivy]` and the six supported actions;
  - `mctl-api-security-code-scanning` appended to `envFromOptionalSecrets`.
- THE SYSTEM SHALL keep every secret value out of Git. `values.yaml`, `mctl-api.yaml`, the ExternalSecret and the runbook contain only references.
- THE SYSTEM SHALL keep the new credential separate from `GITHUB_WEBHOOK_SECRET`: a distinct Vault path and a distinct ExternalSecret.
- IF the Vault entry is missing or the ExternalSecret fails to sync THEN THE SYSTEM SHALL keep `mctl-api-secrets` and `mctl-api-events` synced and the mctl-api pods starting. Only the receiver degrades, answering 503.
- THE SYSTEM SHALL NOT set `securityProviderTokensSecret` or `MCTL_SECURITY_PROVIDER_TOKENS` for this provider. The receiver writes in-process and uses no bearer token.

Rollout ordering
- WHEN the receiver flag is enabled THE SYSTEM SHALL already hold a synced `mctl-api-security-code-scanning` Secret, created by an earlier, separate merge. The pod roll caused by the new env then reads the secret at container start.

Trust and identity (verified end to end; behaviour implemented by mctl-api 4.125.0)
- WHEN a delivery carries a missing or wrong `X-Hub-Signature-256` THE SYSTEM SHALL answer 401 `signature_invalid` and record no observation.
- WHEN a correctly signed delivery names a repository, tool, event or action outside the configuration THE SYSTEM SHALL answer 202 `ignored` and record no observation.
- WHEN a correctly signed `code_scanning_alert` for `mctlhq/mctl-api` and tool Trivy arrives THE SYSTEM SHALL record one observation with these properties:
  - `provider_ref` `github-code-scanning` and tenant `admins`;
  - `source_finding_id` `github:mctlhq/mctl-api/code-scanning/<alert number>`;
  - the alert's path and location;
  - the commit as `observed_revision`.

  Any payload `provider` text and all severity or description text SHALL be stored only as untrusted data.
- WHEN GitHub redelivers the same delivery THE SYSTEM SHALL answer `duplicate` and create no new observation or occurrence.
- WHEN one SARIF upload produces N alerts THE SYSTEM SHALL record N observations.
- WHEN the same rule is reported at two different paths THE SYSTEM SHALL keep two distinct occurrences.
- IF the #774 store is unavailable THEN THE SYSTEM SHALL answer 503 `store_unavailable`, and GitHub SHALL show the delivery as failed. The alert SHALL fire within its window, and a runbook redelivery after recovery SHALL record the observation exactly once.
- THE SYSTEM SHALL NOT start remediation, create WorkItems or start DevLoops from a webhook delivery.

Observability and operations
- WHEN `mctl_security_webhook_deliveries_total{provider="github-code-scanning"}` increases with result `signature_invalid`, `rejected` or `store_unavailable` within 15 minutes THE SYSTEM SHALL fire the `warning` alert `MctlApiSecurityWebhookFailures`.
- THE SYSTEM SHALL document, in `docs/runbooks/security-finding-ingestion.md`:
  - the trust model;
  - the Vault write without a trailing newline;
  - the webhook registration (Code scanning alerts only);
  - rotation;
  - manual redelivery;
  - the absence-of-event gap;
  - rollback.
- IF the production #774 store is not initialised (an admin read of `/api/v1/security/findings` answers 503) THEN THE SYSTEM SHALL record that as a blocking rollout step, fixed before the receiver flag is enabled.

## Out of scope

- SecurityFinding persistence, normalization, dedup and lifecycle (mctlhq/mctl-api#774, released).
- Receiver code, scanner workflow and SARIF upload (mctl-api#801/#802, released).
- Remediation and verification execution (mctlhq/mctl-agents#809).
- A new scanner, a generic SARIF ingestion platform, or a standalone adapter service.
- A Claude Security adapter.
- UI.
- Auto-remediation and auto-merge.
- Providers other than Trivy, and repositories other than `mctlhq/mctl-api`.
- Generating or storing the secret value. The owner creates it in Vault.
- Moving the #774 store to a dedicated database (see Open questions).

## Open questions

- Store database. In 4.125.0, `cmd/api/main.go` resolves `SECURITY_FINDINGS_DB_URL`, then `EVIDENCE_DB_URL`, then `AUDIT_DB_URL`. Only `AUDIT_DB_URL` is set, so the store lives in the shared `mctl-api` database. That is the fallback #774 designed for, but `LIFECYCLE_DB_URL` set a precedent of dedicated databases. This proposal keeps the fallback, documents it in a comment, and verifies that the store is up. Moving to a dedicated `mctl-security-findings` database is left to the owner as a follow-up.
- Live store state was not observed. `mctl_get_service_logs(admins, mctl-api)` returned 0 lines, so the startup log (`security findings store init failed` or not) could not be read. Task 1 verifies it with an admin read before rollout.
- Code Scanning alerts, analyses and repository hooks on `mctlhq/mctl-api` could not be read: the investigator token got 403. The repository is public and `security.yml` uploads category `trivy-fs` at 4.125.0. Whether alerts already exist, and whether a stray hook targets the route, is verified in task 1.
- Store-unavailable proof. Setting `SECURITY_FINDINGS_DISABLED: "true"` for the test window disables every `/api/v1/security*` route in production. That is acceptable only while #809 is not yet consuming the store. If the owner declines, T9 falls back to the mctl-api unit tests plus GitHub's record of a 503 delivery from the receiver's "not configured" path.
- The receiver's "not configured" 503 (`codeScanningReady` false) does not increment `mctl_security_webhook_deliveries_total`, so the alert cannot see a misconfigured receiver. Detection relies on GitHub's delivery log, the startup error log and the T-checks. A follow-up metric in mctl-api is suggested, not required here.
- GitHub does not emit an event when a rescan finds nothing. Verification by absence therefore stays an active #809 scanner rerun. `fixed` deliveries are capped at `provider_claim`.
