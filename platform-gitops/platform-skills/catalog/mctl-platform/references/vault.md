# Vault Access

HashiCorp Vault stores all platform secrets. ExternalSecrets operator syncs them to K8s.

## Key Info

- **UI:** https://ops.mctl.ai/vault (or direct Vault UI if exposed)
- **Internal endpoint:** `http://vault.vault.svc:8200`
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
| `secret/platform/minio` | MinIO root credentials (`root-user`, `root-password`) |
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

## MinIO Access

Platform MinIO credentials live in Vault at `secret/platform/minio` and expose:
- `root-user`
- `root-password`

For in-cluster workloads, use the existing cluster-local MinIO endpoint and buckets:
- endpoint: `http://minio.minio.svc.cluster.local:9000`
- cache bucket: `platform-cache`
- state bucket: `platform-state`

Typical bootstrap form for `install-whisper-cli` caching:

```bash
kubectl -n <namespace> create secret generic minio-cache-creds \
  --from-literal=access-key=minio-admin \
  --from-literal=secret-key=<secret> \
  --from-literal=endpoint=http://minio.minio.svc.cluster.local:9000 \
  --from-literal=bucket=platform-cache
```

The `platform-cache` MinIO bucket stores shared whisper artifacts:
- `whisper/ffmpeg` — static ffmpeg binary
- `whisper/ggml-base.bin` — whisper base model (~150MB)
- `whisper/whisper-cli` — compiled whisper-cli binary
