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

### Backstage auth: Kubernetes auth (switched 2026-08-01)

`mctl-portal.yaml` sets `vaultSecrets.kubernetesRole: backstage`. Backstage
authenticates with the projected token of its own `backstage` ServiceAccount
— the same pattern as `vault-backup` below — instead of the long-lived
static token this replaced, which was revoked once with nothing to renew it
and took every Vault-backed route down until it was reissued by hand
(2026-08-01 incident, root cause for the switch).

```bash
vault write auth/kubernetes/role/backstage \
  bound_service_account_names=backstage \
  bound_service_account_namespaces=backstage \
  policies=backstage-teams-rw \
  ttl=1h
```

The plugin caches the issued token until 80% of its lease has elapsed and
re-logs in on expiry, or immediately if Vault rejects it, so a revoked token
self-heals. Confirmed working live 2026-08-01: `Vault kubernetes auth
succeeded` in the pod logs, DB-credentials card verified loading real
values. `vaultSecrets.token` and the `VAULT_TOKEN` key in the
`backstage-oauth` ExternalSecret are gone — Backstage itself no longer reads
`secret/platform/backstage/vault-token` at all.

**The token at `secret/platform/backstage/vault-token` is NOT revoked yet.**
`platform-gitops/bootstrap/templates/mctl-platform/mctl-api-secrets.yaml`
reads the same Vault path into its own `VAULT_TOKEN`, which `mctl-api`
(`cmd/api/main.go`) uses to build a live Vault client for its own reads —
unrelated to Backstage, added for the OpenClaw onboarding path. Revoking the
token now would break mctl-api even though Backstage is fully migrated.
Before revoking: either issue mctl-api its own separate token/role, or
migrate it to Kubernetes auth the same way Backstage was. Until then this
token stays alive and is a shared credential across two consumers, not a
Backstage-only concern anymore.

**Rollback for Backstage specifically** (Kubernetes auth breaks, static
token still valid because of the above): re-add `token: ${VAULT_TOKEN}` to
`vaultSecrets` in `mctl-portal.yaml` and the `VAULT_TOKEN` /
`secretKey: vault_token` entries to the `backstage-oauth` ExternalSecret
(reverting this PR does both). No new token needs minting — the one at
`secret/platform/backstage/vault-token` is still live for exactly this
reason.

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
