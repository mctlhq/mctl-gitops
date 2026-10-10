# Direct Kubernetes Operations (fallback when MCP tools don't cover it)

Prefer `mctl_*` MCP tools for anything they cover — these commands are the escape hatch for inspecting pod-local state, forcing flushes, reading logs across sidecars, or reacting to cluster-level incidents.

## Cluster identity

- Name: `mctl-preprod`
- Runtime: **k3s** on Hetzner Cloud, provisioned via `kube-hetzner` Terraform module.
- API server: `https://78.47.58.237:6443`
- Kubeconfig: `infrastructure/k3s-preview/kubeconfig.yaml` in your local mctl-gitops checkout
  - `infrastructure/k3s-preview/` is the real live cluster despite the name. `infrastructure/k3s-prod/` exists as an empty/planned spare.

Every kubectl session starts with (from the mctl-gitops checkout root):

```sh
export KUBECONFIG="$(pwd)/infrastructure/k3s-preview/kubeconfig.yaml"
```

## Namespace map

| Namespace | Owner | Contents |
|---|---|---|
| `<team>` (e.g. `labs`, `admins`, `ovk`) | tenant | `<team>-<service>-base-service` Deployments. Tenant workloads live here. |
| `mctl-api` | platform | `mctl-api` Deployment and Service. ArgoCD Application is `admins-mctl-api`, but the pod runs here. |
| `backstage` | platform | Backstage / mctl-portal Deployment and Service. ArgoCD Application is `admins-mctl-portal`. |
| `argocd` | platform | ArgoCD Applications (`<team>-<service>`, `tenant-<team>`, `loki-stack`, `minio`, …) |
| `argo-workflows` | platform | ClusterWorkflowTemplates for centralized write operations (build/deploy/rollback templates). Deploy-key secret `mctl-gitops-deploy-key` lives here. |
| `minio` | platform | `minio` StatefulSet + 10 GiB hcloud-volumes PVC mounted at `/export`. Buckets include `platform-state` (tenant mirror), `loki` (log chunks), `argo-workflows-logs`, `platform-cache`, `postgres-backups`. |
| `monitoring` | platform | `loki-stack` StatefulSet (Loki ≥ 2.9 with tsdb + compactor retention), Prometheus, Grafana. |
| `cnpg-system` | platform | CloudNativePG operator. |
| `platform-db` | platform | Shared PostgreSQL cluster (`shared-pg`), including Backstage database `backstage`. |
| `vault` | platform | HashiCorp Vault. External Secrets Operator's `ClusterSecretStore` is named `vault-backend`; KV v2 mount is `secret`. |

## Tenant onboarding identity checks

Tenant creation has separate desired-state and identity read models:

- GitOps/Kubernetes: `platform-gitops/tenants/<tenant>/`, ArgoCD `tenant-<tenant>`, namespace `<tenant>`.
- Portal/OIDC: Backstage database `backstage`, schema `tenant-management`, table `tenant_members`.
- `mctl-api`: local GitOps reader cache in the `mctl-api` pod.

Useful read-only checks:

```sh
kubectl get app tenant-<tenant> -n argocd
kubectl get ns <tenant>
kubectl exec -n platform-db shared-pg-1 -- \
  psql -U postgres -d backstage -c \
  "select tenant_name, user_id, role from \"tenant-management\".tenant_members where tenant_name='<tenant>';"
kubectl logs -n mctl-api deploy/mctl-api --since=2h | grep -i 'gitops'
```

## GitOps source of truth

Repo: `https://github.com/mctlhq/mctl-gitops` (use your local checkout of it in the mctlhq workspace).

Key files:

- `platform-gitops/services/<team>/<service>/values.yaml` — per-service chart values.
- `platform-gitops/helm-charts/base-service/` — chart every tenant service shares.
- `platform-gitops/bootstrap/templates/observability/loki.yaml` — Loki Application.
- `platform-gitops/bootstrap/templates/data/minio.yaml` — MinIO Application.

**Never `kubectl edit` an ArgoCD-managed resource.** ArgoCD reverts within seconds. Edit gitops, commit, PR, merge.

## Routine operator commands

### Inspect a tenant pod end-to-end

```sh
kubectl -n <team> get pod -l app.kubernetes.io/instance=<team>-<service> -o wide
kubectl -n <team> describe pod -l app.kubernetes.io/instance=<team>-<service>
kubectl -n <team> logs deploy/<team>-<service>-base-service -c base-service --tail=200
# sidecars and init containers: add -c <container-name>
```

### Trigger ArgoCD sync without waiting for the 3-minute poll

```sh
kubectl -n argocd patch application <team>-<service> \
  --type merge \
  -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
```

### Resize a `hcloud-volumes` PVC online

```sh
kubectl patch pvc minio -n minio --type=merge \
  -p '{"spec":{"resources":{"requests":{"storage":"30Gi"}}}}'
```

`allowVolumeExpansion: true` on the StorageClass. **Minimum Hetzner Cloud Volume size is 10 GiB**; any smaller request is silently rounded up and you pay for 10 GiB. Shrinking is not supported.

For StatefulSets, `volumeClaimTemplates.storage` is immutable — a chart bump will render the new value but k8s refuses to mutate the STS. Patch the underlying PVC by hand once; ArgoCD then becomes a no-op.

### MinIO disk triage

When MinIO returns `XMinioStorageFull` (status 507), scale Loki down, clear `/export/loki/{fake,index}` on the MinIO pod, scale Loki back up. The Loki compactor then keeps things clean going forward.

```sh
kubectl -n monitoring scale sts loki-stack --replicas=0
kubectl -n monitoring wait --for=delete pod/loki-stack-0 --timeout=120s
kubectl -n minio exec <minio-pod> -- sh -c 'rm -rf /export/loki/fake /export/loki/index'
kubectl -n monitoring scale sts loki-stack --replicas=1
```

## Anti-patterns and historical outages

- **`mc mirror --remove` with an empty/partial local dir wipes S3.** A state-mirror sidecar (`s3-sync`) depends on its restore init populating the emptyDir before the loop starts. If the pod is recreated while the init had a transient failure, the sidecar can mirror an empty tree to S3 and delete the persisted state. Guard `--remove` with a source-side canary (skip it when the local dir is empty), and never pass `--remove` to a manual pre-rollout flush.
- **A specific runtime file as the restore marker**: the file may not exist yet (early-life or wiped state), so the restore init silently creates an empty dir even though S3 is full. Probe with `[ -n "$(mc ls --recursive ... | head -1)" ]` (mctl-gitops PR #37 + #38). Do **not** pipe through `grep -q .` — the `minio/mc` image has no `grep`, so the test silently fails.
- **Helm-managed PVC resize inside a StatefulSet**: `volumeClaimTemplates.storage` is immutable. ArgoCD will render the new value but k8s refuses to patch. The human has to `kubectl patch pvc` once; ArgoCD then stays in sync.
- **Loki with `store: tsdb` and `persistence.enabled: false` on 2.6.1**: compactor startup banner reports `"Not using boltdb-shipper index, not starting compactor"` and retention never runs — MinIO fills up silently. Fix is Loki ≥ 2.8 (tsdb compactor) + keep the working_directory on a real volume if marker durability across pod restarts matters. On Hetzner the 10 GiB PVC floor usually makes it cheaper to accept the occasional stray chunk and rely on a bigger MinIO bucket.
- **`kubectl edit` on an ArgoCD-managed resource**: reverts within seconds. Work through gitops or `kubectl apply` **with** `argocd app sync` disabled first (rarely worth it).
