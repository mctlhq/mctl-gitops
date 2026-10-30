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

## Verified completion (2026-10-16)

- PR #1914 merged as `6b079832d`; current-head Claude review approved after
  fixing both P2 findings. Full root tests: 87 passed.
- `zitadel-consolidate-grant-9g2wb` succeeded (Vault admins version 7).
  `zitadel-iac-transfer-20261016` succeeded and reported no remaining changes.
  Live destination grants verified before source retirement: ERPAct `frappe`,
  Kubernetes `erpact` plus the existing `kubernetes-admins`.
- `zitadel-consolidate-retire-pzbn9` succeeded (Vault tenant-users version 13).
  `zitadel-iac-retire-20261016` succeeded: 0 added, 0 changed, exactly 3
  destroyed (the approved source user and its two grants).
- Live ZITADEL projections confirm source user/grant counts are both zero;
  destination username and all three transferred/preserved role keys remain.
- This follow-up clears `allowedDeletes`. The former inline workflow was
  rejected before execution; no write occurred from that attempt.
- MCTL audit/identity history is retained. The deleted ZITADEL subject's old
  principal is not merged into the destination and no identity table is edited
  directly. Sign in as `dmitrii.mashkov` for the surviving platform account.
