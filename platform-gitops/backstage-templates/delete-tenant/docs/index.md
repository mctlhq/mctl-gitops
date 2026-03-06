# Delete Tenant

Permanently deletes a tenant and all associated platform resources.

## When to use

Use this template when a team is being disbanded or removed from the platform and you want to:
- Remove the Kubernetes namespace and all workloads inside it
- Delete the Vault policy and all team secrets
- Remove ArgoCD RBAC entries
- Clean up database records and Backstage catalog entries

> **This action is irreversible.** All resources will be permanently removed.

## Inputs

| Field | Required | Description |
|---|---|---|
| Tenant Name | Yes | Exact name of the tenant to delete |
| Confirm Tenant Name | Yes | Re-enter the name to confirm deletion |

## What gets removed

| Resource | Notes |
|---|---|
| Kubernetes namespace | All pods, services, and configs inside are deleted |
| Vault policy | `tenant-{name}` policy removed; all secrets under `teams/{name}/` deleted |
| ArgoCD RBAC | Team RBAC entry removed from ArgoCD config |
| GitOps directory | `platform-gitops/tenants/{name}/` removed from `mctl-core` |
| Database records | Tenant and member records deleted from Backstage DB |
| Catalog entities | Backstage removes the tenant resource and team group on next sync |

## Notes

- Running services inside the namespace will be terminated when the namespace is deleted
- Databases provisioned via the **Provision Database** template are retained by default (`databaseReclaimPolicy: retain`) — delete them separately if no longer needed
- The GitHub team in the `mctlhq` org is **not** deleted automatically

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [ArgoCD Dashboard](https://ops.mctl.ai)
