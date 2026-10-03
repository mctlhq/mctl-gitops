# ZITADEL (auth.mctl.ai)

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
`auth.mctl.ai`.

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
4. `curl -fsS https://auth.mctl.ai/.well-known/openid-configuration` returns
   the discovery document with `"issuer":"https://auth.mctl.ai"`, and
   `curl -fsS https://auth.mctl.ai/ui/v2/login/healthy` returns 200.
5. `curl -s -o /dev/null -w '%{http_code}' https://auth.mctl.ai/debug/metrics`
   returns 403 (the edge deny), not 200.
6. Sign in to `https://auth.mctl.ai/ui/console` as the break-glass admin (below)
   and register a second-factor for it.

## Break-glass admin

User `mctl-admin` in organization `MCTL` (the login name is
`mctl-admin@mctl.auth.mctl.ai` unless the org's login policy changes it), password
in Vault `secret/platform/zitadel` → `admin-password`. It has IAM_OWNER.

The password in Vault is read by the setup job **only when the instance is
first created**. Changing it in Vault later does nothing to the account:
change it in the Console, then write the new value to Vault so the two agree.
Keep this account for emergencies; day-to-day admins get their own users.

## Declarative configuration (#1520)

ZITADEL's own configuration (login policies, organizations, projects, OIDC
applications, users) is declared in `platform-gitops/helm-charts/zitadel-iac/iac/`
and applied by OpenTofu, not clicked in the Console. A change made only in the
Console is drift: the next apply either reports it or reverts it.

- **Who applies.** The `zitadel-iac` Job, a PostSync hook of the `zitadel`
  Application, so it runs after every sync. Its inputs (the root, the
  allowed actions, the image) are the regular ConfigMap `zitadel-iac-inputs`,
  so changing any of them makes the Application OutOfSync and auto-sync
  runs the Job. A hook is never diffed, so an input kept only in a hook would
  merge without ever being applied. Its image
  (`platform-gitops/images/zitadel-iac`) carries OpenTofu and the pinned
  provider. It never downloads anything at run time.
- **Credential.** The ZITADEL System API user `iac`. It is declared in the
  runtime config (`SystemAPIUsers`) by the certificate of the cert-manager key
  pair `zitadel-iac-key`, with System membership `IAM_OWNER` and `ORG_OWNER`.
  ZITADEL mounts only the certificate; only the Job mounts the private key.
  No console-created service user exists.
- **State.** The OpenTofu `kubernetes` backend, in the `zitadel` namespace:
  Secret `tfstate-default-zitadel-iac`, locked by Lease
  `lock-tfstate-default-zitadel-iac`.
- **Guard.** The Job plans, then applies only if every planned action is in
  `allowedActions` (`helm-charts/zitadel-iac/values.yaml`). Otherwise it fails
  before apply, and the plan is in its log. Widen the list in the PR that needs
  it. A plan with no changes exits without applying.
- **Reading a run.** `kubectl -n zitadel logs job/zitadel-iac`. The Job is
  replaced on the next sync.
- **Break-glass.** If every human admin loses their passkey, the `iac` key
  can still change any policy. Declare the fix in `iac/`, or run the image by
  hand with the key mounted. Rotating the key: delete Secret `zitadel-iac-key`,
  let cert-manager reissue it, restart the `zitadel` Deployment.
- **CI.** `validate-manifests.yml`, job `zitadel-iac`, runs `fmt -check`,
  `init -lockfile=readonly` and `validate`, and renders the chart. A provider
  bump changes `iac/versions.tf`, `iac/.terraform.lock.hcl` and the image
  together.

### Sign-in policy (#1520 S2)

Every sign-in needs a WebAuthn authenticator (a passkey or a security key):

- A passkey sign-in works on its own.
- A password sign-in must add a U2F second factor (WebAuthn, not TOTP). A
  user with none enrolled is sent to enrol one, with no skip.
