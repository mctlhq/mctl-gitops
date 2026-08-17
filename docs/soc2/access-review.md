# Access review procedure

Cadence: **quarterly**, or after any offboarding. Owner: founder.
Output: dated notes under `docs/soc2/evidence/access-review-YYYY-QN.md`.

## Checklist

1. GitHub org `mctlhq` members and outside collaborators. Confirm each
   still needs access. Confirm org 2FA requirement:
   `gh api orgs/mctlhq --jq .two_factor_requirement_enabled` (must be
   `true` before CPA fieldwork).
2. GitHub Apps and Actions secrets: no extra org secrets; `gitops-bump`
   token still least-privilege.
3. Vault: list policies and Kubernetes/JWT roles. Remove unused.
4. Argo CD `policy.csv` in `platform-gitops/argocd/values.yaml`. Tenant
   roles must not have `exec`.
5. Backstage / portal admins (`isAdmin`, `ADMIN_USERS`).
6. Cluster: kubeconfig holders (operator laptop + CI). No standing
   cluster-admin for agents.
7. Record exceptions (admin ruleset bypass, bot main writes) still
   match `compensating-controls.md`.

## First review

Not yet performed. Schedule: 2026-Q3 close (before any CPA start).
