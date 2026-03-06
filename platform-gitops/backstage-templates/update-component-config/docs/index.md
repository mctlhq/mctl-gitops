# Update Environment

Update environment variables and secrets for a running service without triggering a rebuild or redeployment.

## When to use

- Adding or changing a plaintext environment variable
- Rotating or adding a Vault-backed secret
- Removing an environment variable

> The service pod will be **restarted** to pick up the new values, but no new Docker image is built.
> To deploy a new version alongside config changes, use [Deploy Version](/create/templates/default/deploy-version) instead.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | Yes | Select the service to update from the catalog |
| Environment Variables | | `KEY=VALUE` pairs, one per line. Replaces the full set of current plaintext vars. |
| Secure Variables | | `KEY=VALUE` pairs, one per line. Replaces the full set of current Vault-backed secrets. |

## What happens

1. **Plaintext vars** are written to `values.yaml` in the GitOps repo under `platform-gitops/services/{team}/{service}/`
2. **Secure vars** are written to Vault at `teams/{team}/{service}/env`
3. ArgoCD detects the GitOps change and restarts the service pod (~1-2 min)

## Notes

- If both fields are left empty, no changes are applied
- Both fields replace the **full set** of current values — include all vars you want to keep, not just the ones being changed
- Secrets are never stored in Git — only the Vault path is referenced in the Kubernetes manifest
- The ExternalSecret syncs from Vault automatically; no manual secret rotation needed in Kubernetes

## Links

- [Argo Workflows UI](https://workflows.mctl.ai)
- [ArgoCD Dashboard](https://ops.mctl.ai)