- Self-registration is off and the password-reset link is hidden. Accounts
  are declared here (S3), not signed up for.

Login V2 has no "passkeys only" switch: `user_login = false` also disables
passkeys, leaving only external IdPs, and no API removes an existing password.
So passwords remain but never suffice alone.

Recovery if an admin loses every authenticator: the `iac` break-glass key
above. Remove their WebAuthn registrations through the API with it, so they can
enrol again.

### Tenant organizations and users (#1520 S3)

- **Source.** One Vault secret per tenant, `secret/platform/zitadel/users/<tenant>`.
  Each field is one user: the field name is the user name, the value a JSON
  object `{"email", "first_name", "last_name", "preferred_language"}`
  (`preferred_language` is optional, default `en`). This repository is public,
  so the list is never in git. ExternalSecret `zitadel-iac-users` finds every
  secret under the path and folds them into `users.json` for the pod.
- **Result.** One organization per tenant secret, named after the tenant, and
  its users. `for_each` keys are `tenant/user_name`. Email and names, display
  name included, are sensitive, so the Job log shows neither.
- **Invitation.** A user is created without a password and with an unverified
  e-mail, so ZITADEL mails a code (Resend, `noreply@mctl.ai`). The text is
  declared in `iac/messages.tf`, in English and Russian, and goes out in the
  user's `preferred_language`. The button opens Login V2 `/verify`, then
  "Choose authentication method", where the user picks Passkeys. Verified end
  to end on a local v4.19.2 with Login V2 and a mail catcher.
- **Adding a user.** Add a field to the tenant's secret, e.g.
  `vault kv patch secret/platform/zitadel/users/<tenant> <user_name>='{"email": ...}'`.
  **Adding a tenant** is a new secret. The hourly CronJob `zitadel-iac` (or
  the next sync) creates them. No PR is needed, because only data changes.
- **Removing a user or a tenant** plans a `delete`, which `allowedActions`
  refuses, so the run fails with the plan in its log. Widen it in a PR for
  that one change, then narrow it again.
- **SMTP.** `zitadel_email_provider_smtp.resend`, `smtp.resend.com:2465`
  (implicit TLS). Not 465: Hetzner Cloud blocks outgoing 25 and 465. The
  password is a sending-only Resend key in Vault
  `secret/platform/zitadel/smtp` (`password`). Egress is the
  `allow-zitadel-smtp-egress` NetworkPolicy, port 2465 only.

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

## Known risk: same site as tenant workloads

`auth.mctl.ai` shares the registrable domain `mctl.ai` with tenant
applications (`<tenant>-<service>.mctl.ai` and bare names such as
`seerrsense.mctl.ai`), which run code the platform does not control. For a
browser that makes them the same site:

- a tenant page can set a cookie with `Domain=.mctl.ai` that the browser then
  sends to `auth.mctl.ai` (cookie tossing), and
- `SameSite` cookie attributes do not separate them, because a request from a
  tenant app to the IdP is same-site.

Accepted for phase 1, while nothing signs in through ZITADEL. Two follow-ups
in the unified-identity epic close it, and must land before real sign-ins:

- reserve platform hostnames (`auth`, `api`, `app`, `ops`, …) at admission,
  so no tenant Ingress can claim `auth.mctl.ai` (#1503);
- move tenant applications to a separate registrable domain listed in the
  Public Suffix List (the `github.io` / `vercel.app` pattern), leaving
  `mctl.ai` to the platform (#1504).

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
- `ExternalDomain` (`auth.mctl.ai`) is part of the instance identity and of
  every issued token's issuer. Changing it later means adding the new domain
  to the instance and migrating clients, not editing one value.

## Upgrades

Bump `targetRevision` in `bootstrap/templates/core-infra/zitadel.yaml`. Read
the ZITADEL and chart release notes first: setup migrates the schema on the
next sync, and a downgrade after that needs the database backup.
