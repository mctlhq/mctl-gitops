# Forking mctl-gitops

Step-by-step guide for external organizations forking this repository to run their own mctl platform instance.

## 1. Quick Start

Fork `mctlhq/mctl-gitops` into your GitHub organization. Then work through sections 2-7 below before pointing ArgoCD at your fork.

**What to change first (in order):**

1. Platform ConfigMap (single source of truth for workflows)
2. Apps templates (ArgoCD Application manifests -- ~60 hardcoded references)
3. Apps values.yaml (repo URL + alert config)
4. ArgoCD repo credentials (two ExternalSecrets)
5. Secrets (Vault paths or manual Secret creation)

## 2. Platform Config (ConfigMap)

Edit `platform-gitops/argo-workflows/mctl-platform-config.yaml`:

```yaml
data:
  GITOPS_ORG: "your-org"
  GITOPS_REPO: "your-gitops-repo"       # or keep "mctl-gitops"
  PLATFORM_DOMAIN: "your-domain.com"
  PLATFORM_DOMAIN_ALT: "your-alt.com"   # leave empty string to disable
  CONTAINER_REGISTRY: "ghcr.io/your-org" # or your-registry.com/your-org
```

All Argo Workflow templates read from this ConfigMap via `envFrom`, so runtime behavior (builds, deployments, tenant creation) is driven from here. The remaining steps cover values baked into static YAML that ArgoCD applies directly.

## 3. Apps Templates

The directory `platform-gitops/apps/templates/` contains ArgoCD Application manifests with ~60 hardcoded references. Run these `sed` commands from the repository root:

```bash
# Replace GitHub org
sed -i '' 's|mctlhq|your-org|g' platform-gitops/apps/templates/*.yaml

# Replace gitops repo name (skip if you kept the name mctl-gitops)
sed -i '' 's|mctl-gitops|your-gitops-repo|g' platform-gitops/apps/templates/*.yaml

# Replace primary domain
sed -i '' 's|mctl\.ai|your-domain.com|g' platform-gitops/apps/templates/*.yaml

# Replace alternate domain
sed -i '' 's|mctl\.me|your-alt.com|g' platform-gitops/apps/templates/*.yaml

# Replace container registry (already covered by org replacement if using ghcr.io)
# Only needed if you use a different registry host:
sed -i '' 's|ghcr\.io/your-org|your-registry.com/your-org|g' platform-gitops/apps/templates/*.yaml
```

On Linux, drop the `''` after `-i` (GNU sed vs BSD sed).

**Verify the result:**

```bash
grep -rn 'mctlhq\|mctl\.ai\|mctl\.me' platform-gitops/apps/templates/
# Should return zero matches.
```

**Files with the most references** (review these carefully):

| File | What it contains |
|---|---|
| `backstage.yaml` | Backstage Helm values with domain, org, image refs |
| `mctl-api.yaml` | API deployment with domain, registry, org refs |
| `argo-workflows.yaml` | Workflow controller config, SSO callback URLs |
| `monitoring.yaml` | Grafana/Prometheus ingress hostnames |
| `vault.yaml` | Vault ingress and HA config |

## 4. Apps values.yaml

Edit `platform-gitops/apps/values.yaml`:

```yaml
spec:
  source:
    repoURL: https://github.com/your-org/your-gitops-repo.git
    targetRevision: main
  destination:
    server: https://kubernetes.default.svc

alertmanager:
  telegramChatId: 0    # your Telegram chat ID, or 0 to disable
```

This file is the root of the App-of-Apps pattern. Every ArgoCD Application inherits `repoURL` and `targetRevision` from here via Helm templating.

## 5. ArgoCD Repo Credentials

Two ExternalSecret files pull a GitHub PAT from Vault and create ArgoCD repository secrets.

**`platform-gitops/apps/templates/argocd-repo-credentials.yaml`** (line 21):

```yaml
        url: https://github.com/your-org/your-gitops-repo.git
```

**`platform-gitops/apps/templates/argocd-repo-creds.yaml`** (line 21):

