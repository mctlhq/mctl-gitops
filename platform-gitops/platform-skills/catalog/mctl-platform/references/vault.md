# Vault Access

HashiCorp Vault stores all platform secrets. ExternalSecrets operator syncs them to K8s.

## Key Info

- **UI:** https://ops.mctl.ai/vault (or direct Vault UI if exposed)
- **Internal endpoint:** `http://vault.vault.svc:8200`
- **TLS:** edge only (`https://secrets.mctl.ai`). The Raft listener is
  `tls_disable = 1` (SOC F15 accepted residual). Do not flip that without
  a cert/retry_join plan — see `docs/runbooks/control-plane.md`.
- **Namespace:** `vault`
- **KV mount:** `secret` (KV v2)
- **ClusterSecretStore:** `vault-backend`

## Auth Methods

### 1. Admin token (direct write access)

The admin Vault token is available at **https://secrets.mctl.ai/ui/** — use it for
direct reads/writes. To use from CLI:

```bash
# Port-forward vault, then use the token
kubectl port-forward -n vault vault-0 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=hvs.<admin-token-from-secrets.mctl.ai>

# Read a secret
vault kv get secret/platform/mctl-api/oauth

# Add/update a field (patch preserves other fields)
vault kv patch secret/platform/mctl-api/oauth MY_KEY=myvalue

# Write a new secret (overwrites all fields!)
vault kv put secret/platform/mctl-api/oauth KEY1=val1 KEY2=val2
```

> The admin token has full read+write access to `secret/platform/*` and `secret/teams/*`.

### 2. Kubernetes Auth (read-only, external-secrets role)

Used by ExternalSecrets operator. **Read-only** — cannot write secrets.

```bash
SA_TOKEN=$(kubectl -n external-secrets create token external-secrets --duration=3600s \
  --audience=https://kubernetes.default.svc)

kubectl port-forward -n vault vault-0 8200:8200 &
export VAULT_ADDR=http://127.0.0.1:8200
VAULT_TOKEN=$(vault write -field=token auth/kubernetes/login \
  role=external-secrets jwt="${SA_TOKEN}")
```

### 3. GitHub Actions JWT (read-only repo PAT)

Used by `mctl-gitops` `.github/workflows/build-image.yaml`. No long-lived
Vault token in GitHub Actions — the job mints a GitHub OIDC JWT and logs
into `auth/jwt` role `github-actions`.

```bash
# From a GitHub Actions runner (id-token: write). Audience must match the
# Vault role bound_audiences (https://github.com/mctlhq).
JWT=$(curl -sS \
  -H "Authorization: bearer ${ACTIONS_ID_TOKEN_REQUEST_TOKEN}" \
  "${ACTIONS_ID_TOKEN_REQUEST_URL}&audience=https%3A%2F%2Fgithub.com%2Fmctlhq" \
  | jq -r .value)

VAULT_TOKEN=$(curl -sS -X POST \
  -H "Content-Type: application/json" \
  -d "{\"role\":\"github-actions\",\"jwt\":\"${JWT}\"}" \
  "https://secrets.mctl.ai/v1/auth/jwt/login" | jq -r .auth.client_token)
```

Policy `github-actions-repo-pat` can only read `secret/data/teams/+/+/repo-pat`.
One-time Vault enable is documented in
`infrastructure/k3s-preview/cluster-bootstrap/vault-config/README.md`.

### 4. Recommended: Write via Argo Workflow

The platform's `tpl-vault-write` ClusterWorkflowTemplate has write access:

```yaml
# Via mctl MCP deploy with secret_env_vars:
mctl_deploy_service(
  action="update-config",
  team_name="myteam",
  component_name="myservice",
  secret_env_vars="MY_KEY=myvalue"
)
# → writes to Vault: secret/data/teams/myteam/myservice → MY_KEY
```

## Secret Paths

| Path | Contents |
|------|----------|
| `secret/platform/mctl-api/*` | API service secrets (argocd-token, backstage-token, etc.) |
| `secret/platform/github-app` | GitHub OAuth client_id/secret |
| `secret/platform/alertmanager` | Telegram bot token |
| `secret/teams/{team}/{service}` | Per-service secrets (mctl-api-token, etc.) |
| `secret/teams/{team}/{service}/database` | DB credentials (username, password, host, port, database) |

## ExternalSecret Pattern

```yaml
extraExternalSecrets:
  my-secret:
    refreshInterval: 1h
    targetSecret: my-secret
    data:
      - secretKey: MY_KEY          # K8s secret key name
        remoteKey: secret/data/platform/my-path   # Vault path (with secret/data/ prefix)
        property: my-field         # field inside the Vault secret
```

**Note:** ClusterSecretStore `vault-backend` adds `secret/data/` prefix automatically for KV v2.
Use path WITHOUT `secret/data/` in `dbSecret.vaultPath`, WITH `secret/data/` in `extraExternalSecrets.remoteKey`.

## Object Storage (R2)

The in-cluster MinIO (`secret/platform/minio`) was decommissioned in 2026-10;
object storage is Cloudflare R2. Each consumer gets its own bucket-scoped R2
API token in Vault under its platform path, e.g.
`secret/platform/mctl-claude-remote/r2` (`access-key`, `secret-key`) or
`secret/platform/r2-loki-argo`. Buckets are declared in
`infrastructure/cloudflare/account/r2.tf`; tokens are created in the
Cloudflare dashboard and written to Vault by an operator.
