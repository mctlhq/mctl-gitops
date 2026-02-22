# 🧹 Retire Service

Permanently removes a service from the platform.

## When to use

Use this template when a service is being decommissioned and you want to:
- Remove it from ArgoCD and the cluster
- Delete its GitOps files
- Clean up Vault secrets
- Remove it from the Backstage catalog

> ⚠️ **This action is irreversible.** All Kubernetes resources, Vault secrets, and GitOps files will be deleted.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | ✅ | Select the service to retire from the catalog |
| Confirm | ✅ | Type `RETIRE` to confirm the action |

## What gets deleted

1. GitOps files: `platform-gitops/services/preview/{team}/{service}/` (or `workers/`)
2. ArgoCD Application — all Kubernetes resources are removed from the cluster
3. Vault secrets at `teams/{team}/{service}/`
4. Catalog entry — Backstage removes the component on next sync

## Notes

- The Docker image in GHCR is **not** deleted (images are immutable artifacts)
- Database resources (if any) are **not** deleted by this template — use the database deprovisioning process separately

## Links

- [GitHub Actions workflow](https://github.com/mctlhq/mctl-core/actions/workflows/retire-service.yml)
