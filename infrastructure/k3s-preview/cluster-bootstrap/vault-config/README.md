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

### mctl-api-erpact-deployer-read

Read-only access to one tenant secret, `secret/teams/erpact/deployer`'s
`DEPLOYER_API_TOKEN` property: the bearer token mctl-api uses to call the
erpact tenant's own site-deployer (mctl-api#486, cmd/api/main.go's
`erpactDeployer` construction), backing the temporary
`/api/v1/tenants/erpact/sites*` routes. Read at request time through
mctl-api's own `VaultReader`, not through an ExternalSecret env var -- the cluster-wide `vault-backend`
ClusterSecretStore's policy (`vault-policy-external-secrets-read.hcl`)
deliberately denies all of `secret/data/teams/*`, since it is reachable
from every namespace and any tenant path granted there becomes readable by
every other tenant. This policy, bound only to mctl-api's own Kubernetes
auth role below, is the narrow alternative.

```bash
vault policy write mctl-api-erpact-deployer-read vault-policy-mctl-api-erpact-deployer-read.hcl
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
  policies=mctl-api-erpact-deployer-read \
  ttl=1h
```

Not confirmed live yet. Once the image with the Kubernetes-auth support
lands and this config change deploys: confirm `"auth":"kubernetes"` in the
`vault client enabled` startup log line and `vault kubernetes auth
succeeded` on first use, and exercise a route that reads Vault through it,
such as the ERPact site routes (or at minimum confirm no `vault auth:`
errors under load). Only after both
Backstage AND mctl-api are confirmed on Kubernetes auth does revoking
`secret/platform/backstage/vault-token` become safe — it is a shared
credential between the two, not a Backstage-only concern.

**Rollback for mctl-api specifically:** delete the `VAULT_KUBERNETES_ROLE`
line from `mctl-api.yaml` — `VAULT_TOKEN` is still configured and takes
over on the next pod restart, same one-line-revert pattern as Backstage.

### github-actions (GitHub OIDC JWT)

`build-image.yaml` no longer uses a long-lived `VAULT_TOKEN` GitHub Actions
secret. The job requests an OIDC JWT from `token.actions.githubusercontent.com`
(`permissions.id-token: write`) and logs into Vault `auth/jwt` as role
`github-actions`. The resulting token can only read
`secret/data/teams/+/+/repo-pat`.

**Applied and confirmed end to end on 2026-08-15**: `auth/jwt` is mounted, the
policy and role exist, and a real `build-image.yaml` run authenticated against
them. The block below is kept as the recreate-from-scratch recipe.

One-time apply (Vault admin token; `VAULT_ADDR=https://secrets.mctl.ai`).
Vault 1.17+ requires `bound_audiences` to match the JWT `aud` claim.

```bash
vault auth enable jwt

vault write auth/jwt/config \
  oidc_discovery_url="https://token.actions.githubusercontent.com" \
  bound_issuer="https://token.actions.githubusercontent.com"

vault policy write github-actions-repo-pat \
  infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-github-actions-repo-pat.hcl

vault write auth/jwt/role/github-actions -<<'EOF'
{
  "role_type": "jwt",
  "user_claim": "sub",
  "bound_audiences": "https://github.com/mctlhq",
  "bound_claims_type": "glob",
  "bound_claims": {
    "repository": "mctlhq/mctl-gitops",
    "job_workflow_ref": "mctlhq/mctl-gitops/.github/workflows/build-image.yaml@*"
  },
  "policies": ["github-actions-repo-pat"],
  "ttl": "10m"
}
EOF
```

Vault must be able to fetch GitHub's OIDC JWKS over HTTPS (egress from the
vault namespace to `token.actions.githubusercontent.com`). The vault
namespace's NetworkPolicy is ingress-only, so nothing blocks this.

#### No Vault GitHub Actions secrets remain

All three were deleted on 2026-08-15, each after an org-wide
`gh search code` confirmed nothing referenced it:

- **`VAULT_ADDR`** (repo, `mctlhq/mctl-gitops`) — this one was actively
  breaking the JWT login. Its value had gone stale and answered
  `HTTP 410 Gone` from a runner. Because the step does
  `VAULT_ADDR="${VAULT_ADDR:-https://secrets.mctl.ai}"`, the stale secret
  silently *shadowed* the correct default, so every login died in ~0.3s with
  `Vault JWT login failed; skipping Vault PAT` while the Vault side was
  perfectly healthy. The step still reads `secrets.VAULT_ADDR` into its env,
  so recreating the secret remains a supported override — but it must be
  exactly `https://secrets.mctl.ai`. A `${SECRET:-sane-default}` fallback
  buys nothing while a wrong secret exists.
