# ESO CVE-2026-22822 — Cross-Namespace Secret Access via getSecretKey

## Context

CVE-2026-22822 (CVSS 9.3 Critical, published 2026-01-20) is a vulnerability in External Secrets
Operator that allows any namespace with permission to create an ExternalSecret to invoke the
`getSecretKey` path against `ClusterSecretStore` and retrieve secrets that belong to a different
namespace's Vault path. The vulnerability bypasses the tenant isolation boundary that the
`ClusterSecretStore` model is supposed to enforce.

On this platform ESO is the sole secret delivery channel for all tenants. The single
`ClusterSecretStore` named `vault-backend` serves both the `admins` and `labs` namespaces via
Vault at `secrets.mctl.ai`. If CVE-2026-22822 is left unpatched, a workload or pipeline running in
the `labs` tenant could read secrets that are scoped to `admins`, and vice versa. This fully
invalidates the tenant trust model. Because `labs` is also near its memory limit, any remediation
that materially increases operator memory footprint in that namespace must be flagged as risky.

## User stories

- AS a platform operator I WANT the ESO operator upgraded to a version that patches
  CVE-2026-22822 SO THAT cross-namespace secret reads through `getSecretKey` are no longer
  possible.
- AS a tenant admin for `admins` I WANT assurance that secrets stored under the `admins` Vault
  path cannot be read by workloads in the `labs` namespace SO THAT the tenant isolation boundary
  is maintained.
- AS a tenant admin for `labs` I WANT the same isolation guarantee in the opposite direction SO
  THAT `labs` secrets are not readable from `admins`.
- AS a platform operator I WANT the fix applied with no increase in memory footprint inside
  `labs` SO THAT the tenant's existing memory budget is not exceeded.

## Acceptance criteria (EARS)

- WHEN an ExternalSecret resource in the `labs` namespace references a Vault path scoped to the
  `admins` namespace THE SYSTEM SHALL deny the secret read and surface a `SecretSyncError` status
  condition on that ExternalSecret.
- WHEN an ExternalSecret resource in the `admins` namespace references a Vault path scoped to
  the `labs` namespace THE SYSTEM SHALL deny the secret read and surface a `SecretSyncError`
  status condition on that ExternalSecret.
- WHEN the ESO operator is upgraded to the patched version THE SYSTEM SHALL leave all
  previously-synced Kubernetes Secrets intact and in service during the rolling update.
- WHEN the upgrade is applied THE SYSTEM SHALL restore all legitimate ExternalSecret resources
  to `Ready=True` within five minutes of the operator pod becoming available.
- WHILE the ESO operator pod is restarting during the upgrade THE SYSTEM SHALL preserve all
  Kubernetes Secrets that were already synced (no deletion of existing secret data).
- IF the patched ESO Helm chart version causes a CRD schema change THEN THE SYSTEM SHALL apply
  the updated CRDs before rolling the operator Deployment so that existing ExternalSecret objects
  remain valid.
- IF the memory usage of the ESO operator pod in the `admins` namespace increases by more than
  10 % after the upgrade THEN THE SYSTEM SHALL surface this in the post-upgrade monitoring check
  and the change shall be flagged for review before the rollout is finalised.
- WHEN a CI pipeline validates ExternalSecret manifests THE SYSTEM SHALL reject any manifest
  that attempts to reference a ClusterSecretStore namespace path not belonging to the submitting
  tenant namespace.

## Out of scope

- Migrating from `ClusterSecretStore` to per-namespace `SecretStore` resources as the
  primary architecture change (considered as an alternative; not part of this proposal).
- Changes to Vault policies or Vault AppRole/Kubernetes auth configurations beyond what is
  required to verify isolation after the ESO upgrade.
- Remediation of CVE-2026-34165, CVE-2026-33762 (covered by `eso-cve-patch`), or
  CVE-2026-34984 (covered by `eso-dns-exfil-patch`).
- Adding new tenants or namespace structures.
- ESO feature work unrelated to this CVE.
