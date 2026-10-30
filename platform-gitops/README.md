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

### Unregister vs retire

**"Unregister Entity" in Backstage** only removes the catalog entry. The
GitOps files stay and the service keeps running.

**Retiring** removes the service everywhere. Use the platform, not a manual
directory delete:

- `mctl_retire_service` (MCP) or the **"Retire Service"** template in
  Backstage. Both submit the `retire-service` workflow in the tenant
  namespace.

The workflow (`wft-retire-service.yaml`):

1. `preflight` checks that the ArgoCD Application belongs to the service.
2. In parallel:
   - `delete-vault-secrets` deletes everything under
     `secret/teams/{team}/{service}`, nested paths included, and fails
     unless the path is gone afterwards (skipped only with
     `delete_vault_secrets=false`);
   - `delete-from-git` removes `services/{team}/{service}/` from `main`,
     then `cleanup-db-resources` removes the service's database resources,
     if any.
3. `delete-argocd-app` deletes the Application and waits for it, and its
   Kubernetes resources, to be gone.

Deleting `services/{team}/{service}/` by hand removes the Application and
its resources, but nothing cleans Vault or the database: those are left
behind. There is no ArgoCD hook that does it.
