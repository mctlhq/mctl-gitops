# GitOps Services

Kubernetes service manifests managed by ArgoCD.

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
   - **Services:** [`platform-gitops/services/preview/{team}/{service}/`](https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/services/preview)
   - **Workers:** [`platform-gitops/workers/preview/{team}/{service}/`](https://github.com/mctlhq/mctl-gitops/tree/main/platform-gitops/workers/preview)

2. Click **"..."** → **"Delete directory"**

3. Commit message: `delete: {team}/{service}`

4. Commit directly to main → Automated cleanup starts

#### Option 2: Git CLI

```bash
# Delete service directory
git rm -r platform-gitops/workers/preview/{team}/{service}

# Commit
git commit -m "delete: {team}/{service}"

# Push
git push origin main
```

#### Option 3: Delete Workflow

```bash
# Manual trigger via GitHub Actions
gh workflow run delete-service.yml \
  -f team_name={team} \
  -f service_name={service}
```

### What Happens Automatically

```
1. Git: Files deleted from main branch
   ↓
2. ArgoCD: Detects deletion (within 3 min)
   ↓
3. PreDelete Hook: vault-cleanup Job runs
   ↓
4. Vault: Secrets deleted from teams/{team}/{service}
   ↓
5. ArgoCD: Deletes Application
   ↓
6. Kubernetes: All resources removed
   ↓
7. Backstage: Entity removed (after 5 min refresh)
```

### Undo Deletion

```bash
# Restore from Git history
git revert <commit-hash>
git push origin main
```

### Troubleshooting

**Service still in Backstage after deletion?**
- Wait 5 minutes for catalog refresh
- Or manually unregister entity

**Vault secrets not deleted?**
```bash
# Check PreDelete hook logs
kubectl logs -n {team} job/vault-cleanup-{service}
```

**Need to verify Vault cleanup?**
```bash
# Check if secrets still exist
vault kv list secret/teams/{team}/
```