- **`VAULT_TOKEN`** (org, visibility ALL) — an earlier revision of this file
  said other repositories still read it. They do not: the only match for
  `secrets.VAULT_TOKEN` anywhere in the org was that sentence itself. There
  was never a repo-level `VAULT_TOKEN` on `mctlhq/mctl-gitops`.
- **`VAULT_PROVISION_TOKEN`** (repo and org) — zero references, unrelated to
  this flow, removed in the same sweep.

Actions secret *values* can never be read back, only names and update
timestamps. Verify consumers by searching code, not by inspecting the secret.

#### Reading a run

`build-image.yaml` discards Vault's error body, so the step log is all you get:

| Log line | Meaning |
|---|---|
| `Vault HTTP status: 200` | Login worked, PAT found |
| `Vault HTTP status: 404` | **Also success** — login and policy are fine, there is simply no `repo-pat` at that path |
| `Vault HTTP status: 403` | Login worked, the policy is wrong |
| `Vault JWT login failed` | Login itself was rejected — wrong `VAULT_ADDR`, or a claim does not match the role |

To probe without building anything, dispatch `build-image.yaml` with a
deliberately nonexistent `git_ref`: the Vault step runs first and checkout
then fails before GHCR login. Do not let a probe run to completion — a
successful build also pushes `:latest`.

To debug a *rejected* login, push a throwaway branch carrying an `on: push`
workflow with `id-token: write` that decodes the JWT payload claims and curls
`auth/jwt/login` with `-w '%{http_code}'`. Never log the raw JWT — it is a
bearer credential; print decoded claims only. `workflow_dispatch` will not
work here, as it only fires from the default branch.

**Rollback:** `vault auth disable jwt` plus
`vault policy delete github-actions-repo-pat`. No workflow change is needed —
`build-image.yaml` falls back to the GitHub App token on its own, which is
exactly what it did for the whole period this role did not exist.

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

### coolify-mcp
Used by `mctl-coolify-mcp`'s multi-tenant mode (`mctlhq/mctl-coolify-mcp`,
`MCP_TENANCY=multi`) to store per-tenant Coolify credentials and OAuth AS
state, self-service: each tenant enrolls and revokes their own record while
the process runs, which is why this cannot be served by ESO (read-only
mount, no write path) the way `projects-mcp` is.

**This service gets its own dedicated KV v2 mount, `coolify-mcp-users/`, not
a path under the shared `secret/` mount.** Its `VaultClient` (`src/lib/vault.ts`
in that repo) takes a single `mount` string and uses it verbatim as the Vault
API path segment (`${mount}/data/${key}`), which only resolves if a secrets
engine is actually enabled at that exact path — a subpath of `secret/` would
404, since `secret/` itself is the mount and Vault does not treat `secret/teams/labs/coolify-mcp`
as anything special within it. A small dedicated mount per hosted service
that needs a write path (unlike everything else here, which reads through
ESO) keeps its ACL off the shared mount's surface entirely. No `delete`
capability anywhere — only `destroy`, since KV v2's `delete` tombstones the
current version but leaves every prior version readable, which would make a
revocation not actually revoke.

No dedicated ServiceAccount exists yet for this service — `labs` currently
shares its `default` SA across 15+ deployments in `platform-gitops/services/labs/`,
and binding this role to `default` would let every one of them authenticate
as `coolify-mcp` and read tenant Coolify tokens. This role is bound ahead of
that ServiceAccount's creation; **do not deploy `coolify-mcp` until
`platform-gitops/services/labs/coolify-mcp/values.yaml` sets
`serviceAccount: {create: true}`** (the `claude-remote` pattern), or the
Kubernetes-auth login will fail closed — safe, but worth knowing why up
front, since the failure mode looks like a login bug rather than a missing
identity.

```bash
# 1. Dedicated KV v2 mount — not a path under secret/, see above.
vault secrets enable -path=coolify-mcp-users -version=2 kv

# 2. Policy
vault policy write coolify-mcp vault-policy-coolify-mcp.hcl

# 3. Kubernetes auth role, bound to the ServiceAccount the service's own
#    values.yaml must create before this role can ever be assumed.
vault write auth/kubernetes/role/coolify-mcp \
  bound_service_account_names=labs-coolify-mcp-base-service \
  bound_service_account_namespaces=labs \
  policies=coolify-mcp \
  ttl=1h
```

Deployment must set `VAULT_KV_MOUNT=coolify-mcp-users` (not a `teams/...`
path) to match.

Applied and confirmed live 2026-09-20: mount, policy and role all three, plus
the dedicated ServiceAccount from a follow-up PR. First deploy crash-looped
until three separate fixes landed — wrong container command, `undici`/Node 20
incompatibility, and this policy missing `create` on `metadata/*` — the last
of which 403'd every first-ever write (including `oauth-state` on first boot)
until fixed live, then backported to the `.hcl` file above.

