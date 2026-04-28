# Vault PKI ACME SSRF Patch (CVE-2026-5052 / HCSEC-2026-06)

## Context
Vault CE versions 1.14.0–1.21.4 contain a Server-Side Request Forgery (SSRF) vulnerability in
the PKI ACME challenge validation flow (CVE-2026-5052 / HCSEC-2026-06, published 2026-04-16).
The http-01 and tls-alpn-01 challenge validators did not reject requests to local network targets.
An attacker with DNS control can redirect ACME validation requests to internal cluster services,
causing information disclosure and potential lateral movement within the platform network.

Vault at `secrets.mctl.ai` is the sole secret store for the entire platform. Every tenant
(`admins` and `labs`) depends on it through the External Secrets Operator and the
`vault-backend` ClusterSecretStore. Exploitation of this vulnerability could expose credentials
for all platform services simultaneously. The fix ships in Vault CE v2.0.0, which also contains
breaking changes in the Docker helper and auth endpoint interface; these must be addressed during
the upgrade. A lower-effort mitigation path — disabling ACME challenge entirely if it is not
actively used — is available and must be evaluated first.

## User stories
- AS a platform security engineer I WANT the Vault SSRF vulnerability remediated SO THAT an
  attacker with DNS control cannot redirect ACME validation requests to internal platform services.
- AS a platform engineer I WANT the Vault upgrade to v2.0.0 breaking changes documented and
  applied safely SO THAT no tenant secrets become inaccessible during or after the upgrade.
- AS a tenant operator I WANT secrets to remain available throughout the Vault upgrade SO THAT
  running services are not interrupted.
- AS a security officer I WANT CVE-2026-5052 remediated promptly SO THAT the platform's exposure
  window is minimised following the public disclosure on 2026-04-16.

## Acceptance criteria (EARS)

### SSRF remediation
- WHEN Vault PKI ACME challenge validation is invoked THE SYSTEM SHALL reject any validation
  target that resolves to an RFC-1918 or link-local address (loopback, 10.0.0.0/8, 172.16.0.0/12,
  192.168.0.0/16, 169.254.0.0/16, ::1).
- WHEN Vault is deployed THE SYSTEM SHALL run a version that is not affected by CVE-2026-5052
  (either Vault CE v2.0.0+ or a configuration-level mitigation that disables ACME challenge).
- IF ACME challenge functionality is not actively used by any tenant THEN THE SYSTEM SHALL disable
  the ACME challenge endpoint in Vault PKI configuration as the primary mitigation path.

### Upgrade safety
- WHEN Vault CE v2.0.0 is deployed THE SYSTEM SHALL have all v2.0.0 breaking changes
  (Docker helper changes, auth endpoint requirement changes) applied and verified before
  the new image is rolled out.
- WHEN the Vault version is changed THE SYSTEM SHALL reflect that change as a git commit to the
  Terraform configuration under `infrastructure/`.
- WHILE the Vault upgrade is in progress THE SYSTEM SHALL preserve all existing Kubernetes Secrets
  that were previously synced by the External Secrets Operator so that tenant workloads continue
  to operate using cached credentials.
- WHEN the upgrade is complete THE SYSTEM SHALL have the `vault-backend` ClusterSecretStore in
  `Ready` status and all ExternalSecret resources in `Synced` status across all tenants.

### Memory safety for labs
- WHEN Vault CE v2.0.0 is deployed THE SYSTEM SHALL be assessed for memory footprint change
  relative to the prior version before rollout.
- IF Vault CE v2.0.0 increases Vault pod memory consumption beyond the available headroom for the
  `labs` tenant THEN THE SYSTEM SHALL not proceed with the upgrade until resource limits are
  adjusted or the mitigation-only path (ACME disable) is taken instead.

### Rollback
- IF Vault v2.0.0 fails health checks after rollout THEN THE SYSTEM SHALL support rollback to
  the previous Vault version via git revert of the Terraform change without permanent data loss.

## Out of scope
- Migrating from Vault to an alternative secret backend (e.g., AWS Secrets Manager, Doppler).
- Changing the `vault-backend` ClusterSecretStore provider type or Vault auth method (AppRole,
  Kubernetes auth) unless required by v2.0.0 breaking changes.
- Rotating or auditing the content of Vault policies and secret paths.
- Upgrading the External Secrets Operator itself (tracked separately).
- Changing ACME certificate issuance workflows outside of the PKI challenge mitigation.
- Capacity expansion of the `labs` tenant (a separate platform capacity proposal if needed).
