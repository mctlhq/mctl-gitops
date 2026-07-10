# ArgoCD Remediation Checklist

## Fast Triage

1. `kubectl -n argocd get app <app> -o yaml`
2. Inspect:
   - `.status.health.status`
   - `.status.sync.status`
   - `.status.conditions`
   - `.status.operationState`
   - `.status.resources`
3. Open the failing object directly with `kubectl get` and `kubectl describe`.

## Patterns Seen In `mctlhq`

### `minio` degraded with `ProgressDeadlineExceeded`

- Symptom:
  - app `Synced Degraded`
  - deployment stuck with `replicas: 2`, `ready: 1`, `updated: 1`
  - old pod holds the only RWO PVC
- Durable fix:
  - set `deploymentUpdate.type: Recreate` in `platform-gitops/bootstrap/templates/data/minio.yaml`

### `tenant-*` sync failure on `ExternalSecret`

- Symptom:
  - sync error mentions `metadata.managedFields must be nil`
  - one `ExternalSecret` remains `OutOfSync`
- Durable/live fix:
  - confirm rendered desired manifest is correct
  - delete the broken `ExternalSecret`
  - delete its generated `Secret` if needed
  - let Argo self-heal recreate it

### `tenant-*` warning about orphaned resources

- Symptom:
  - app is `Synced Healthy`
  - condition says `Application has N orphaned resources`
  - namespace contains service workloads not managed by tenant chart
- Durable fix:
  - disable orphan warnings for `project: platform`
  - do not delete live service workloads to silence the warning

### `shared-pg` fallout after tenant deletion

- Symptom:
  - `shared-pg` degraded or out of sync after tenant removal
  - stale `Database` or `ExternalSecret` objects remain in `platform-db`
- Fix:
  - clean GitOps manifests under `infra-components/data/cnpg/shared`
  - delete only stale live DB artifacts

## Verification Commands

- `kubectl -n argocd get app <app> -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'`
- `kubectl -n argocd get app root-app -o jsonpath='{.status.sync.status} {.status.health.status}{"\n"}'`
