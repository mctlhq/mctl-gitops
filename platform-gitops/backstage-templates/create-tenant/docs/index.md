# 🏗️ Create Tenant

Provision a new tenant (team) on the mctl.me platform — creates a Kubernetes namespace with quotas, a Vault policy, and ArgoCD RBAC.

## When to use

Use this template when you want to:
- Onboard a **new team** to the platform
- Create an isolated namespace with resource quotas and network policies

## Inputs

| Field | Required | Description |
|---|---|---|
| Tenant Name | ✅ | Lowercase DNS-safe slug (e.g. `my-team`). Used as the Kubernetes namespace name. |
| Display Name | ✅ | Human-readable name shown in Backstage and dashboards |
| Description | | Brief description of the team |
| GitHub Team Slug | | GitHub team in the `mctlhq` org for OAuth + ArgoCD RBAC. Defaults to tenant name. |
| Contact Email | | Team email for platform notifications |
| CPU Requests | | Total CPU requests across all pods (default: `4`) |
| CPU Limits | | Total CPU limits (default: `8`) |
| Memory Requests | | Total memory requests (default: `8Gi`) |
| Memory Limits | | Total memory limits (default: `16Gi`) |
| Max Pods | | Maximum number of pods in the namespace (default: `20`) |
| Allow Internet Egress | | Allow outbound internet access (default: disabled) |

## What gets created

1. **Vault policy** — `tenant-{name}` scoped to `secret/data/teams/{name}/*`
2. **GitOps files** committed to `mctl-core`:
   - `platform-gitops/tenants/{name}/values.yaml` — quotas, networking, GitHub team
   - `platform-gitops/tenants/{name}/catalog-info.yaml` — Backstage catalog entry
   - `platform-gitops/argocd/values.yaml` — RBAC entry for the team
3. **Kubernetes namespace** `{name}` (provisioned by ArgoCD):
   - `ResourceQuota` — CPU/memory/pod limits
   - `NetworkPolicy` — deny-all + allow intra-namespace + optional internet egress
   - `LimitRange` — default per-container resource limits
4. **ArgoCD RBAC** — `g, mctlhq:{github_team}, role:team-{name}`

## Notes

- The GitHub team must already exist in the `mctlhq` org (or be created separately)
- ArgoCD provisions the namespace within ~2-3 minutes after commit
- Backstage catalog refreshes the tenant Resource entity within ~5 minutes
- Internet egress is disabled by default — enable only if the team's services call external APIs

## Links

- [Argo Workflows UI](https://workflows.mctl.me)
- [ArgoCD Dashboard](https://ops.mctl.me)
