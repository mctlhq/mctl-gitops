# GitOps Platform & Services

Source of truth for the mctl.ai Kubernetes platform.

## Directory Structure

*   📁 **`bootstrap/`**: ArgoCD ApplicationSets that provision the platform.
*   📁 **`argo-workflows/`**: Automation logic (ClusterWorkflowTemplates).
*   📁 **`backstage/`**: Developer portal configuration and templates.
*   📁 **`infra-components/`**: Foundational services (Databases, Monitoring, Dashboards).
*   📁 **`services/`**: User-facing microservices (organized by team).
*   📁 **`tenants/`**: Team workspace configurations (quotas, RBAC).

## Service Deletion

### ⚠️ Unregister vs Delete

**"Unregister Entity" in Backstage:**
- Only removes from Backstage catalog (soft delete)
- GitOps files remain
- Service continues running in Kubernetes

**Full Deletion (deprovision):**
- Delete service folder from Git
- Automatic cleanup triggers:
  - ✅ Vault secrets deleted (PreDelete hook)
  - ✅ ArgoCD Application removed
  - ✅ Kubernetes resources deleted
  - ✅ Backstage entity removed (after 5min)

### How to Delete Service

#### Option 1: GitHub UI (Easiest)

1. Navigate to service folder:
   - **Services:** [`platform-gitops/services/{team}/{service}/`](https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/services)

2. Click **"..."** → **"Delete directory"**

3. Commit message: `delete: {team}/{service}`

4. Commit directly to main → Automated cleanup starts

#### Option 2: Git CLI

```bash
# Delete service directory
git rm -r platform-gitops/services/{team}/{service}

# Commit
git commit -m "delete: {team}/{service}"

# Push
git push origin main
```

#### Option 3: Delete Workflow

Use the **"Retire Service"** template in Backstage or trigger manually via GitHub Actions.

### What Happens Automatically

```
1. Git: Files deleted from main branch
   ↓
2. ArgoCD: Detects deletion (within 60s)
   ↓
3. PreDelete Hook: vault-cleanup Job runs
   ↓
4. Vault: Secrets deleted from teams/{team}/{service}
   ↓
5. ArgoCD: Deletes Application
   ↓
6. Kubernetes: All resources removed
   ↓
7. Backstage: Entity removed (after refresh)
```
