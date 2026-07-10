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
| `ovk`, `labs`, `admins` | tenant | `<team>-openclaw-base-service` Deployment + per-tenant `<team>-openclaw-skills` ConfigMap. Tenant workloads live here. |
| `mctl-api` | platform | `mctl-api` Deployment and Service. ArgoCD Application is `admins-mctl-api`, but the pod runs here. |
| `backstage` | platform | Backstage / mctl-portal Deployment and Service. ArgoCD Application is `admins-mctl-portal`. |
| `argocd` | platform | ArgoCD Applications (`<team>-openclaw`, `<team>-openclaw-skills`, `loki-stack`, `minio`, …) |
| `argo-workflows` | platform | ClusterWorkflowTemplates for centralized write operations (`openclaw-skill-save`, `-identity-save`, build/deploy templates). Deploy-key secret `mctl-gitops-deploy-key` lives here. |
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

## OpenClaw tenant pod anatomy

Every `<team>-openclaw-base-service` pod is built from the shared `base-service` Helm chart plus a per-tenant overlay:

- Main container `base-service`: OpenClaw Node process. Image `ghcr.io/mctlhq/mctl-openclaw:<tag>`. Tag + `OPENCLAW_VERSION` env in `platform-gitops/services/<team>/openclaw/values.yaml` (both must stay in sync on every bump).
- Sidecar `s3-sync`: `minio/mc` image, runs `mc mirror --remove --overwrite /home/node/.openclaw → s3/platform-state/<team>/openclaw/` on a 10-second loop. Has a `lifecycle.preStop` hook that runs one final synchronous mirror before SIGTERM.
- Init `restore-state`: pulls `s3/platform-state/<team>/openclaw/` into the `state-data` emptyDir at pod start. First-line recovery on Recreate.
- Other inits (`setup`, `seed-workspace-skills`, `install-whisper-cli`) prep the filesystem.

### Pod filesystem paths worth remembering

| Path in pod | Backed by | Purpose |
|---|---|---|
| `/home/node/.openclaw` | emptyDir `state-data` | Agent runtime state. **Durable via s3-sync sidecar, not via PVC.** |
| `/home/node/.openclaw/agents/main/agent/auth-profiles.json` | emptyDir | OAuth tokens (Codex + provider auth). Atomic writes enabled in image ≥ `2026.4.23-beta.1`. |
| `/home/node/.openclaw/workspace/skills/<name>/SKILL.md` | fan-out from `<team>-openclaw-skills` ConfigMap | Layer-3 per-tenant skills. Source of truth: `platform-gitops/services/<team>/openclaw/skills/*.md`. |
| `/app/mctl-skills/mctl-platform/SKILL.md` | image overlay (from mctl-openclaw repo) | Layer-2 platform skills shipped in image. |
| `/app/mctl-identity/` | image overlay | Layer-2 identity defaults (AGENTS, SOUL, IDENTITY, USER, TOOLS + CLAUDE.md symlink). |

## GitOps source of truth

Repo: `https://github.com/mctlhq/mctl-gitops` (use your local checkout of it in the mctlhq workspace).

Key files:

- `platform-gitops/services/<team>/openclaw/values.yaml` — per-tenant chart values.
- `platform-gitops/services/<team>/openclaw/skills/*.md` — Layer-3 skills (auto-rendered into the skills ConfigMap via the regenerator workflow).
- `platform-gitops/services/<team>/openclaw/generated/skills-values.yaml` — **do NOT hand-edit**; regenerated by `openclaw-skill-save` / `openclaw-identity-save` workflows.
- `platform-gitops/helm-charts/base-service/` — chart every tenant service shares.
- `platform-gitops/bootstrap/templates/observability/loki.yaml` — Loki Application.
- `platform-gitops/bootstrap/templates/data/minio.yaml` — MinIO Application.

**Never `kubectl edit` an ArgoCD-managed resource.** ArgoCD reverts within seconds. Edit gitops, commit, PR, merge.

## Routine operator commands

### Inspect a tenant pod end-to-end

