# Tasks: vault-ldap-null-bind-bypass

- [ ] 1. Identify the current Vault Terraform Provider version and the first patched release — DoD: The `required_providers` block in the relevant Terraform root module under `infrastructure/` is read and the current `hashicorp/vault` provider version constraint is documented. The HashiCorp provider registry is checked to confirm the earliest version outside the affected range v4.2.0–v5.4.0, and that version number is recorded in the PR description.

- [ ] 2. Update the Vault Terraform Provider version pin in `infrastructure/` (depends on 1) — DoD: The `required_providers` block is updated to constrain `hashicorp/vault` to the patched version (e.g., `>= <patched_version>, < <next_major>`). `terraform init -upgrade` runs successfully in a local or CI environment and `.terraform.lock.hcl` is updated to reflect the new provider hash.

- [ ] 3. Add `deny_null_bind = true` to the `vault_ldap_auth_backend` resource (depends on 2) — DoD: The Terraform resource definition for the Vault LDAP auth backend explicitly sets `deny_null_bind = true`. The attribute is present in the `.tf` source file and is not relying on provider defaults. A code review confirms no other LDAP auth backend resources in `infrastructure/` are missing this attribute.

- [ ] 4. Run `terraform plan` and review the output (depends on 3) — DoD: `terraform plan` produces output that shows only an in-place update (no destroy/recreate) for the `vault_ldap_auth_backend` resource. The plan shows `deny_null_bind: false -> true` (or confirms the attribute is already correctly set in state). The plan output is attached to the PR for review. No unexpected changes to other Vault resources are present.

- [ ] 5. Apply Terraform changes in the target environment (depends on 4) — DoD: `terraform apply` completes without errors in the target environment managing `secrets.mctl.ai`. The Vault LDAP auth backend configuration reflects `deny_null_bind = true` as confirmed via `vault auth tune` or the Vault API (`GET /v1/auth/ldap/config`).

- [ ] 6. Document resolution in decisions/ ADR (depends on 5) — DoD: A new ADR entry under `context/decisions/` records the provider version pin, the explicit `deny_null_bind` setting, the CVE reference (CVE-2025-13357), and the date of remediation.

## Tests

- [ ] T1. Terraform plan idempotency: After a successful `terraform apply`, re-run `terraform plan` and confirm the output shows `No changes`. This confirms the applied state matches the desired configuration and no drift remains.

- [ ] T2. Vault LDAP auth configuration verification: Query the Vault LDAP auth config via the Vault CLI or API (`vault read auth/ldap/config`) and confirm the `deny_null_bind` field is `true` in the live Vault configuration.

- [ ] T3. Null bind rejection test: Using an LDAP client configured for null (anonymous) bind, attempt to authenticate against Vault using the LDAP auth method. Confirm Vault returns an authentication error and does not issue a token. (If the LDAP server itself rejects null binds at the server level, document this fact and confirm the Vault-side setting is still enforced.)

- [ ] T4. Existing LDAP auth smoke test: Using a valid LDAP service account credential, authenticate against Vault via the LDAP auth method and confirm a token is issued with the expected policies. Confirm at least one ExternalSecret consumer (e.g., a test ExternalSecret in `admins`) can still resolve secrets from Vault after the change.

## Rollback
If the `terraform apply` produces unexpected results (e.g., auth backend destroy/recreate causes a Vault auth outage):

1. Do not proceed with `apply` if the plan shows destroy/recreate — treat as a blocker and investigate the provider resource lifecycle before continuing.
2. If `apply` has already been executed and Vault LDAP auth is broken, restore the previous provider version constraint in `infrastructure/` and re-run `terraform apply` to restore the auth backend to its previous state.
3. If Terraform state is corrupted, use `terraform import` to re-import the Vault LDAP auth backend resource and reconcile the state manually, then apply a corrective plan.
4. Notify on-call if Vault auth is unavailable, as this will break all ExternalSecret resolution across both tenants.
