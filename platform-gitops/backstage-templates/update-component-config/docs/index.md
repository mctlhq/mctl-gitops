# ⚙️ Update Environment

Update environment variables and secrets for a running service without triggering a full rebuild.

## When to use

Use this template when you need to:
- Add or change a plaintext environment variable
- Rotate or add a secret (Vault-backed)
- Remove an environment variable

> The service will be **restarted** to pick up the new configuration, but no new Docker image is built.

## Inputs

| Field | Required | Description |
|---|---|---|
| Service | ✅ | Select the service to update from the catalog |
| Env vars | | Plaintext `KEY=value` pairs (replaces current non-secret vars) |
| Secret env vars | | Plaintext `KEY=value` pairs (replaces current secrets in Vault) |

## What happens

1. Plaintext env vars are written to `values.yaml` in the GitOps repo
2. Secret env vars are written to Vault at `teams/{team}/{service}/env`
3. ArgoCD detects the change and restarts the service pod

## Notes

- Providing an empty value for a field **clears** all vars of that type
- To remove a single var, submit the full list without the key you want removed
- Secrets are never stored in Git — only Vault paths are referenced

## Links

- [GitHub Actions workflow](https://github.com/dmitriimashkov/mctl.me/actions/workflows/release-service.yml)
