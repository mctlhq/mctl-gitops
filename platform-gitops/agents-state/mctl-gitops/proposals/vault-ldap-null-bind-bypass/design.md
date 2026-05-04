# Design: vault-ldap-null-bind-bypass

## Current state
Vault (`secrets.mctl.ai`) is the authoritative secret backend for the platform. External Secrets Operator consumes it via the `vault-backend` ClusterSecretStore, which is referenced by ExternalSecret manifests across `platform-gitops/argo-workflows/secrets/` and in per-tenant service directories under `platform-gitops/services/`. Vault's LDAP auth method is provisioned and managed via Terraform under `infrastructure/`.

The Vault Terraform Provider currently in use falls within the affected version range v4.2.0–v5.4.0 for CVE-2025-13357. Within this range the provider defaults `deny_null_bind` to `false` when creating or updating the `vault_ldap_auth_backend` resource. If the LDAP server configured in Vault permits null (anonymous) binds, Vault will accept unauthenticated LDAP bind requests and issue tokens, bypassing the intended authentication requirement. The existing Terraform state may or may not have `deny_null_bind` stored explicitly; if it was not set at resource creation time, the value in Vault is `false`.

## Proposed solution
Two coordinated changes in `infrastructure/` (Terraform):

1. **Provider version pin:** Update the `required_providers` block in the relevant Terraform root module to pin `hashicorp/vault` provider to the first patched release outside the v4.2.0–v5.4.0 range. Based on the advisory and available releases, the target is the earliest available patched version (to be confirmed against the HashiCorp provider registry at time of implementation; the constraint should be `>= <patched_version>` with an upper bound to prevent accidental major-version drift).

2. **Explicit `deny_null_bind = true`:** In the `vault_ldap_auth_backend` Terraform resource definition, add or update the `deny_null_bind` attribute to `true`. This ensures the setting is explicit in code and in Terraform state regardless of provider default behavior, and survives any future provider upgrade.

`terraform plan` must be reviewed before `terraform apply` to confirm:
- The provider upgrade does not trigger unexpected resource replacements.
- The `deny_null_bind` change results in an in-place update to the existing auth backend (not a destroy/recreate).

After `terraform apply`, Vault should be verified to reject null bind attempts against the LDAP auth endpoint.

## Alternatives

### Option A: Upgrade the Vault Terraform Provider to the latest available version (v5.x latest or v6.x)
Jumping to the very latest provider version in one step introduces a wider set of changes and potential behavioral differences across all Vault resources managed in `infrastructure/`. Given that the goal is a targeted security fix, a minimal version bump to the first patched release is preferred to reduce regression risk. A broader provider upgrade can be planned as a maintenance proposal.

### Option B: Manually set `deny_null_bind = true` via the Vault HTTP API without touching Terraform
A direct Vault API call (`POST /v1/auth/ldap/config`) could set `deny_null_bind = true` immediately. However, this would create drift between Terraform state and live Vault configuration, breaking idempotency and IaC auditability. The next `terraform apply` would overwrite the manual change. Dropped in favour of the Terraform-first approach.

### Option C: Disable the Vault LDAP auth method entirely during remediation
Disabling LDAP auth would immediately eliminate the attack surface but would break all platform services that authenticate to Vault via LDAP tokens, causing a service outage. Not viable as a remediation approach. Dropped.

## Platform impact

### Migrations
No Vault data migrations. The Terraform change is an in-place update to the LDAP auth backend configuration. Existing Vault policies, roles, and secrets are unaffected.

### Backward compatibility
Existing LDAP users with valid credentials are unaffected — they continue to bind and authenticate normally. Only null (anonymous) binds will be newly rejected. If any existing automation was inadvertently relying on null binds (which would represent a misconfiguration), it will break; this is the intended behavior.

### Resource impact
No change to Vault server resource usage. The Terraform provider version update runs only at plan/apply time in CI and does not affect runtime pod memory or CPU. No impact on the `labs` tenant memory envelope. This proposal does not increase memory consumption in any tenant.

### Risks and mitigations
- **Risk:** `terraform plan` shows a destroy/recreate for the LDAP auth backend rather than an in-place update, causing a temporary auth outage.
  - **Mitigation:** Review the plan output carefully before applying. If destroy/recreate appears, investigate provider resource lifecycle behavior for the pinned version and open a separate incident track rather than proceeding with apply.
- **Risk:** Provider version constraints conflict with other Vault resources managed in the same Terraform root module.
  - **Mitigation:** Run `terraform init -upgrade` in a non-production environment first and review `terraform plan` for unexpected changes across all Vault resources.
- **Risk:** The LDAP server in use does not permit null binds, making this a low-exploitability issue in practice; however, the fix should still be applied for defense-in-depth and audit compliance.
  - **Mitigation:** Proceed with remediation regardless of LDAP server null-bind policy; the explicit `deny_null_bind = true` is a hardening measure with no operational downside.
