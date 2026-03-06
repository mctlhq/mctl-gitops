# Create Tenant

Provision a new team workspace on the mctl.ai platform — creates a Kubernetes namespace with resource quotas, a Vault policy scoped to the team, and ArgoCD RBAC.

## When to use

- Onboarding a **new team** to the platform
- Creating an isolated namespace with quota and network policies for an existing team

## Inputs

### Tenant Identity

| Field | Required | Description |
|---|---|---|
| Tenant Name | Yes | Lowercase DNS-safe slug (e.g. `my-team`). Used as the Kubernetes namespace name. |
| Display Name | Yes | Human-readable name shown in Backstage and dashboards |
| Description | | Brief description of the team and what they build |
| Contact Email | | Team email for platform notifications |

### Resource Quotas

| Field | Default | Description |
|---|---|---|
| CPU Requests | `1` | Total CPU requests across all pods in the namespace |
| CPU Limits | `2` | Total CPU limits across all pods |
| Memory Requests | `1Gi` | Total memory requests |
| Memory Limits | `2Gi` | Total memory limits |
| Max Pods | `10` | Maximum number of pods in the namespace |

### Networking

| Field | Default | Description |
|---|---|---|
| Allow Internet Egress | enabled | Allow pods to make outbound requests to the internet. Enabled by default — workflow pods need to reach GitHub, services may call external APIs. |

## What gets created

1. **Vault policy** — `tenant-{name}` scoped to `secret/data/teams/{name}/*`
2. **GitOps files** committed to `mctl-core`:
   - `platform-gitops/tenants/{name}/values.yaml` — quotas, networking config
   - `platform-gitops/tenants/{name}/catalog-info.yaml` — Backstage catalog entry
3. **Kubernetes resources** provisioned by ArgoCD (~2-3 min):
   - `Namespace` — isolated workspace for the team
   - `ResourceQuota` — CPU/memory/pod limits
   - `NetworkPolicy` — deny-all ingress + allow intra-namespace + optional internet egress
   - `LimitRange` — default per-container resource limits
4. **ArgoCD RBAC** — team members get access to their namespace's ArgoCD applications automatically via OIDC groups

## Notes

- Backstage catalog refreshes the tenant entity within ~5 minutes after ArgoCD sync
- Quotas apply to the sum of all pods in the namespace — individual pod limits are set via LimitRange
- Internet egress is enabled by default; disable it for isolated or sensitive workloads

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [ArgoCD Dashboard](https://ops.mctl.ai)
- [Backstage Catalog](https://app.mctl.ai/catalog)
