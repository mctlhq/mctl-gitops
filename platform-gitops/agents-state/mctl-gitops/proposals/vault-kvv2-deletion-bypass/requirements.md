# Vault KVv2 Secret Deletion Policy Bypass (CVE-2026-3605)

## Context
CVE-2026-3605 affects HashiCorp Vault's KVv2 secrets engine. An authenticated user who
holds any glob-based KVv2 policy (e.g., `secret/data/labs/*`) can invoke the metadata or
delete endpoint for paths they are not permitted to read, permanently destroying secrets
they have no read authorization over. This is a targeted denial-of-service vector via
secret destruction rather than data exfiltration.

Vault at `secrets.mctl.ai` is the single secret store for all tenants on the platform.
The `vault-backend` ClusterSecretStore is used by External Secrets Operator to materialize
secrets into both the `admins` and `labs` namespaces. If a tenant with glob-based KVv2
access deletes secrets belonging to another tenant or platform service, ExternalSecrets
will fail to refresh those secrets, causing workload disruption across the platform. This
CVE is a separate attack surface from CVE-2026-5052 (SSRF/ACME), which is already tracked
by the `vault-ssrf-acme-patch` proposal.

## User stories
- AS a platform operator I WANT Vault to enforce that a user cannot delete secrets outside
  their authorized read scope SO THAT a tenant cannot destroy another tenant's secrets.
- AS a security engineer I WANT all KVv2 glob-based policies to be audited and tightened
  SO THAT the blast radius of any compromised token is limited to the paths it can read.
- AS a `labs` tenant I WANT assurance that my secrets cannot be deleted by an `admins`
  user (or vice versa) SO THAT my workloads remain stable regardless of other tenants'
  actions.

## Acceptance criteria (EARS)
- WHEN an authenticated user with a glob-based KVv2 policy attempts to delete a secret at
  a path they are not authorized to read THE SYSTEM SHALL deny the delete operation and
  return a 403 response.
- WHEN a KVv2 delete or metadata destroy request is made THE SYSTEM SHALL evaluate the
  caller's policy against the specific secret path before executing the operation.
- WHILE Vault is running with the patched version THE SYSTEM SHALL enforce path-level
  authorization for all KVv2 delete, metadata-delete, and destroy operations.
- IF a KVv2 policy uses glob patterns THE SYSTEM SHALL scope delete and destroy permissions
  only to paths explicitly granted, not to paths matched solely by the glob on other
  operations.
- WHEN the Vault upgrade is applied THE SYSTEM SHALL complete the upgrade without
  disrupting ExternalSecrets synchronization for either tenant.
- IF upgrading Vault is not immediately feasible THEN THE SYSTEM SHALL have all glob-based
  KVv2 policies tightened to remove delete/destroy capabilities from paths not owned by
  the token holder as an interim mitigation.

## Out of scope
- CVE-2026-5052 (Vault SSRF/ACME) — already tracked by `vault-ssrf-acme-patch`.
- Changes to the External Secrets Operator deployment or ClusterSecretStore configuration
  (unless a policy change makes a SecretStore update necessary).
- Vault PKI engine, auth backends, or non-KVv2 secrets engines.
- Vault infrastructure changes (HA configuration, storage backend, TLS certs).
