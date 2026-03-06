# Retire Service

Permanently removes a service from the platform.

## When to use

Use this template when a service is being decommissioned:
- Remove it from ArgoCD and the cluster
- Delete its GitOps files from `mctl-core`
- Clean up Vault secrets
- Remove it from the Backstage catalog

**This action is irreversible.** All Kubernetes resources, Vault secrets, and GitOps files will be permanently deleted.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | Yes | Select the service to retire from the catalog |
| Confirm | Yes | Type `RETIRE` to confirm the action |

## What gets deleted

1. **GitOps files** — `platform-gitops/services/{team}/{service}/` removed from `mctl-core`
2. **ArgoCD Application** — all Kubernetes resources (Deployment, Service, Ingress, etc.) deleted from the cluster
3. **Vault secrets** — `teams/{team}/{service}/` removed
4. **Catalog entry** — Backstage removes the component on next catalog sync

## Notes

- The Docker image in GHCR is **not** deleted — images are immutable artifacts
- Databases provisioned via the **Provision Database** template are **not** deleted automatically — remove them separately if no longer needed
- The team's namespace and other services are unaffected

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [ArgoCD Dashboard](https://ops.mctl.ai)