```sh
kubectl -n ovk get pod -l app.kubernetes.io/instance=ovk-openclaw -o wide
kubectl -n ovk describe pod -l app.kubernetes.io/instance=ovk-openclaw
kubectl -n ovk logs deploy/ovk-openclaw-base-service -c base-service --tail=200
kubectl -n ovk logs deploy/ovk-openclaw-base-service -c s3-sync --tail=50
kubectl -n ovk logs deploy/ovk-openclaw-base-service -c restore-state   # init logs
```

### Force a safe state flush to S3 before a rollout

```sh
for team in ovk labs admins; do
  pod=$(kubectl -n "$team" get pod -l app.kubernetes.io/instance="$team-openclaw" -o name | head -1)
  kubectl -n "$team" exec "$pod" -c s3-sync -- \
    mc mirror --overwrite --exclude '*.lock' --exclude '*.tmp' \
    /home/node/.openclaw "s3/platform-state/$team/openclaw/"
done
```

**Omit `--remove` deliberately.** The sidecar's looping mirror uses `--remove`, but the manual pre-rollout flush must not — a transient local pruning (init race, partial startup) would propagate to S3 and delete live state.

### Trigger ArgoCD sync without waiting for the 3-minute poll

```sh
for app in ovk-openclaw labs-openclaw admins-openclaw; do
  kubectl -n argocd patch application "$app" \
    --type merge \
    -p '{"metadata":{"annotations":{"argocd.argoproj.io/refresh":"hard"}}}'
done
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

## Image bump recipe (mctl-openclaw)

1. Tag on `mctl-openclaw`: `git tag -a v<YYYY.M.D-beta.N> -m "…"; git push origin v<YYYY.M.D-beta.N>`. Docker Release workflow fires on `v*` and publishes `ghcr.io/mctlhq/mctl-openclaw:<version>` (amd64 + arm64 + manifest). The image path uses `mctl-openclaw`, **not** `openclaw` — a historical gotcha after the docker-release workflow moved to `IMAGE_NAME: ${{ github.repository }}`.
2. **Wait for the GitHub Actions run to complete (~15 min)** before bumping gitops. Otherwise every tenant ImagePullBackOffs for the image pull timeout window, which in combination with `--remove` mirror loops risks wiping state on S3 (documented below).
3. Manually flush tenant state to S3 (command above) as a safety belt.
4. PR on `mctl-gitops` bumping `image.tag` **and** `env.OPENCLAW_VERSION` in every tenant's `values.yaml` to the new version.
5. Merge. ArgoCD applies within 3 min (or trigger a hard refresh).

## Auth persistence + safe rollout recipe (post-2026-04-26 hardening)

State on each openclaw tenant lives in `emptyDir` mirrored to S3 by the `s3-sync` sidecar. Two guards now protect against wipe; they do not eliminate the need for the recipe below, they just buy you time when something goes wrong.

### Pre-flush before any rollout that re-runs init containers

```sh
flush_failed=""
for team in ovk labs admins; do
  pod=$(kubectl -n "$team" get pod -l app.kubernetes.io/instance="$team-openclaw" -o name | head -1)
  if [ -z "$pod" ]; then
    echo "FLUSH FAILED: no openclaw pod found in $team"
    flush_failed="$flush_failed $team"
    continue
  fi
  kubectl -n "$team" exec "$pod" -c s3-sync -- \
    mc mirror --overwrite --exclude '*.lock' --exclude '*.tmp' \
    /home/node/.openclaw "s3/platform-state/$team/openclaw/" \
    || { echo "FLUSH FAILED: $team"; flush_failed="$flush_failed $team"; }
done
[ -z "$flush_failed" ] || echo "DO NOT ROLL OUT:$flush_failed — state not flushed"
```

Do NOT proceed with the rollout for any team whose flush failed — the rollout
re-runs init containers and an unflushed pod loses everything since the last
sidecar mirror. `--overwrite` without `--remove` so a wonky source can't wipe S3.

### Verify the canary guard is live before trusting it

```sh
kubectl -n <team> get pod -l app.kubernetes.io/instance=<team>-openclaw \
  -o jsonpath='{.items[0].spec.containers[?(@.name=="s3-sync")].args[0]}' \
  | grep -c AGENT_DIR