```yaml
        url: https://github.com/your-org
```

Both reference `vault-backend` ClusterSecretStore at Vault path `platform/argocd/github-repo` (property: `pat`). If your Vault path differs, update the `remoteRef` blocks as well.

## 6. Secrets

The platform expects these Kubernetes secrets (created via ExternalSecrets from Vault, or manually):

| Secret | Namespace | Purpose | Vault Path (default) |
|---|---|---|---|
| `github-app-credentials` | `backstage` | GitHub App key for Backstage catalog discovery | `platform/github-app` |
| `mctl-gitops-deploy-key` | `argo-workflows` | SSH deploy key for workflow git-commit steps | (SSH key, not in Vault) |
| `gitops-token` | `argo-workflows` | GitHub PAT for CI image-tag updates | `platform/argocd/github-repo` |
| `vault-backend` (ClusterSecretStore) | cluster-wide | Vault connection for all ExternalSecrets | n/a (it IS the Vault ref) |
| `argocd-repo-mctl-app` | `argocd` | ArgoCD repo auth (auto-created by ExternalSecret) | `platform/argocd/github-repo` |

**If you are not using Vault**, replace the ExternalSecret resources with plain `kind: Secret` manifests. Search for `ExternalSecret` across the repo:

```bash
grep -rl 'kind: ExternalSecret' platform-gitops/
```

## 7. Annotation Namespaces

The codebase uses custom Kubernetes/Backstage annotations under two prefixes:

- `mctl.me/*` -- e.g., `mctl.me/tenant-name`, `mctl.me/auto-deploy`, `mctl.me/component-type`
- `platform.mctl.me/*` -- e.g., `platform.mctl.me/database`, `platform.mctl.me/database-team`

These are **string keys only** -- they do not resolve to any external service. Kubernetes and Backstage treat them as opaque labels/annotations.

**You can keep them as-is.** They will work fine regardless of your domain. However, if you want to rebrand them:

```bash
# From the repo root:
find platform-gitops/ -name '*.yaml' -o -name '*.tpl' | \
  xargs sed -i '' 's|platform\.mctl\.me/|platform.your-domain.com/|g'

find platform-gitops/ -name '*.yaml' -o -name '*.tpl' | \
  xargs sed -i '' 's|mctl\.me/|your-domain.com/|g'
```

Be careful not to run the domain-replacement `sed` from section 3 *after* this step, or you will double-replace. Do annotation renaming last, or skip it entirely.

## 8. Verification

After completing all edits:

**Step 1 -- Check for leftover references:**

```bash
grep -rn 'mctlhq\|mctl\.ai' platform-gitops/apps/ platform-gitops/argo-workflows/mctl-platform-config.yaml
# Should return zero matches (mctl.me may remain if you kept annotations).
```

**Step 2 -- Apply the ConfigMap:**

```bash
kubectl apply -f platform-gitops/argo-workflows/mctl-platform-config.yaml
kubectl get configmap mctl-platform-config -n argo-workflows -o yaml
# Verify all values match your org/domain.
```

**Step 3 -- Apply workflow templates:**

```bash
kubectl apply -f platform-gitops/argo-workflows/workflow-templates/
# All templates should create/update without errors.
```

**Step 4 -- Bootstrap ArgoCD App-of-Apps:**

```bash
# Point ArgoCD at your fork (if not already configured):
argocd repo add https://github.com/your-org/your-gitops-repo.git --username argocd --password <PAT>

# Create the root Application:
argocd app create apps \
  --repo https://github.com/your-org/your-gitops-repo.git \
  --path platform-gitops/apps \
  --dest-server https://kubernetes.default.svc \
  --dest-namespace argocd

argocd app sync apps
```

**Step 5 -- Verify in ArgoCD UI:**

- All child Applications should appear and begin syncing.
- Check for `ComparisonError` or `SyncError` -- these usually indicate a missed reference or missing secret.
- Run `argocd app list` and confirm no apps are stuck in `Unknown` or `Missing` health.

---

For questions or issues with the fork process, open an issue on the upstream repository.
