# Vault KVv2 Secret Deletion Policy Bypass (CVE-2026-3605)

## Context

CVE-2026-3605 is a policy bypass vulnerability in HashiCorp Vault: an authenticated user whose
KVv2 policy contains a glob path (e.g., `secret/data/labs/*`) can delete secrets at those paths
even when the policy grants no `read` or `list` capabilities. The deletion is silent — the secret
disappears without triggering an explicit access-denied event on the read path.

On the mctl platform, Vault (`secrets.mctl.ai`) is the single secret store for every tenant.
All secrets flow through the `vault-backend` ClusterSecretStore (External Secrets Operator) into
Kubernetes ExternalSecret objects. If a tenant's secrets are unexpectedly deleted, their
ExternalSecrets will fail to refresh, pods will crash on restart due to missing environment
variables or mounted secrets, and workloads across the affected tenant will stop. Because `labs`
is near its memory limit, a cascading crash-restart loop there is especially risky.

## User stories

- AS a platform operator I WANT all KVv2 glob policies replaced with explicit path policies SO
  THAT no authenticated user can delete secrets outside their authorized scope.
- AS a security engineer I WANT Vault upgraded to the release that patches CVE-2026-3605 SO THAT
  the underlying enforcement defect is eliminated, not just mitigated by policy rewrites.
- AS a `labs` tenant I WANT my secrets protected against deletion by other tenants SO THAT my
  workloads remain stable even if another tenant's credentials are compromised.

## Acceptance criteria (EARS)

- WHEN a Vault token with a glob-based KVv2 policy attempts to delete a secret path not explicitly
  granted in its policy, THE SYSTEM SHALL return a 403 Forbidden response.
- WHEN the policy audit is complete, THE SYSTEM SHALL have no KVv2 policy that grants `delete` or
  `destroy` capabilities via a glob pattern without a corresponding explicit `read` grant.
- IF the Vault server version is earlier than the release that patches CVE-2026-3605, THE SYSTEM
  SHALL have Phase 1 policy tightening applied as an interim mitigation before the upgrade window.
- WHEN Vault is upgraded to the patched release, THE SYSTEM SHALL pass all existing ESO
  ExternalSecret sync checks within 5 minutes of the upgrade completing.
- WHILE Phase 1 policy tightening is in effect, THE SYSTEM SHALL not break any existing
  ExternalSecret that legitimately reads secrets under a glob-matched path.
- WHEN the remediation is complete, THE SYSTEM SHALL record the updated policy files and the Vault
  version bump in a git commit in this repository.

## Out of scope

- CVE-2026-5052 (Vault PKI ACME SSRF) — tracked separately in `vault-ssrf-acme-patch`.
- Changes to the External Secrets Operator itself.
- Migration away from Vault to a different secret store.
- Rotation of existing tenant secrets (separate operational task, not gated on this proposal).
