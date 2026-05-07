# Vault v2.0.0 Major Version Upgrade and CVE-2026-5807 Remediation

## Context

The platform uses HashiCorp Vault as its secrets backend, accessed via External Secrets
Operator's `vault-backend` ClusterSecretStore. Four individual CVE proposals exist
(`vault-cve-2026-token-exposure`, `vault-kvv2-deletion-bypass`, `vault-ldap-null-bind-bypass`,
`vault-ssrf-acme-patch`) and address CVE-2026-4525, CVE-2026-3605, and CVE-2026-5052 in
isolation. However, no coordinated upgrade plan covers the v2.0.0 major release, which
introduces breaking changes — in particular path canonicalization enforcement (double-slash
paths are now rejected) — that require deliberate migration work across all ExternalSecret
manifests in `platform-gitops/`.

CVE-2026-5807 is an unauthenticated denial-of-service vulnerability: an attacker can
repeatedly initiate and cancel root-token generation or rekey operations, blocking all
legitimate operator workflows against the Vault cluster. It has no existing proposal and is
fixed exclusively in Vault v2.0.0. Without a coordinated upgrade plan, piecemeal patching
leaves CVE-2026-5807 open indefinitely and risks path-breakage misconfigurations when
individual patches are applied ahead of a structured migration.

## User stories

- AS a platform operator I WANT a single, sequenced upgrade plan for Vault v2.0.0
  SO THAT I can apply all security fixes without causing secrets-delivery outages or
  configuration drift.
- AS a security team member I WANT CVE-2026-5807 remediated and all four Vault CVEs closed
  together SO THAT the platform's secrets infrastructure is no longer exposed to
  unauthenticated denial-of-service or token-exposure attacks.
- AS an on-call engineer I WANT a documented rollback path for the Vault upgrade
  SO THAT I can recover quickly if the upgrade breaks ExternalSecret sync in production.

## Acceptance criteria (EARS)

- WHEN the Vault chart is upgraded to v2.0.0 THE SYSTEM SHALL continue delivering secrets
  to all ExternalSecret consumers without interruption throughout the transition.
- BEFORE the Vault chart version is changed in the `admins` namespace THE SYSTEM SHALL have
  all ExternalSecret manifests in `platform-gitops/services/` audited and corrected to remove
  double-slash paths.
- WHEN an ExternalSecret manifest contains a double-slash path after v2.0.0 is deployed THE
  SYSTEM SHALL fail the sync with a clear error rather than silently returning an empty secret.
- WHEN CVE-2026-5807 is present in the running Vault version THE SYSTEM SHALL be considered
  non-compliant and the upgrade SHALL be treated as a blocking security task.
- WHILE the staged upgrade is in progress (labs promoted, admins pending) THE SYSTEM SHALL
  continue resolving secrets in the `admins` namespace from the existing Vault v1.x instance.
- IF the `labs` Vault upgrade causes memory consumption to exceed the `labs` tenant memory
  limit THEN THE SYSTEM SHALL halt promotion to `admins` and a capacity review SHALL be
  triggered before proceeding.
- WHEN the upgrade is complete THE SYSTEM SHALL pass all CVE remediation checks for
  CVE-2026-4525, CVE-2026-3605, CVE-2026-5052, and CVE-2026-5807.
- IF the upgrade must be rolled back THE SYSTEM SHALL restore the previous Vault chart
  version via a documented Git revert procedure without data loss.

## Out of scope

- Migrating from Vault to any alternative secrets backend (e.g., Kubernetes-native Secrets,
  AWS Secrets Manager, Doppler).
- Individual CVE patch proposals for CVE-2026-4525, CVE-2026-3605, CVE-2026-5052 — those
  are addressed as separate prior proposals and are superseded by this upgrade plan.
- Vault Enterprise features or Enterprise-specific configuration changes.
- Changes to the External Secrets Operator version beyond confirming ESO compatibility with
  Vault v2.0.0.
