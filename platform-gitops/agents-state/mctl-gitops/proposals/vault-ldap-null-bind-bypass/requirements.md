# Vault Terraform Provider LDAP Auth Bypass via Null Bind Default

## Context
CVE-2025-13357 affects the HashiCorp Vault Terraform Provider in versions v4.2.0 through v5.4.0. In those versions the `deny_null_bind` attribute for the LDAP auth method defaults to `false`, meaning that if the target LDAP server allows null (anonymous) binds, the Vault LDAP auth configuration will silently accept them. An attacker who can reach the LDAP server with a null bind could bypass Vault authentication entirely and obtain Vault tokens, subsequently accessing any secret managed by the platform.

Vault is the `vault-backend` ClusterSecretStore consumed by External Secrets Operator throughout the platform. Every ExternalSecret manifest in `platform-gitops/argo-workflows/secrets/` and in per-tenant service configs relies on this secret store. A Vault authentication bypass therefore has a platform-wide blast radius affecting both the `admins` and `labs` tenants. The remediation consists of two low-effort changes under `infrastructure/`: pinning the Vault Terraform Provider to a patched version and explicitly setting `deny_null_bind = true` in the Terraform LDAP auth resource.

## User stories
- AS a platform engineer I WANT the Vault Terraform Provider pinned to a patched version SO THAT LDAP auth configuration is generated with secure defaults.
- AS a security officer I WANT `deny_null_bind = true` explicitly enforced in Terraform config SO THAT null LDAP binds are rejected regardless of Vault provider default behavior.
- AS a tenant operator I WANT confidence that Vault authentication cannot be bypassed via null LDAP binds SO THAT secrets stored in Vault remain inaccessible to unauthenticated actors.

## Acceptance criteria (EARS)
- WHEN the Vault Terraform Provider version is declared in `infrastructure/` THE SYSTEM SHALL reference a version outside the affected range v4.2.0–v5.4.0.
- WHEN the Terraform LDAP auth method resource is applied THE SYSTEM SHALL include `deny_null_bind = true` as an explicit attribute.
- WHEN `terraform plan` is executed against the Vault LDAP auth configuration THE SYSTEM SHALL show no diff related to `deny_null_bind` (confirming it is already correctly set in state).
- WHEN an unauthenticated null bind attempt is made against the Vault LDAP auth endpoint THE SYSTEM SHALL reject the request with an authentication error.
- WHILE the Terraform provider version pin is being updated THE SYSTEM SHALL not destroy or recreate any existing Vault auth mount or policy (plan must show in-place update only).
- IF the Terraform apply step fails THE SYSTEM SHALL leave existing Vault LDAP auth configuration intact so that current secret consumers remain unaffected.

## Out of scope
- Upgrading the Vault server itself (v2.0.0 major upgrade is a separate planned proposal).
- Rotating LDAP credentials or service account passwords — incident response action, not in scope here.
- Changes to LDAP server configuration or LDAP server access controls.
- External Secrets Operator chart upgrade — tracked in a separate proposal.
