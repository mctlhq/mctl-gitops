# Tenant Cleanup Patterns

## Safe Model

- ordinary service deletion:
  - run `retire-service` in the tenant namespace so the tenant can see the workflow
- tenant deletion:
  - run `delete-tenant-safe` from `argo-workflows`
  - retire all tenant services
  - wait for completion
  - sweep shared resources
  - remove tenant GitOps and namespace

## Shared Resource Sweep

The tenant cleanup must also inspect:

- `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`
- `platform-gitops/infra-components/data/cnpg/shared/databases.yaml`
- `platform-gitops/infra-components/data/cnpg/shared/secrets.yaml`

Look for names like `${tenant}-*`.

Typical leftovers:

- `database/<tenant>-<service>-db` in `platform-db`
- `externalsecret/<tenant>-<service>-db-creds` in `platform-db`

## Validation

After cleanup, check:

- `kubectl -n argocd get app shared-pg`
- `kubectl -n argocd get app root-app`
- `kubectl -n platform-db get database,externalsecret`
- `kubectl -n argocd get app <tenant>-<service>` returns not found
- `kubectl -n argocd get app tenant-<tenant>` returns not found
- `kubectl get ns <tenant>` returns not found
- `GET /api/v1/tenants/<tenant>` returns `404`
- treat only explicit `NotFound` from `kubectl get` as success; generic command failures are not valid cleanup proof

## ArgoCD ApplicationSet Timing

Two fixes in this repo materially reduced tenant create/delete lag:

- `apps` ApplicationSet git generator now uses `requeueAfterSeconds: 30`
- `tenants` ApplicationSet git generator now uses `requeueAfterSeconds: 30`
- `delete-tenant-safe` now eager-prunes service app CRs and tenant app CRs before waiting on namespace disappearance

Without that, deploy and cleanup flows can wait behind the controller's default multi-minute poll interval even after Git is already correct.

Observed live cleanup timings after these fixes:

- service app CR gone: about `0.8s`
- tenant app CR gone: about `19.9s`
- namespace gone: about `20.2s`

## Related Argo Workflow Hygiene

If old failed workflows or orphan pods confuse the incident:

1. list old workflows in `argo-workflows`
2. delete only stale failed/error workflows
3. delete orphan pods with no useful owner
4. keep current or recent successful workflows unless they are clearly noise
