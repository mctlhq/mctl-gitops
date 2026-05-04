# ArgoCD CVSS 9.6 — Plaintext Secret Extraction via ServerSideDiff

## Context
CVE-2026-43824 (GHSA-3v3m-wc6v-x4x3, CVSS 9.6 Critical) was disclosed against ArgoCD and patched in v3.3.9 and v3.2.11. The vulnerability allows any authenticated read-only ArgoCD user to extract the full plaintext content of Kubernetes Secrets by invoking the ServerSideDiff endpoint when the `IncludeMutationWebhook=true` flag is active. Because the platform uses ArgoCD (`ops.mctl.ai`) as the single reconciliation engine for both the `admins` and `labs` tenants, and because secrets are managed platform-wide through Vault and ExternalSecrets, an exploited read-only account can exfiltrate credentials across all tenants.

The current ArgoCD version in use predates the v3.3.9 patch. The fix is a targeted version-pin update with no CRD migrations, no API breaking changes, and no ApplicationSet schema changes. Immediate remediation is warranted given the CVSS score and the broad blast radius of the affected endpoint.

## User stories
- AS a platform engineer I WANT ArgoCD pinned to v3.3.9 or later SO THAT the ServerSideDiff secret extraction path is closed and read-only accounts cannot exfiltrate Secret data.
- AS a security officer I WANT assurance that ArgoCD is not running a version affected by CVE-2026-43824 SO THAT audit findings and compliance requirements can be marked resolved.
- AS a tenant operator I WANT my tenant's Kubernetes Secrets to remain confidential within ArgoCD SO THAT service credentials are not exposed to users with only read access.

## Acceptance criteria (EARS)
- WHEN the ArgoCD version deployed in the cluster is queried THE SYSTEM SHALL report v3.3.9 or later.
- WHEN an authenticated read-only user calls the ServerSideDiff endpoint with `IncludeMutationWebhook=true` THE SYSTEM SHALL not return plaintext Secret values.
- WHEN the ArgoCD image tag is updated in the GitOps repository THE SYSTEM SHALL reference an image digest that corresponds to the official v3.3.9 release.
- WHILE ArgoCD is upgrading (rollout in progress) THE SYSTEM SHALL keep at least one ArgoCD server pod running to maintain reconciliation availability.
- IF the ArgoCD upgrade rollout fails health checks THE SYSTEM SHALL roll back automatically to the previous version via the ArgoCD ApplicationSet sync policy.
- WHEN the upgrade is complete THE SYSTEM SHALL successfully sync all existing Applications in both `admins` and `labs` tenants without manual intervention.

## Out of scope
- Rotating or invalidating secrets that may have been exposed prior to this patch (this is a separate incident-response action).
- Disabling or removing the ServerSideDiff feature itself — only the vulnerable version is replaced.
- Upgrading any other Argo project component (Argo Workflows, Argo Rollouts, argocd-image-updater) in this proposal.
- Introducing RBAC changes or restricting existing read-only roles — the patch is the sole remediation.
