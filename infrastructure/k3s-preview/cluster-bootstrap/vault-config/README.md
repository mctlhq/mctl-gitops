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

**Rollback for Backstage specifically:** re-add `token: ${VAULT_TOKEN}` to
`vaultSecrets` in `mctl-portal.yaml` and the `VAULT_TOKEN` /
`secretKey: vault_token` entries to the `backstage-oauth` ExternalSecret
(reverting gitops#700 does both). No new token needs minting as long as the
token below is still live.

### mctl-api-openclaw-read
Read-only access to the one path `mctl-api` actually reads:
`secret/teams/{team}/{component}/telegram`, checked during OpenClaw
onboarding preflight (`handlers_openclaw.go`) to confirm a Telegram bot
token was saved. Scoped narrower than `backstage-teams-rw` on purpose — no
write path, no reason to grant the rest of `secret/teams/*/*`.

```bash
vault policy write mctl-api-openclaw-read vault-policy-mctl-api-openclaw-read.hcl
```

### mctl-api auth: Kubernetes auth (migration in progress)

`mctl-api.yaml` sets `VAULT_KUBERNETES_ROLE: mctl-api`, which takes
precedence over `VAULT_TOKEN` (`mctl-api-secrets.yaml`) the same way
`kubernetesRole` does for Backstage. mctl-api already runs under its own
dedicated `mctl-api` ServiceAccount (`helm/templates/serviceaccount.yaml` in
the mctl-api repo) — no new identity needed, just the Vault role:

```bash
vault write auth/kubernetes/role/mctl-api \
  bound_service_account_names=mctl-api \
  bound_service_account_namespaces=mctl-api \
  policies=mctl-api-openclaw-read \
  ttl=1h
```

Not confirmed live yet. Once the image with the Kubernetes-auth support
lands and this config change deploys: confirm `"auth":"kubernetes"` in the
`vault client enabled` startup log line and `vault kubernetes auth
succeeded` on first use, and exercise the OpenClaw onboarding preflight path
(or at minimum confirm no `vault auth:` errors under load). Only after both
Backstage AND mctl-api are confirmed on Kubernetes auth does revoking
`secret/platform/backstage/vault-token` become safe — it is a shared
credential between the two, not a Backstage-only concern.

**Rollback for mctl-api specifically:** delete the `VAULT_KUBERNETES_ROLE`
line from `mctl-api.yaml` — `VAULT_TOKEN` is still configured and takes
over on the next pod restart, same one-line-revert pattern as Backstage.

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

## ESO tenant isolation

ESO reads Vault through three distinct identities. The split exists because a
`ClusterSecretStore` is usable from every namespace and authenticates as the ESO
controller's own ServiceAccount — so any path it can read is readable by every
tenant, regardless of which namespace the `ExternalSecret` lives in. A tenant
naming another tenant's `remoteRef.key` is enough to read it.

| Store | Kind | Vault role | Scope |
|---|---|---|---|
| `vault-backend` | ClusterSecretStore | `external-secrets` | `secret/data/platform/*` only |
| `tenant-store` (per tenant ns) | SecretStore | `eso-tenant-{name}` | `secret/data/teams/{name}/*` |
| `cnpg-db-creds` (platform-db) | SecretStore | `cnpg-db-creds` | `secret/data/teams/+/+/database` |

**Never add `teams/*` back to `external-secrets-read`** — that single line is
what made every tenant's secrets readable from every other tenant namespace.

Per-tenant roles are created by the `wft-create-tenant` workflow. To create one
by hand (or to backfill an existing tenant):

```bash
sed 's/${TENANT}/labs/g' vault-policy-tenant-eso.hcl.tmpl \
  | vault policy write eso-tenant-labs -

vault write auth/kubernetes/role/eso-tenant-labs \
  bound_service_account_names=tenant-eso \
  bound_service_account_namespaces=labs \
  policies=eso-tenant-labs \
  ttl=1h
```

The `platform-db` store is a one-off, created the same way from
`vault-policy-cnpg-db-creds-read.hcl` (see the header of that file).

**Multi-team tenants (`tenant.teams`).** The role name follows the *namespace*,
not the tenant: a tenant with teams renders one namespace per team
(`{tenant}-{team}`) and therefore needs one `eso-tenant-{namespace}` role each,
since `bound_service_account_namespaces` matches exact namespaces. No tenant
uses `tenant.teams` today, and `wft-create-tenant` only creates the single
bare-tenant role — create the extra roles by hand before enabling teams for a
real tenant, or ExternalSecrets in the sub-namespaces will fail with a 403.

Verify a tenant cannot reach another tenant's prefix:

```bash
vault token capabilities <tenant-token> secret/data/teams/<other-tenant>/x  # → deny
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
