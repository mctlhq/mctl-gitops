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
Keep this account for emergencies; day-to-day admins get their own users
(see "Platform admins" below).

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
  `allowedActions` (`helm-charts/zitadel-iac/values.yaml`). Deletes are never an
  action class there: every address the plan destroys or replaces must be
  listed in `allowedDeletes`, and the count of addresses read must match the
  JSON plan's deletes. Otherwise it fails before apply, and the plan is in its
  log. Widen either list in the PR that needs it, naming exact addresses. A
  plan with no changes exits without applying.
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

### Platform admins

`iac/admins.tf` holds the one list of platform admins. Each of them holds
every admin grant: Argo CD `admins`, Vault `admins` and Cloudflare Access
`access`. The MCTL API project has no roles, so there is nothing to grant
there: any `MCTL` user, and any user of a tenant organization (see "mctl-api
audience"), gets its token, and mctl-api grants nothing based on ZITADEL
roles yet.

- **Break-glass.** `mctl-admin` is in `break_glass_admins` and is looked up
  by its login name. It is not created by this root.
- **Personal accounts.** These come from Vault
  `secret/platform/zitadel/admins`, one field per person. The field name is
  the account's stable key, a plain handle matching `^[a-z0-9][a-z0-9._-]*$`
  (no `@`, never `mctl-admin`): it addresses the user and its grants. The
  value is a JSON object
  `{"email", "first_name", "last_name", "preferred_language", "username"}`,
  where `preferred_language` is optional and defaults to `en`,
  `username`, optional, is the login name when it should differ from the key
  (same pattern; login names must be unique), and `github_login`, optional,
  is the admin's GitHub login (see "GitHub login claim"). ExternalSecret
  `zitadel-iac-admins` extracts the secret into `admins.json`, and the pod
  passes it on as `TF_VAR_platform_admins`. The owner writes the secret;
  it is never in git:

  ```sh
  vault kv put secret/platform/zitadel/admins \
    <user_name>='{"email": "<email>", "first_name": "<first>", "last_name": "<last>", "preferred_language": "en"}'
  # a second admin later: vault kv patch secret/platform/zitadel/admins <user_name2>='{...}'
  ```

  The user is created like a tenant user. It has no password and an
  unverified e-mail, so an invitation goes out. Redeeming it in Login V2
  enrols a passkey. The instance login policy is unchanged: a password alone
  never suffices.
- **Fail closed.** The pod cannot start if the Vault path is missing or was
  never read, because ESO creates no Secret and the `secretKeyRef` is not
  optional. If a later read fails, ESO keeps the last content
  (`deletionPolicy: Retain`). OpenTofu refuses an empty or malformed object
  (variable validation). In none of these cases does a plan remove an admin
  or a grant.
- **Renaming a personal admin's login** is `username` on the existing entry,
  never a new field name: a new key is a new user with a new ID, and the ID
  is the `sub` that Argo CD, Vault, Cloudflare Access, mctl-api and the
  passkeys know. The plan is an in-place update of `user_name` (proven on
  v4.19.2 with provider 3.8.7 before `username` was added); nothing that
  matches on the ID changes. What does follow the login name is display
  only: mctl-api's `User.ID` for ZITADEL callers (audit and whoami), the
  `username` metadata Vault maps from `preferred_username`, and Grafana's
  login (it finds the user by its OAuth id and updates the login).
- **Removing a personal admin** from Vault plans deletes of
  `zitadel_human_user.platform_admin["<user_name>"]` and of its
  `zitadel_user_grant.{argocd_admin,vault_admin,cloudflare_access}["<user_name>"]`.
  The guard refuses them until those addresses are in `allowedDeletes`.
- **First sign-in of a personal admin.**
  1. Open the invitation mail and follow it to Login V2 `/verify`. Choose
     Passkeys and register one. A second passkey or a security key is a
     good idea.
  2. Argo CD: sign in at `https://ops.mctl.ai` via ZITADEL. **User Info**
     must show `groups: [admins]`.
  3. Vault: run `vault login -method=oidc -path=mctl` (or use the UI at
     `https://secrets.mctl.ai`). `vault token lookup` must show
     `identity_policies` `[admin]`.
  4. Cloudflare Access: open the test application behind the ZITADEL
     identity provider and sign in.
- **Retiring mctl-admin from day-to-day grants** is a later step, and only
  after a personal account has passed all of the above. Remove
  `mctl-admin@mctl.auth.mctl.ai` from `break_glass_admins`, and list the
  deletes of `zitadel_user_grant.{argocd_admin,vault_admin,cloudflare_access}["mctl-admin@mctl.auth.mctl.ai"]`
  in `allowedDeletes` in the same PR. The account itself stays, with
  IAM_OWNER, as the ZITADEL break-glass.

### Tenant organizations and users (#1520 S3)

- **Source.** One Vault secret per tenant, `secret/platform/zitadel/users/<tenant>`.
  Each field is one user: the field name is the user name, the value a JSON
  object `{"email", "first_name", "last_name", "preferred_language", "argocd",
  "vault", "workflows", "frappe", "github_login"}` (`preferred_language` is
  optional, default `en`; `argocd`, `vault` and `workflows` are optional,
  default `false`, see "Argo CD sign-in" and "Vault sign-in" below, and
  `iac/workflows.tf`; `frappe` is for tenant `erpact` only, see "ERPact copy
  sign-in"; `github_login` is optional, see "GitHub login claim"). This repository is public,
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
- **Removing a user or a tenant** plans a `delete`, which the guard refuses
  unless that address (e.g. `zitadel_human_user.tenant["erpact/alice"]`) is in
  `allowedDeletes`. The user's Argo CD grant goes with it
  (`zitadel_user_grant.argocd_tenant["erpact/alice"]`, see below), and a tenant
  also takes its `argocd_tenant` role, project grant, `argocd_groups` action
  and trigger. List every one of those addresses. Add them in a PR for that
  one change, and empty the list again afterwards.
- **SMTP.** `zitadel_email_provider_smtp.resend_2465`, `smtp.resend.com:2465`
  (implicit TLS). Not 465: Hetzner Cloud blocks outgoing 25 and 465. The
  password is a sending-only Resend key in Vault
  `secret/platform/zitadel/smtp` (`password`). Egress is the
  `allow-zitadel-smtp-egress` NetworkPolicy, port 2465 only.
  **Never change the SMTP provider in place:** ZITADEL v4.19.2 cannot project
  an SMTP update (the password column is written twice), so the apply
  "succeeds" while ZITADEL keeps the old settings. Change it by renaming the
  resource (a delete plus a create), with the old address in `allowedDeletes`.
  The cloud firewall (`infrastructure/k3s-preview/kube.tf`,
  `extra_firewall_rules`) must allow the port as well.

### Argo CD sign-in (#1500)

`iac/argocd.tf` declares Argo CD's ZITADEL clients and who gets which Argo CD
group:

- **Project `Argo CD`** in organization `MCTL`, separate from `MCTL platform`
  because its checks apply to every application in it. With
  `project_role_check` and `has_project_check`, a user who holds no role on it
  gets no token: ZITADEL answers `Errors.User.GrantRequired` before any
  redirect to Argo CD.
- **Roles are Argo CD group names.** `admins` (`g, admins, role:admin` in
  `platform-gitops/argocd/values.yaml`), held by the platform
  admins (`platform_admin_user_ids`, see "Platform admins"). One role per tenant
  organization, named after the tenant (`argocd/rbac/tenants/<tenant>.csv`).
  Each tenant organization is granted only its own role, and a tenant user
  holds it **only if** their Vault entry carries `"argocd": true` (opt-in,
  owner decision on #1500). Without the flag the user is refused, like any
  user without a role. Granting or revoking it is a Vault-only change; a
  revoke plans a delete of `zitadel_user_grant.argocd_tenant["<tenant>/<user>"]`,
  which needs that address in `allowedDeletes`.
- **`groups` claim.** Argo CD needs a flat list of strings. ZITADEL's own role
  claim is a map, so the Actions v1 action `argocdGroups` copies the user's
  roles on this project, and nothing else, into `groups` at
  `PRE_USERINFO_CREATION` (with `id_token_userinfo_assertion`, the ID token
  carries it). Actions v1 run in the *user's* organization, so the action and
  its trigger exist in `MCTL` and in every tenant organization.
  `project_role_assertion` must stay on: without it the grants are not loaded
  into the action at all and the claim is never set. The action may fail
  (`allowed_to_fail`), which leaves the claim out and so grants nothing.
- **Clients.** `argocd` (web, client secret) and `argocd-cli` (native, PKCE,
  `http://localhost:8085/auth/callback`, for `argocd login --sso`). Their IDs
  and the secret go into `argocd/argocd-oidc-zitadel`, which `argocd-cm`
  references as `$argocd-oidc-zitadel:<key>`.

Verified on a local v4.19.2: an admin gets `groups: ["admins"]`, a flagged
tenant user `["<tenant>"]`, an unflagged tenant user or a user of `MCTL` with
no grant is refused, and
Forgejo (another project) still signs in users without any Argo CD role, with
no `groups` claim.

### Vault sign-in

`iac/vault.tf` declares who may sign in to Vault (`secrets.mctl.ai`), and as
what. Vault's own side (the `auth/mctl` mount, groups, policies) is the
`vault-human-auth-iac` Job; see `docs/runbooks/vault-human-auth.md`.

- **Project `Vault`** in `MCTL`. It has the same three flags as `Argo CD`
  (`project_role_check`, `has_project_check`, `project_role_assertion`), and
  it is a project of its own so that no other application's tokens carry
  Vault's audience.
- **Roles.**
  - `admins` is held by the same platform admins. Vault maps it to the
    `admin` policy.
  - One role per tenant, held by a tenant user **only if** their Vault entry
    carries `"vault": true`. This works like `"argocd"`: the same users list
    and the same opt-in, and a revoke plans a delete of
    `zitadel_user_grant.vault_tenant["<tenant>/<user>"]`.
- **`groups` claim.** The `argocdGroups` action copies the user's roles on the
  Argo CD **or** the Vault project. Each token still carries only its own
  application's roles, because the grants the action sees are loaded for the
  requesting client's project only (see the comment in `argocd.tf`).
- **Client `vault`.** A web client with a client secret and code flow. Vault
  adds PKCE S256 itself. The same client serves both:
  - the UI, at `https://secrets.mctl.ai/ui/vault/auth/mctl/oidc/callback`
    (the Vault mount path; it was `auth/oidc` before the move, and that
    callback is removed);
  - the CLI, at `http://localhost:8250/oidc/callback`. ZITADEL accepts this
    plain-http loopback redirect for a confidential code-flow client without
    dev mode, matched exactly.

  The client id, the secret and the tenant list (JSON) go into
  `vault-human-auth-iac/vault-oidc-zitadel`.

Verified on a local v4.19.2 with Vault 1.17.2 and the real OpenTofu roots, by
a full code flow through the session API (`/v2/sessions`,
`/v2/oidc/auth_requests/<id>`) and Vault's own `auth_url` and `callback`
endpoints, for both redirects:

- A flagged tenant user gets `identity_policies ["human-tenant-<tenant>"]`. It
  reads its own tenant's paths, and another tenant's path returns 403.
- An admin gets `["admin"]`.
- A tenant user flagged for Argo CD only, or not flagged at all, is refused
  with `Errors.User.GrantRequired` before reaching Vault.
- Vault's authorize URL carries `code_challenge_method=S256`.
- A user holding `t1` on the Argo CD project and `admins` on the Vault project
  gets `groups: ["t1"]` from Argo CD's client and `["admins"]` from Vault's.

### mctl-api audience (mctl-api#434)

`iac/mctl-api.tf` gives mctl-api, a resource server, the audience it enforces
on ZITADEL tokens:

- **Project `MCTL API`**, separate from `MCTL platform`, because ZITADEL puts
  the client id of every application of a project into `aud`. In `platform`,
  every Forgejo token would also be valid at api.mctl.ai.
- **Application `mctl-api`**, API type, private-key JWT with no key issued:
  no credential and no flow of its own. Until a client joins this project, no
  token carries its client id, so the provider is registered in mctl-api but
  idle. A client meant to call mctl-api joins this project with
  `access_token_type = "OIDC_TOKEN_TYPE_JWT"`, because mctl-api cannot
  verify opaque access tokens. Adding one is a reviewed decision of its own.
- **Client `mctl-cli`** (owner decision on mctl-api#434): native, public,
  PKCE, authorization code + refresh token, JWT access tokens, redirects
  `http://127.0.0.1/callback` and `http://localhost/callback`. ZITADEL
  matches loopback redirects of a native app on path and query only, so the
  CLI's ephemeral port needs no entry and `dev_mode` stays off.
- **Who gets a token.** The project sets `has_project_check`: only users of
  `MCTL` and of an organization the project is granted to obtain one.
  `zitadel_project_grant.mctl_api_tenant` grants it, with no role keys, to
  every tenant organization, so tenant users can link (`mctl-api-link`) and
  later sign in to mctl-api through ZITADEL (#1500). ZITADEL accepts a grant
  to the user's organization alone; no user grant is needed while
  `project_role_check` stays off. Any other organization of the instance is
  refused. A token is authentication only: mctl-api resolves it to the
  linked principal, or to a new principal with no tenant or admin access.
- **Client `mctl-api-link`** (mctl-api#435, owner decision B): confidential
  web app, client secret plus PKCE, redirect
  `https://api.mctl.ai/identity/link/zitadel/callback` only. mctl-api signs a
  person in with it right after GitHub to link that ZITADEL identity to the
  principal they already have; it reads the ID token only. Its id and secret
  go into the same Secret as `ZITADEL_LINK_CLIENT_ID` /
  `ZITADEL_LINK_CLIENT_SECRET` (chart value `zitadelLinkSecret`).
- **Client `mctl-api-oauth`** (mctl-api#467): confidential web app, client
  secret (HTTP Basic) plus PKCE, redirect
  `https://api.mctl.ai/oauth/zitadel/callback` only, opaque access token,
  `preferred_username` in the ID token. It is the ZITADEL upstream of
  `/oauth/authorize`, which every MCP connector signs in through: with
  `OAUTH_UPSTREAM=zitadel` or `both`, mctl-api signs a person in here,
  resolves the ZITADEL identity to the principal it is linked to, and issues
  its own code for that principal's GitHub login, with the same groups as a
  GitHub sign-in. A person who is not linked is sent to the link flow; no
  principal is created. Its id and secret go into the same Secret as
  `OAUTH_ZITADEL_CLIENT_ID` / `OAUTH_ZITADEL_CLIENT_SECRET` (chart value
  `oauthZitadelSecret`). Nothing reads them while `OAUTH_UPSTREAM` is
  `github`, the default; `zitadel` and `both` refuse to start without them.
  It is separate from `mctl-api-link` so that neither flow accepts the
  other's codes and either secret can be rotated alone. Rollback of the
  upstream: set `OAUTH_UPSTREAM` back to `github` (or remove it) in
  `bootstrap/templates/mctl-platform/mctl-api.yaml`.
- **Output.** The Job writes the complete `MCTL_OIDC_PROVIDERS` JSON (name
  `zitadel`, issuer `https://auth.mctl.ai`, audience = that client id) into
  `mctl-api/mctl-api-oidc-zitadel`, plus `MCTL_CLI_ZITADEL_CLIENT_ID`, which
  mctl-api does not read: it is where the CLI's default client id comes from
  (the provider marks every client id sensitive). The mctl-api chart reads it through
  `oidcProvidersSecret`, optionally. Rollback: drop `oidcProvidersSecret`
  from `bootstrap/templates/mctl-platform/mctl-api.yaml`. The Secret can
  stay as it is.

### Cloudflare Access sign-in (#1500 step 3)

`iac/cloudflare-access.tf` declares the client Cloudflare Access uses when
ZITADEL is offered as an Access identity provider:

- **Project `Cloudflare Access`** in organization `MCTL`, with
  `project_role_check` and `has_project_check`. Role `access` is held by the
  users in `cloudflare_access_users`, which is the platform admins (the
  holders of the Argo CD `admins` group); anyone else is refused with `Errors.User.GrantRequired` before Access sees them.
  Access policies still decide per application on top of that.
- **Client `cloudflare-access`**: web, `OIDC_AUTH_METHOD_TYPE_NONE`, PKCE
  (S256), redirect `https://mbank.cloudflareaccess.com/cdn-cgi/access/callback`.
  No secret exists, so none has to reach `infrastructure/cloudflare/account`.
  Verified on a local v4.19.2: a token request without a valid
  `code_verifier` is refused, and any client secret sent is ignored.
- **Client id.** The only value Cloudflare needs. The Job writes it into
  `zitadel/cloudflare-access-oidc` (key `clientID`); copy it into the
  `zitadel_access_client_id` variable of the Cloudflare account root. It is
  not a secret. The project and the application carry `prevent_destroy`,
  because a recreate changes the id and breaks the Access login until the
  copy is updated.

### GitHub login claim (#1500 phase 1)

`iac/github-login.tf` gives the applications that still identify people by
GitHub login (the portal and its OIDC provider) that login, as declared by
an admin. Its first client is the portal's OIDC provider (see "Portal
sign-in" below).

- **Source.** Optional field `github_login` in a user's Vault entry,
  `secret/platform/zitadel/users/<tenant>` or `secret/platform/zitadel/admins`:

  ```sh
  vault kv patch secret/platform/zitadel/users/<tenant> \
    <user_name>='{"email": "...", "first_name": "...", "last_name": "...", "github_login": "<login>"}'
  ```

  `kv patch` replaces the whole field, so the JSON must carry the user's
  other attributes too. The value must be a GitHub login: 1-39 letters,
  digits and single inner hyphens. Anything else, including `null` or an
  empty string, fails variable validation and stops the run; leave the field
  out instead. The same login twice (ignoring case), across all tenants and
  the admins, fails the plan. Never derive it from the e-mail: it is the
  admin's statement that this ZITADEL user is that GitHub account.
- **Storage.** User metadata `github_login` on the user, its value the login
  as a JSON string, marked sensitive in the plan.
- **Claim.** The Actions v1 action `mctlGithubLogin`, in every organization's
  `PRE_USERINFO_CREATION` trigger next to `argocdGroups`, sets
  `mctl:github_login` only when the client is in
  `local.github_login_clients` (the portal's clients, by reference in
  `portal.tf`, plus the variable `github_login_client_ids`, empty by
  default) and the user is one whose login this root manages (their IDs are in the script). It checks the value again and
  leaves the claim out if it is not a login. It may fail
  (`allowed_to_fail`), which leaves the claim out: a consumer must treat a
  missing claim as "not mapped" and refuse, never fall back to the e-mail.
  The claim is in userinfo, and in the ID token for a client with
  `id_token_userinfo_assertion`.
- **Who can write the metadata.** Not the user: on v4.19.2 the auth API has
  only `ListMyMetadata` and `GetMyMetadata`, and user v2 `SetUserMetadata`
  requires `user.write` with self-management off
  (`internal/api/grpc/user/v2/metadata.go`). Holders of `user.write` on the
  user's organization can (IAM owners; no organization members are declared
  here), and so can the organization's Actions, all declared here. Because
  the action trusts only the users listed in it, a key set on any other user
  is ignored, and a value changed out of band on a listed user is put back by
  the next run of the hourly CronJob.
- **Removing** a user's `github_login` plans a delete of
  `zitadel_user_metadata.github_login_tenant["<tenant>/<user_name>"]`
  (`github_login_admin["<key>"]` for an admin), which needs that address in
  `allowedDeletes`. Changing it is an in-place update.

### Portal sign-in (#1500 phase 3)

`iac/portal.tf` lets the portal (app.mctl.ai) sign people in through ZITADEL
instead of GitHub (mctlhq/mctl-portal#150). The portal keeps identifying a
person by GitHub login, which it reads from `mctl:github_login`; a ZITADEL
user without the claim is refused there, never matched by e-mail.

- **Project `MCTL Portal`**, owned by MCTL, `has_project_check` on, no
  roles. One `zitadel_project_grant.portal_tenant` per tenant organization,
  without role keys, is what lets a tenant's users obtain a token; removing a
  tenant plans a destroy of its grant, which needs the address in
  `allowedDeletes`.
- **Client `portal-oidc-provider`**: the upstream of the portal's OIDC
  provider (`plugins/oidc-provider-backend`). Confidential web app, client
  secret plus PKCE, authorization code only, the single redirect
  `https://app.mctl.ai/api/oidc-provider/zitadel/callback`, opaque access
  token, `id_token_userinfo_assertion` on so the claim reaches the ID token.
- **Secret.** The Job writes `OIDC_ZITADEL_CLIENT_ID` and
  `OIDC_ZITADEL_CLIENT_SECRET` into `backstage/backstage-oidc-zitadel`,
  which the `mctl-portal-oidc-zitadel` Application pre-creates empty
  (`infra-components/mctl-platform/mctl-portal/oidc-zitadel.yaml`).
- **Switch.** Creating the client changes nothing in the portal: it signs
  people in at GitHub until its `oidcProvider.upstream` is set to `both` or
  `zitadel`, a separate change in
  `bootstrap/templates/mctl-platform/mctl-portal.yaml` that also has to
  reference the Secret. Setting it back to `github` is the rollback.

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

### ERPact copy sign-in (#1501)

`iac/erpact.tf` lets the Frappe sites of the ERPact copy (tenant `erpact`,
the copy only) sign their users in through ZITADEL:

- **Project `ERPact`** owned by organization `erpact`, with
  `has_project_check` and one role, `frappe`, granted to the MCTL
  organization (project grant) for platform admins: only users of `erpact`
  and of MCTL get a token, and the path confers no Argo CD, mctl-api or
  tenant-admin rights. Every `erpact` user holds `frappe`; an admin holds it
  only with a `frappe` field in `secret/platform/zitadel/admins`. The role
  gates sign-in once `project_role_check` is on, a separate change made
  after the grants exist.
- **Admins sign in with a second key.** The `mctl` key's
  `urn:zitadel:iam:org:id:<erpact>` scope makes ZITADEL refuse any user of
  another organization, grant or not, so admins use the Social Login Key
  `mctl_admin` (provider name "MCTL Admin", button "Login with MCTL Admin"),
  scoped to the MCTL organization
  (`admin_org_id` in `erpact/erpact-oidc-zitadel`; a second redirect URI per
  site, `.../custom/mctl_admin`). Their Frappe user is the one under the MCTL
  account's e-mail.
- **Application `erpact-frappe`**: web, `client_secret_post` (what Frappe's
  rauth client sends), opaque access token read at userinfo; one redirect URI
  per site, `https://<site>/api/method/frappe.integrations.oauth2_logins.custom/mctl`.
  The Job writes `client_id`, `client_secret` and `org_id` into
  `erpact/erpact-oidc-zitadel` (`infra-components/erpact/oidc-zitadel.yaml`).
- **Verified e-mail only.** Frappe matches users by the `email` claim alone,
  without `email_verified` and without the stored `sub`. The action
  `erpactVerifiedEmail` (`PRE_USERINFO_CREATION`, in the same trigger as
  `argocdGroups`, not allowed to fail, so it aborts userinfo wherever it runs
  in the trigger) refuses userinfo for this client
  unless the user's e-mail is verified. It returns at once for every other
  client. It is declared in both `erpact` and MCTL: an action only runs for
  users of its own organization.
- **Frappe side** (git.mctl.ai/erpact/mctl-apps, the restore Jobs' `sso`
  step): Social Login Key `mctl` per site, sign-up of unknown users disabled
  (v15 `sign_ups = Deny`; v14 Website Settings `disable_signup`), users
  matched by e-mail to the users each site already has.
- **Users the sites must have.** The copy's databases come from production,
  which has no MCTL people, so such a user would get the 403. A user's Vault
  entry (`secret/platform/zitadel/users/erpact`) may carry
  `"frappe": {"sites": ["erpact-control.mctl.ai"], "roles": ["System Manager"]}`.
  The Job writes every such user, and only those, into
  `erpact/erpact-frappe-users` (`users.json`: `{version, users: [{email,
  first_name, last_name, sites, roles}]}`). The restore Jobs and the users
  CronJob of mctl-apps then create the User (named by e-mail, enabled,
  System User) or add the missing roles. The manifest grants roles and never
  revokes them. A site outside `local.erpact_frappe_sites`, an empty or
  malformed `sites`/`roles`, or a `frappe` field on another tenant's user
  fails the run before anything is written.

Not yet verified with a real sign-in. The owner's first sign-in on the copy
checks it both ways before anyone else is pointed at it:

1. A verified `erpact` user signs in on one site and lands on `/app` as their
   existing Frappe user.
2. An `erpact` user whose e-mail is not verified is refused at the userinfo
   step (Frappe shows an error; nobody is signed in).
3. A user of `MCTL` on the `mctl` key is refused by ZITADEL ("User is no
   member of the required organization"), grant or not.
4. A platform admin with a `frappe` field signs in on the `mctl_admin` key
   and lands on `/app` as the Frappe user of their MCTL e-mail.
5. A user of `MCTL` without the `frappe` grant, on the `mctl_admin` key: until
   `project_role_check` is on, ZITADEL issues the token and Frappe refuses
   (no such user, sign-up disabled); once it is on, ZITADEL refuses
   (`Errors.User.GrantRequired`).
6. An `erpact` user with no matching Frappe user gets Frappe's 403 "Signup is
   disabled".

## Known risk: same site as tenant workloads

`auth.mctl.ai` shares the registrable domain `mctl.ai` with tenant
applications (`<tenant>-<service>.mctl.ai` and bare names such as
`seerrsense.mctl.ai`), which run code the platform does not control. For a
browser that makes them the same site:

- a tenant page can set a cookie with `Domain=.mctl.ai` that the browser then
  sends to `auth.mctl.ai` (cookie tossing), and
- `SameSite` cookie attributes do not separate them, because a request from a
  tenant app to the IdP is same-site.

Owner decision 2026-10-04 (#1504, left open as the tracked risk): accepted,
tenant applications stay on `mctl.ai`, and tenant sign-in (#1501) proceeds;
platform session cookies get hardened against tossing instead (#1560).
Originally accepted for phase 1, while nothing signed in through ZITADEL. Two
follow-ups in the unified-identity epic close it; since the decision above they
are tracked follow-ups, not blockers:

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