# expect 2 (main loop + preStop)
```

### Verify the restore-state probe is the new shape

```sh
kubectl -n <team> get pod -l app.kubernetes.io/instance=<team>-openclaw \
  -o jsonpath='{.items[0].spec.initContainers[?(@.name=="restore-state")].args[0]}' \
  | grep -c 'mc ls --recursive'
# expect 2 (NEW prefix + LEGACY prefix probes)
```

If the count is wrong on any tenant, the canary / probe is missing — patch the values.yaml before triggering a rollout.

### Symptoms of a wipe-class incident

- `restore-state` log shows `Added 's3' successfully.` and nothing else → the marker probe didn't find anything. Verify with `mc ls -r s3/platform-state/<team>/openclaw/` from inside the s3-sync container; if S3 has files, the probe is broken (likely missing `grep` or wrong marker key) — open a fix PR, don't hand-restore.
- Pod has `agents/main/agent/` empty but S3 has full state → restore-state ran but didn't mirror down. Same diagnosis as above.
- Pod has auth, S3 has no auth-profiles.json → emptyDir nuked S3 at preStop. Verify canary guard is deployed; if it is, the wipe predates the guard's deployment and recovery requires UI re-auth.

### Recovery flow (auth-profiles.json missing locally)

1. Check S3 first: `kubectl -n <team> exec deploy/<team>-openclaw-base-service -c s3-sync -- mc ls s3/platform-state/<team>/openclaw/agents/main/agent/`
2. If S3 has it: any spec-changing reconcile will trigger a Recreate, the new restore-state probe will pull it back automatically. No UI action needed.
3. If S3 doesn't have it: only path is UI re-auth at `https://<team>-openclaw.mctl.ai`. Tokens cannot be regenerated server-side.

## Anti-patterns and historical outages

- **`mc mirror --remove` with an empty/partial local dir wipes S3.** The sidecar depends on the `restore-state` init populating emptyDir before the loop starts. If the main container enters ImagePullBackOff and the pod later gets recreated while the init had a transient failure, the sidecar can mirror an empty tree to S3 and vaporise tenant auth-profiles + session history. **Mitigation now in place**: source-side canary guard on `agents/main/agent/` skips `--remove` when local is empty (mctl-gitops PR #36). Still pre-flush before risky rollouts as belt-and-braces.
- **`mc find ... --name <runtime-artifact>.json` as the restore-state marker**: artifact may not exist for tenants that never wrote it (early-life or wiped). restore-state silently `mkdir -p`s an empty dir even though S3 is full. **Fix**: probe with `[ -n "$(mc ls --recursive ... | head -1)" ]` (mctl-gitops PR #37 + #38). Do **not** pipe through `grep -q .` — `minio/mc` image has no `grep`, the test silently fails.
- **Squash-rebase across multiple openclaw values.yaml changes**: easy to drop a sidecar block during conflict resolution (mctl-gitops PR #35 had to restore `skills-fanout` on ovk + labs after a previous squash dropped it). After any rebase touching openclaw values, `grep -c skills-fanout platform-gitops/services/{ovk,labs,admins}/openclaw/values.yaml` per tenant.
- **Helm-managed PVC resize inside a StatefulSet**: `volumeClaimTemplates.storage` is immutable. ArgoCD will render the new value but k8s refuses to patch. The human has to `kubectl patch pvc` once; ArgoCD then stays in sync.
- **Loki with `store: tsdb` and `persistence.enabled: false` on 2.6.1**: compactor startup banner reports `"Not using boltdb-shipper index, not starting compactor"` and retention never runs — MinIO fills up silently. Fix is Loki ≥ 2.8 (tsdb compactor) + keep the working_directory on a real volume if marker durability across pod restarts matters. On Hetzner the 10 GiB PVC floor usually makes it cheaper to accept the occasional stray chunk and rely on a bigger MinIO bucket.
- **`kubectl edit` on an ArgoCD-managed resource**: reverts within seconds. Work through gitops or `kubectl apply` **with** `argocd app sync` disabled first (rarely worth it).
- **Tag name drift**: tenant `values.yaml` must reference the full image path `ghcr.io/mctlhq/mctl-openclaw` (not the shorter `ghcr.io/mctlhq/openclaw` that older docker-release versions used). If a rollout shows `ErrImagePull: … openclaw:<tag> not found`, this is the likely cause.
