# mctl-core

GitOps repository for the mctl.ai platform. ArgoCD watches this repo and syncs all platform components to the Kubernetes cluster.

## What's here

```
platform-gitops/
├── apps/
│   └── templates/          # ArgoCD Applications (one per service/component)
│       ├── mctl-api.yaml   # REST API + MCP server
│       ├── mctl-web.yaml   # Landing + MCP connect page
│       └── ...
├── tenants/                # Team workspaces (namespace + RBAC + quotas)
│   └── {team}/values.yaml
├── services/               # Per-team service deployments
│   └── {team}/{app}/values.yaml
├── helm-charts/            # Shared Helm charts
│   ├── base-service/       # HTTP services with ingress
│   ├── worker-service/     # Background workers (no ingress)
│   └── tenant/             # Team workspace provisioning
├── argo-workflows/
│   └── workflow-templates/ # ClusterWorkflowTemplates (deploy, create-tenant, provision-db)
└── argocd/
    └── values.yaml         # ArgoCD self-managed config (RBAC, Dex, SSO)
```

## How changes reach the cluster

```
git push → ArgoCD detects diff → syncs to K8s cluster
```

All components have `automated: {prune: true, selfHeal: true}`.

## Releasing a service

Image version is pinned in `values.yaml` per service. CI in each service repo updates the tag automatically on release:

```bash
# In mctl-api repo:
git tag 0.2.0 && git push origin 0.2.0
# → CI builds ghcr.io/mctlhq/mctl-api:0.2.0
# → CI commits: platform-gitops/apps/templates/mctl-api.yaml tag: "0.2.0"
# → ArgoCD syncs → cluster updated
```

## Provisioning a new team

Create `platform-gitops/tenants/{team}/values.yaml` — ApplicationSet picks it up, ArgoCD provisions namespace + RBAC + quotas.

Or use the platform:
```
"Create a workspace for the payments team"
→ mctl_create_tenant(tenant_name="payments") via Claude/mctl-api
```

## Key URLs

| URL | What |
|---|---|
| `ops.mctl.me` | ArgoCD UI |
| `ops.mctl.me/api/dex` | Dex OIDC issuer |
| `workflows.mctl.me` | Argo Workflows UI |
| `api.mctl.ai` | mctl REST API + MCP server |
| `app.mctl.me` | Backstage service catalog |
| `mctl.me` | Landing page |
