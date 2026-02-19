# Vault Policies

Apply after Vault is initialized and unsealed.

## Policies

### external-secrets-read
Used by the ExternalSecrets Operator (ESO) service account.
Grants read access to all platform and team secrets.

```bash
vault policy write external-secrets-read vault-policy-external-secrets-read.hcl
```

### backstage-teams-rw
Used by the Backstage VAULT_TOKEN (injected via backstage-secrets ExternalSecret).
Grants read/write access to `secret/teams/*/*` so Backstage scaffolder templates
can manage service secrets via the /proxy/vault endpoint.

```bash
vault policy write backstage-teams-rw vault-policy-backstage-teams-rw.hcl
```

Create/update the Backstage Vault token with both policies:
```bash
vault token create \
  -policy=backstage-teams-rw \
  -policy=external-secrets-read \
  -no-parent \
  -period=87600h \
  -orphan \
  -display-name=backstage

# Store the new token:
vault kv put secret/platform/backstage/vault-token token="<TOKEN>"
```

## Vault Secret Structure

```
secret/
├── platform/
│   ├── github-app          ← GitHub App credentials (ArgoCD + Backstage)
│   │   app-id, client-id, client-secret, installation-id, private-key
│   ├── argocd/
│   │   └── github-oauth    ← ArgoCD Dex OAuth (client-id, client-secret)
│   ├── backstage/
│   │   ├── vault-token     ← Backstage Vault API token
│   │   └── database        ← Backstage PostgreSQL credentials
│   └── vault/
│       └── r2-backup       ← Vault backup R2 credentials
└── teams/
    └── {team}/
        └── {service}       ← Service secrets (KEY=value, managed via Backstage UI)
            /repo-pat        ← Private registry PAT (optional)
```
