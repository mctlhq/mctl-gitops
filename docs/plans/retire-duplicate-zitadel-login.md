# Retire the duplicate ZITADEL login

Owner approved on 2026-10-16: transfer ERPact `frappe` and Kubernetes `erpact`
from tenant user `erpact/mashkovd` to the existing platform-admin account
`dmitrii` (login `dmitrii.mashkov`), verify both grants, then delete the tenant
user. Preserve the destination user ID and its `kubernetes-admins` role.
Personal attributes remain in Vault.

1. Add grant-only ERPact and additional Kubernetes tenant-role opt-ins to IaC.
2. Set destination Vault flags `frappe_access: true`, `kubectl_tenants: [erpact]`.
3. Reconcile and verify destination grants before touching the source.
4. Permit only the exact source addresses in `allowedDeletes`, remove its
   Vault field, reconcile, verify deletion, then clear the delete exception.
   Addresses: `zitadel_human_user.tenant["erpact/mashkovd"]`,
   `zitadel_user_grant.erpact_frappe_tenant["erpact/mashkovd"]`,
   `zitadel_user_grant.kubernetes_tenant["erpact/mashkovd"]`.
5. Verify the surviving login and report the MCTL duplicate-principal state.
   Do not delete audit-referenced principals or write identity tables directly.

Current state: implementation and tests in progress; no user or grant changed.
