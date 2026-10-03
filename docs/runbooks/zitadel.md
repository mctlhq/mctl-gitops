# ZITADEL (id.mctl.ai)

Platform identity provider: [ZITADEL](https://zitadel.com) v4, running in the
`zitadel` namespace. Chosen 2026-10-03 for the unified-identity epic
(mctlhq/.github#91); this deployment is work item `zitadel-deployment`
(mctlhq/mctl-gitops#1499).

| Piece | Where |
| --- | --- |
| ArgoCD Application + chart values | `platform-gitops/bootstrap/templates/core-infra/zitadel.yaml` |
| ExternalSecrets, login service key, NetworkPolicy, /debug edge deny, scrape | `platform-gitops/infra-components/identity/zitadel/` |
| Database (role `zitadel`, db `zitadel`) | `platform-gitops/infra-components/data/cnpg/shared/` |
| Alerts | `observability/vm-rules/zitadel-alerts.yaml` |
| Health probe | `observability/blackbox/vmprobes.yaml` (`zitadel-public`) |
| Vault | `secret/platform/zitadel`, `secret/platform/zitadel/database` |

Two Deployments: `zitadel` (API, Console at `/ui/console`, OIDC/OAuth/SAML
endpoints) and `zitadel-login` (the Login V2 UI at `/ui/v2/login`), both on
`id.mctl.ai`.

Phase 1 scope: the instance, Console, Login UI and one break-glass admin. No
SMTP (no email verification or password reset by mail), no external identity
providers, no OIDC clients. Those come with mctl-api#434 and the
platform/tenant SSO items, each with its own change to the egress policy.

## First deploy

1. Seed Vault. Re-submitting the bootstrap workflow is safe — every path is
   `write_if_missing`, existing secrets are skipped:
   `argo submit -n argo-workflows --from clusterworkflowtemplate/bootstrap-platform`
2. ArgoCD syncs `shared-pg` (role + Database) and `zitadel`. Check
   `kubectl -n platform-db get database zitadel-db` reports `applied: true`,
   `kubectl -n zitadel get externalsecret` all `SecretSynced` and
   `kubectl -n zitadel get certificate` `Ready`.
3. The sync then runs `zitadel-init` (wave 1) and `zitadel-setup` (wave 2) as
   Sync hooks, then starts both Deployments (wave 3). The first setup builds
   every projection and can take several minutes.
4. `curl -fsS https://id.mctl.ai/.well-known/openid-configuration` returns
   the discovery document with `"issuer":"https://id.mctl.ai"`, and
   `curl -fsS https://id.mctl.ai/ui/v2/login/healthy` returns 200.
5. `curl -s -o /dev/null -w '%{http_code}' https://id.mctl.ai/debug/metrics`
   returns 403 (the edge deny), not 200.
6. Sign in to `https://id.mctl.ai/ui/console` as the break-glass admin (below)
   and register a second-factor for it.

## Break-glass admin

User `mctl-admin` in organization `MCTL` (the login name is
`mctl-admin@mctl.id.mctl.ai` unless the org's login policy changes it), password
in Vault `secret/platform/zitadel` → `admin-password`. It has IAM_OWNER.

The password in Vault is read by the setup job **only when the instance is
first created**. Changing it in Vault later does nothing to the account:
change it in the Console, then write the new value to Vault so the two agree.
Keep this account for emergencies; day-to-day admins get their own users.

## Sync hooks instead of Helm hooks

The chart ships `zitadel-init` and `zitadel-setup` as Helm pre-install hooks.
ArgoCD maps those to PreSync, which runs before every regular resource —
including the ExternalSecrets holding the masterkey and DB password — so a
first sync could never succeed. The values override them to ArgoCD Sync hooks
in waves 1 and 2, after the secrets (wave -1) and before the Deployments
(wave 3). Both Jobs re-run on every sync; setup is idempotent.

`initJob.command: zitadel` only creates ZITADEL's schemas inside the database
CNPG already created for the `zitadel` role. No Postgres superuser credential
is ever given to this namespace.

## Secrets

- **masterkey** (`secret/platform/zitadel` → `masterkey`): encrypts signing
  keys and secrets inside the database. **Never rotate or regenerate it.** A
  database without its masterkey is unrecoverable; Vault raft snapshots
  (`vault-backup`) are its only backup, so a ZITADEL restore needs a Vault
  restore from the same era if Vault itself was lost.
- **DB password** (`secret/platform/zitadel/database`): rotate in Vault; both
  the CNPG role secret (labelled `cnpg.io/reload`) and `zitadel-config` read
  it. After both are synced (≤1h or force-sync),
  `kubectl -n zitadel rollout restart deploy/zitadel`.
- **Login session cookie secret** (`login-session-secret`): a comma-separated
  list, first entry signs, all verify. To rotate without logging users out,
  write `new,old`, restart `deploy/zitadel-login`, and after the session
  lifetime write `new` alone.
- **Login service keypair** (`zitadel-login-service-key`): issued by
  cert-manager from a namespaced self-signed Issuer, ten-year validity. If it
  is ever re-issued, restart both Deployments: ZITADEL reads the public half
  at start.

## Backups and restore

All state is in the `zitadel` database on shared-pg, backed up by CNPG to R2
(`docs/runbooks/restore.md`). There is no volume. Restore = restore the
database to a point in time, keep the masterkey from Vault unchanged, and
restart both Deployments.

## Limits worth knowing

- `/debug/*` (health, readiness, metrics) is denied at the edge by
  `identity/zitadel/debug-edge-deny.yaml`; probes and the metrics scrape
  reach it in-cluster.
- Egress is DNS + shared-pg only. Adding GitHub/Google as identity providers,
  SMTP, or Actions targets needs an explicit internet egress rule in
  `identity/zitadel/networkpolicy.yaml`.
- One replica of each Deployment in phase 1. Before anything depends on
  ZITADEL for sign-in, raise both to 2+, add PDBs, and make `ZitadelDown`
  critical.
- `ExternalDomain` (`id.mctl.ai`) is part of the instance identity and of
  every issued token's issuer. Changing it later means adding the new domain
  to the instance and migrating clients, not editing one value.

## Upgrades

Bump `targetRevision` in `bootstrap/templates/core-infra/zitadel.yaml`. Read
the ZITADEL and chart release notes first: setup migrates the schema on the
next sync, and a downgrade after that needs the database backup.
