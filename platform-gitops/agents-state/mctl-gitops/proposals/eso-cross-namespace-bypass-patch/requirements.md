# Upgrade External Secrets Operator to remediate CVE-2026-22822 Cross-Namespace Secret Access

## Context
CVE-2026-22822 (CVSS 8.8 Critical) is a vulnerability in External Secrets Operator (ESO) versions prior to the fix included in helm-chart-2.4.1 (released April 28, 2026). Any user with permission to create or update an `ExternalSecret` resource in any namespace can craft a manifest that causes the ESO controller — which runs with a broad ClusterRoleBinding — to fetch and surface secrets from any other namespace, defeating the namespace isolation model entirely. Because ESO + Vault (`secrets.mctl.ai`) is the only secrets pathway for both `admins` and `labs` tenants, this vulnerability means a compromised workload or misconfigured `labs` service could read `admins`-namespace secrets and vice versa.

The remediation is available in ESO helm-chart-2.4.1. Upgrading the pinned Helm chart version in this GitOps repository is the complete fix; no architectural changes to the Vault ClusterSecretStore or ExternalSecret manifests are needed.

## User stories
- AS a platform engineer I WANT ESO upgraded to helm-chart-2.4.1 SO THAT the cross-namespace secret access vector from CVE-2026-22822 is closed and namespace isolation is enforced by the operator.
- AS a security officer I WANT ExternalSecret resources to be constrained to their own namespace SO THAT a tenant cannot read secrets belonging to another tenant through the ESO controller.
- AS a `labs` tenant operator I WANT assurance that my ExternalSecrets cannot access `admins`-namespace secrets (and vice versa) SO THAT the principle of least privilege is maintained across tenants.
- AS a platform engineer I WANT the Vault ClusterSecretStore and all existing ExternalSecret manifests to continue working after the upgrade SO THAT secrets delivery to all services is uninterrupted.

## Acceptance criteria (EARS)
- WHEN the ESO Helm chart is updated to `helm-chart-2.4.1` and ArgoCD syncs the change, THE SYSTEM SHALL run ESO controller pods built from the patched image corresponding to helm-chart-2.4.1.
- WHEN a user creates an ExternalSecret in the `labs` namespace that references a secret path belonging to the `admins` namespace, THE SYSTEM SHALL deny the cross-namespace fetch and SHALL NOT surface the `admins` secret data in the `labs` namespace.
- WHEN the ESO upgrade rollout completes, THE SYSTEM SHALL successfully reconcile all existing ExternalSecrets in both `admins` and `labs` namespaces, delivering secrets to their target Kubernetes Secrets without error.
- WHILE the ESO controller is restarting during the upgrade, THE SYSTEM SHALL NOT delete or invalidate existing Kubernetes Secrets that were previously synced by ESO.
- IF the new ESO pods fail their readiness probe within five minutes of rollout, THE SYSTEM SHALL retain the previous pod revision via Kubernetes rolling-update guarantees.

## Out of scope
- Migrating from the Vault ClusterSecretStore to a namespace-scoped SecretStore (a separate architectural decision).
- Changes to Vault policies or Vault ACL beyond what is needed to run ESO v2.4.1.
- Remediating CVEs in ArgoCD or Argo Workflows (covered by separate proposals).
- Adding new ExternalSecret resources or changing the secrets structure for any service.
- Restricting which namespaces are permitted to create ExternalSecret resources at the admission-controller level (out of scope for this patch; can be a follow-on hardening proposal).