### vault-human-auth-iac (human sign-in through ZITADEL)

Humans sign in to Vault through ZITADEL (`auth.mctl.ai`) on the `auth/mctl`
mount, and get access from the `groups` claim: `admins` maps to the `admin`
policy, a tenant name to `human-tenant-<tenant>`: read and write on
`secret/teams/<tenant>/*`. That policy grants no destroy and no metadata
write, and keeps `<service>/database` read only
(docs/runbooks/vault-human-auth.md). None of that is typed here: the
`vault-human-auth-iac` Job (Argo CD Application of the same name, namespace
`vault-human-auth-iac`) declares the mount, its role, the external groups,
their aliases and the tenant policies with OpenTofu, and re-applies hourly.

The only hand-applied part is the Job's own identity: the policy
`vault-human-auth-iac` and the Kubernetes auth role that hands it out. The
policy covers `sys/auth/mctl` (no delete), `sys/mounts/auth/mctl` (+`tune`),
`auth/mctl/{config,role/*}`, `identity/group*`,
`identity/group-alias*`, `sys/policies/acl/human-tenant-*`, and the audit
device at `sys/audit/stdout` (plus listing `sys/audit`; no delete), and no
secret data. It cannot write the `admin` policy, create tokens, or touch any other
auth mount. It is still admin-equivalent in effect, since it decides which
identity lands in which policy group; read the header of the `.hcl`.

One-time apply (owner, admin token, `VAULT_ADDR=https://secrets.mctl.ai`).
Safe before the Job exists: the role binds a ServiceAccount that Argo CD
creates later.

```bash
vault policy write vault-human-auth-iac \
  infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-vault-human-auth-iac.hcl

vault write auth/kubernetes/role/vault-human-auth-iac \
  bound_service_account_names=vault-human-auth-iac \
  bound_service_account_namespaces=vault-human-auth-iac \
  token_policies=vault-human-auth-iac \
  token_ttl=10m \
  token_max_ttl=10m
```

Check: `vault policy read vault-human-auth-iac` matches the file, and
`vault read auth/kubernetes/role/vault-human-auth-iac` shows the one
ServiceAccount, the one namespace and the one policy.

Proven on a local Vault 1.17.2 (the live version) with a token holding only
this policy: the OpenTofu root creates everything, re-plans clean, adds and
removes a tenant, and rotates the client; reading any `secret/` path, reading
or writing any other policy (`admin` included), disabling the mount, enabling
another auth method, writing a Kubernetes auth role and creating a token are
all refused (403). Each grant was checked by removing it: without
`sys/mounts/auth/mctl` the apply fails, while `read` on `sys/auth/mctl`,
`sudo` on `sys/mounts/auth/mctl`, `list` anywhere and `create` on the
`identity/*/id` paths turned out unneeded and are not granted.

**The audit device** (`iac/audit.tf`, docs/runbooks/vault-audit.md) added
`read`+`sudo` on `sys/audit` and `update`+`sudo` on `sys/audit/stdout`.
Proven the same way on a local Vault 1.17.2 with a token holding only this
policy: the root enables the device, re-plans clean, and re-enables it after
root disables it; removing any one of the four capabilities makes the apply
fail with 403; disabling `stdout`, enabling any other audit path, and
re-enabling `stdout` with other options (`log_raw=true`) are all refused.

**The move from `auth/oidc` to `auth/mctl`** (docs/runbooks/vault-human-auth.md)
needed a temporary `sys/remount` grant, limited by `allowed_parameters` to
`from=auth/oidc`, `to=auth/mctl`. The cleanup step removed it and renamed the
`oidc` paths to `mctl`, so the Job keeps no remount ability. The owner
applied that file before the cleanup change merged, as above, and it was
diffed byte-identical (the Job touches only `mctl` paths by then). The end
state was proven on a local Vault 1.17.2: the root re-plans clean, and
`sys/remount` gets a 403.

**Rollback:** `vault delete auth/kubernetes/role/vault-human-auth-iac` and
`vault policy delete vault-human-auth-iac`. The Job then fails at login and
changes nothing; what it already declared stays as it is.

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
│   │   └── github-oauth    ← no reader in this repo (was the ArgoCD Dex GitHub connector)
│   ├── backstage/
│   │   └── database        ← Backstage PostgreSQL credentials
│   └── vault/
│       └── r2-backup       ← Vault backup R2 credentials
└── teams/
    └── {team}/
        └── {service}       ← Service secrets (KEY=value, managed via Backstage UI)
            /database        ← DB credentials (written by wft-provision-database)
            /repo-pat        ← Private registry PAT (optional)
```

Note the absence of a `platform/teams/...` branch. Nothing writes one; a
reader that assumed it existed is what broke the DB-credentials card
(mctl-portal#51).
