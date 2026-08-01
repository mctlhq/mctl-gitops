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

#### Current in-cluster auth: Kubernetes auth (switched 2026-08-01)

`mctl-portal.yaml` now sets `vaultSecrets.kubernetesRole: backstage`, which
takes precedence over `vaultSecrets.token` in `plugin.ts` (mctl-portal#53).
Backstage authenticates with the projected token of its own `backstage`
ServiceAccount — the same pattern as `vault-backup` below — instead of a
long-lived static token that was revoked once with nothing to renew it, and
took every Vault-backed route down until it was reissued by hand
(2026-08-01 incident).

```bash
vault write auth/kubernetes/role/backstage \
  bound_service_account_names=backstage \
  bound_service_account_namespaces=backstage \
  policies=backstage-teams-rw \
  ttl=1h
```

The plugin caches the issued token until 80% of its lease has elapsed and
re-logs in on expiry, or immediately if Vault rejects it, so a revoked token
self-heals.

#### Rollback / legacy static token (kept configured, not yet removed)

`vaultSecrets.token: ${VAULT_TOKEN}` is still set in `mctl-portal.yaml` as a
one-line rollback: since `kubernetesRole` takes precedence, deleting that one
line falls back to the static token on the next pod restart. The token itself
is still delivered by the `backstage-oauth` ExternalSecret from
`secret/platform/backstage/vault-token` and **must not be revoked** until
Kubernetes auth is confirmed working live (`Vault kubernetes auth succeeded`
in the pod logs, DB-credentials card still loads) — only then drop
`vaultSecrets.token` from `mctl-portal.yaml`, drop `VAULT_TOKEN` from the
ExternalSecret, and revoke the token below.

```bash
# NB: -no-parent does not exist in Vault 1.20 — -orphan is the flag. The
# recipe in this README carried it for months and failed outright when run.
vault token create \
  -policy=backstage-teams-rw \
  -period=87600h \
  -orphan \
  -display-name=backstage

vault kv put secret/platform/backstage/vault-token token="<TOKEN>"
```

Backstage reads `VAULT_TOKEN` only at startup, so after replacing it force a
sync of the `backstage-oauth` ExternalSecret and
`kubectl -n backstage rollout restart deploy/backstage`.

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
