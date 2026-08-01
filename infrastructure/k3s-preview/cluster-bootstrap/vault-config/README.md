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
Used by `vault-secrets-backend` in Backstage to read and write service secrets
under `secret/teams/*/*`.

```bash
vault policy write backstage-teams-rw vault-policy-backstage-teams-rw.hcl
```

Backstage authenticates with the projected token of its own `backstage`
ServiceAccount — no long-lived token, same pattern as `vault-backup` below:

```bash
vault write auth/kubernetes/role/backstage \
  bound_service_account_names=backstage \
  bound_service_account_namespaces=backstage \
  policies=backstage-teams-rw \
  ttl=1h
```

The plugin caches the issued token until 80% of its lease has elapsed and
re-logs in on expiry, or immediately if Vault rejects it — so a revoked token
self-heals instead of taking the DB-credentials card down.

<details>
<summary>Legacy: static token (fallback only)</summary>

Set `vaultSecrets.token` instead of `vaultSecrets.kubernetesRole` to use a
static token. This is for local dev. Do not reintroduce it in-cluster: the
last one was revoked with nothing to renew it, and every Vault-backed route
returned 500 until it was reissued by hand (2026-08-01).

```bash
# NB: -no-parent does not exist in Vault 1.20 — -orphan is the flag.
vault token create \
  -policy=backstage-teams-rw \
  -period=87600h \
  -orphan \
  -display-name=backstage

vault kv put secret/platform/backstage/vault-token token="<TOKEN>"
```
</details>

### vault-backup
Used by the `vault-backup` CronJob (namespace `vault`) to take a raft snapshot.
No long-lived token: the CronJob authenticates via Kubernetes auth using the
projected SA token of the `vault-backup` ServiceAccount.

```bash
# 1. Policy
vault policy write vault-backup vault-policy-vault-backup.hcl

# 2. Kubernetes auth role binding the vault-backup SA to the policy.
#    Short TTL is fine — the CronJob only needs the token for one snapshot.
vault write auth/kubernetes/role/vault-backup \
  bound_service_account_names=vault-backup \
  bound_service_account_namespaces=vault \
  policies=vault-backup \
  ttl=10m
```

After both commands run, the CronJob is self-sufficient and rotates auth on
every run. The legacy static token at `secret/platform/vault/backup-token`
can be deleted once the next scheduled run succeeds.

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
            /database        ← DB credentials (written by wft-provision-database)
            /repo-pat        ← Private registry PAT (optional)
            /telegram        ← Telegram bot token (optional, openclaw intake)
```

Note the absence of a `platform/teams/...` branch. Nothing writes one; a
reader that assumed it existed is what broke the DB-credentials card
(mctl-portal#51).
