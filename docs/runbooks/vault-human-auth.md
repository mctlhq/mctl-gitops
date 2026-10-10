# Vault human sign-in (secrets.mctl.ai via auth.mctl.ai)

Humans sign in to Vault through ZITADEL on the `auth/mctl` mount (an OIDC auth
method), in the UI (tab **mctl**) or with `vault login -method=oidc -path=mctl`. What they may read comes from the `groups`
claim, which carries the user's roles on ZITADEL's "Vault" project, and nothing
else.

| Piece | Where |
| --- | --- |
| ZITADEL project, roles, grants, OIDC client | `platform-gitops/helm-charts/zitadel-iac/iac/vault.tf` |
| `groups` claim (shared with Argo CD) | `platform-gitops/helm-charts/zitadel-iac/iac/argocd.tf`, action `argocdGroups` |
| Vault mount, role, groups, tenant policies | `platform-gitops/helm-charts/vault-human-auth-iac/iac/` |
| Job, CronJob, guard | `platform-gitops/helm-charts/vault-human-auth-iac/` |
| Argo CD Application, namespace `vault-human-auth-iac` | `platform-gitops/bootstrap/templates/core-infra/vault-human-auth-iac.yaml` |
| Hand-off Secret, NetworkPolicies, pull secret | `platform-gitops/infra-components/identity/vault-human-auth-iac/` |
| The Job's own Vault identity (applied once by hand) | `infrastructure/k3s-preview/cluster-bootstrap/vault-config/vault-policy-vault-human-auth-iac.hcl`, README "vault-human-auth-iac" |
| Image | `platform-gitops/images/vault-iac/Dockerfile` |
| Audit log (the same Job enables the `stdout` audit device) | `iac/audit.tf`; queries and failure modes in [vault-audit.md](vault-audit.md) |

## How it fits together

```
Vault secret/platform/zitadel/users/<tenant>   (who, which tenant, "vault": true)
        |
        v
zitadel-iac Job ── ZITADEL: project "Vault", roles admins + <tenant>, grants,
        |          app `vault` (web, code + PKCE)
        v
Secret vault-human-auth-iac/vault-oidc-zitadel   (client_id, client_secret, tenants)
        |
        v
vault-human-auth-iac Job ── Vault: auth/mctl, role `zitadel`,
                           groups human-admins / human-tenant-<tenant>,
                           policies human-tenant-<tenant>
```

| `groups` value | Vault group | Policy |
| --- | --- | --- |
| `admins` | `human-admins` | `admin` (existing, hand-written, not managed here) |
| `<tenant>` | `human-tenant-<tenant>` | `human-tenant-<tenant>`: read and write (create, update, patch, soft delete, undelete, list) on `secret/data/teams/<tenant>/*`, `read`+`list` on its metadata; `list` only on exactly `secret/metadata/` and `secret/metadata/teams/` (browse); `<service>/database` read only; no destroy, no metadata write or delete |
| anything else, or none | none | `default` only |

- **Who is an admin.** The platform admins in `zitadel-iac/iac/admins.tf`
  (`platform_admin_user_ids`):
  - the personal MCTL accounts listed in Vault `secret/platform/zitadel/admins`;
  - the break-glass account `mctl-admin`.

  Argo CD, Vault, Argo Workflows, Grafana and Cloudflare Access share that one
  list. Vault's side does not care how many admins there are: anyone whose
  `groups` claim from the `vault` client carries `admins` lands in
  `human-admins`.
- **Who is a tenant user.** A user listed in `secret/platform/zitadel/users/<tenant>` whose entry carries `"vault": true`. Without the flag, ZITADEL refuses to issue a token for Vault (`project_role_check`), so the login fails before Vault sees it.
- **Tenant access is read and write on the tenant's own prefix** (owner
  decision 2026-10-04). A tenant user can create, update, patch, soft-delete
  and undelete secrets under `secret/teams/<tenant>/`. They cannot destroy a
  version, or write or delete metadata, so every deleted version stays
  recoverable and only platform admins can purge.
- **`<service>/database` stays read only for tenants.** `wft-provision-database`
  generates it and the `cnpg-db-creds` store syncs it into the shared-pg role,
  so a human edit would break the database login.
- **Tenants browse down to their folder in the UI.** In the UI, a tenant user
  opens `secret/`, then `teams/`, then `<tenant>/`. To make that work, the
  policy grants `list`, and nothing else, on exactly `secret/metadata/` and
  `secret/metadata/teams/`, with no glob. Those two listings show the
  top-level key names and the folder names under `teams/`, which are the
  tenant names in `platform-gitops/tenants/` (public). Opening another
  tenant's folder, or anything under `platform/`, is still 403. Before this,
  `secret/` looked empty to a tenant, who had to type `teams/<tenant>/` into
  "View secret" by hand. The CLI equivalent is
  `vault kv list secret/teams/<tenant>/`.
- **Token lifetime.** Human tokens live 1h and cannot be renewed past that (`token_max_ttl` 1h); sign in again. Group membership is re-evaluated at every login, so removing the role or the flag takes effect at the user's next login.

Verified before rollout on a local ZITADEL v4.19.2 and Vault 1.17.2, running
these roots with the bootstrap policy as the Job's only credential. Full code
flows through Vault's `auth_url` and `callback`, for both redirects, gave:

| User | Result |
| --- | --- |
| Opted-in tenant user | `identity_policies ["human-tenant-<tenant>"]`, TTL 3600. Reads its own tenant; another tenant's path returns 403. (Read-only policy at the time; write was added later and proven separately, see below.) |
| Admin | `["admin"]` |
| Unflagged user, or flagged for Argo CD only | Refused by ZITADEL (`Errors.User.GrantRequired`) |

The authorize request carried PKCE S256. Details are in docs/runbooks/zitadel.md, "Vault sign-in".

Tenant write access was proven on a local Vault 1.17.2 with this root applied
by the bootstrap policy, using a token from a simulated `groups: ["erpact"]`
login:

| Action | Result |
| --- | --- |
| `put`, `patch`, new key, `delete`, `undelete`, `delete -versions` on `secret/teams/erpact/...` | allowed |
| `destroy`, `metadata delete`, `metadata put` | 403 |
| `get` on `erpact/<svc>/database` | allowed |
| `put`, `patch`, `delete` on `erpact/<svc>/database` | 403 |
| any `labs` path, listing `secret/teams` (before the browse rules below), `secret/platform/...`, `secret/teams/erpactx/...` | 403 |

The test was also run against two broken policies. With the database rules
removed, the tenant could overwrite `database`. With the old read-only policy,
`put` returned 403. The next Job run reverted the edited policy (`update`).

The browse rules were proven the same way, on a local Vault 1.17.2. The token
held the rendered `human-tenant-erpact` policy, with a second tenant `other`
and a `platform/` tree seeded:

| Action | Result |
| --- | --- |
| list `secret/metadata/`, `secret/metadata/teams/`, `secret/metadata/teams/erpact/` | allowed |
| list `secret/metadata/teams/other/` and `.../other/<svc>/`, list `secret/metadata/platform/` | 403 |
| read `secret/metadata/teams` (not list), read data or metadata under `other/`, write at `teams/x` or a top-level key, delete `secret/metadata/teams` | 403 |
| the tenant's own read and write, and the `database` and destroy rules | as above |

The test was also run against two broken policies. Without the two browse
rules, listing `secret/metadata/` and `secret/metadata/teams/` returned 403,
which was the reported bug. With `secret/metadata/teams/*` in place of the
exact path, the tenant could list `other/` and its subfolders.

## Rollout order

1. The owner applies the Job's Vault policy and Kubernetes auth role once
   (vault-config README, "vault-human-auth-iac").
2. Merge the namespace PR (Secret, Role), then the zitadel-iac PR: the next
   zitadel-iac run fills `vault-oidc-zitadel`.
3. Merge the Job with `allowedActions: "no-op read"`. Its first run must log in,
   read the Secret, plan the mount, role, groups and policies, print the plan
   and refuse it:
   `kubectl -n vault-human-auth-iac logs job/vault-human-auth-iac` ends with
   `plan contains 'create' ... refusing to apply`. Check the plan: one
   `vault_jwt_auth_backend.oidc`, one role, `human-admins`, and one group,
   alias and policy per tenant, nothing else.
4. Widen `allowedActions` to `"no-op read create update"` in its own PR
   (update: client rotation and drift repair). The run after the sync applies;
   the next hourly run prints `no changes`.

## First login (owner checklist)

Sign in with your personal MCTL account, the one created from
`secret/platform/zitadel/admins` (the owner's entry is keyed `dmitrii`; its
login name is the entry's `username`, `dmitrii.mashkov`), using that login
name or the e-mail address. It holds `admins` on the Vault project
(`zitadel_user_grant.vault_admin["dmitrii"]`, addressed by the key). Use `mctl-admin` only as
break-glass, when the personal account cannot sign in.

1. **CLI login.**

   ```bash
   export VAULT_ADDR=https://secrets.mctl.ai
   vault login -method=oidc -path=mctl
   ```

   A browser opens on `auth.mctl.ai`. After sign-in, the CLI prints
   `Success! You are now authenticated.`
2. **CLI token.** Run `vault token lookup`. Expect:
   - `policies [default]` and `identity_policies [admin]`
   - `ttl` of at most 1h
   - `meta` with `role=zitadel` and your `username`
3. **UI login.** Open `https://secrets.mctl.ai/ui/`, choose the **mctl** tab,
   leave the role empty and sign in. You land on the dashboard and can open
   `secret/`. A tenant user sees `teams/` there, and inside it every tenant
   folder, but can open only their own.
4. **Tenant isolation, live.** Use a tenant user, for example your own user in
   a tenant organization:
   - Set `"vault": true` in that user's entry at
     `secret/platform/zitadel/users/<tenant>`.
   - Wait for the next hourly zitadel-iac run.
   - Sign in with that account (`vault login -method=oidc -path=mctl` in a fresh shell,
     or a private browser window).
   - Then run:

   ```bash
   vault token lookup        # identity_policies [human-tenant-<tenant>]
   vault token capabilities secret/data/teams/<tenant>/x        # create, delete, list, patch, read, update
   vault token capabilities secret/data/teams/<tenant>/<svc>/database  # read
   vault token capabilities secret/destroy/teams/<tenant>/x     # deny
   vault token capabilities secret/data/teams/<other-tenant>/x  # deny
   vault token capabilities secret/metadata/teams/              # list
   vault token capabilities secret/metadata/teams/<other-tenant>/  # deny
   vault kv get secret/teams/<other-tenant>/<any>               # 403
   ```

   Remove the flag again afterwards if that account should not keep Vault
   access.
5. **Refused when not granted.** Sign in with a ZITADEL user that has no role
   on the Vault project. ZITADEL refuses to issue the token (project role
   check), and no Vault token is created.

## Operations

- **Grant a tenant user.** Add `"vault": true` to their entry at
  `secret/platform/zitadel/users/<tenant>`. zitadel-iac grants the role within
  the hour. Nothing changes in Vault, because the group already exists.
- **Revoke.** Remove the flag. The user's next login gets no token. A token
  already issued lives at most until its TTL, or revoke it at once with
  `vault token revoke -accessor <accessor>`.
- **New tenant.** A new `secret/platform/zitadel/users/<tenant>` makes
  zitadel-iac create the tenant's role and add it to `tenants`. The next
  vault-human-auth-iac run creates `human-tenant-<tenant>`, its policy and its
  alias. These are creates only, so no guard change is needed.
- **Retired tenant.** The next run plans destroys of the tenant's group, alias
  and policy, and the guard refuses them. To apply, list those three addresses
  in `allowedDeletes` in a PR, then empty the list again after it has applied.
- **Rotate the client secret.** Regenerate the client in ZITADEL by replacing
  `zitadel_application_oidc.vault` through zitadel-iac. The Secret updates,
  and the next vault-human-auth-iac run updates `auth/mctl/config`.
- **Drift.** A change made by hand to the mount, the role, a `human-*` group or
  a `human-tenant-*` policy shows up as an update in the next hourly plan, and
  the run reverts it.

## The move from `auth/oidc` to `auth/mctl`

The mount was `auth/oidc` until the owner approved moving it, because the UI
labels the login tab with the mount path. Vault cannot show a different
label in OSS, and the "Other" tab cannot be hidden either: custom login
settings are Enterprise-only. What changed for users:

- **Sign in again once.** The move revokes every token the mount had issued
  (Vault 1.17.2 revokes the mount's leases on a remount). Group memberships
  and policies are unchanged: the accessor is kept, so the same identity
  entity is found on the next login.
- **CLI:** `vault login -method=oidc -path=mctl`. The old
  `vault login -method=oidc` now fails with `403 permission denied` on
  `auth/oidc/oidc/auth_url`, because nothing is mounted there.
- **UI:** the tab reads **mctl**.

The order, each step its own change: (a) zitadel-iac registers the
`/ui/vault/auth/mctl/oidc/callback` redirect next to the old one; (b) the
owner applies the temporary remount grant to the Job's policy
(cluster-bootstrap/vault-config/README.md) and it is diffed byte-identical
against the file; (c) the root sets `path = "mctl"`, with the role listed in
`allowedDeletes`; (d) cleanup drops the old redirect, empties
`allowedDeletes`, removes the remount grant and renames the policy's `oidc`
paths to `mctl` (the owner re-applies the policy file).

**Recovery, if (c) ever applies without the grant** (only before (d)). The Job
destroys the role first and the remount then fails with a 403: the mount stays
at `auth/oidc` with no login role, and later runs refuse to plan. Finish the
move by hand (owner, admin token), after applying the grant:

```bash
vault write sys/remount from=auth/oidc to=auth/mctl
```

The next Job run then creates the role and converges (verified locally).

**Rolling the move back is owner-only.** After (d) the Job has no remount
grant at all, and before it the grant allowed exactly `auth/oidc` to
`auth/mctl`, so the Job is refused the reverse (403). To go back:

1. Suspend the CronJob and set `allowedActions: "no-op read"`, so no run
   plans against a mount that is moving under it.
2. The owner moves the mount by hand with an admin token
   (`vault write sys/remount from=auth/mctl to=auth/oidc`).
3. Revert (c) and (d) in git; the policy then needs the `oidc` paths again,
   re-applied by the owner.
4. Expect a state fix-up before that run plans clean: the provider tracks
   the mount by its path, so `tofu state rm vault_jwt_auth_backend.oidc`
   and an import at `oidc` may be needed (not verified; rehearse it).
5. Resume the CronJob and widen `allowedActions` again once a run re-plans
   clean.

Every human signs in again, as with the move itself. This path is not
rehearsed: plan it on a local Vault first.

## Break-glass

When ZITADEL is down, OIDC logins fail. Already-issued tokens keep working
until they expire.

The admin paths that do not depend on ZITADEL:
- an existing admin token;
- a root token generated with the unseal keys (`vault operator generate-root`,
  a quorum of the Shamir unseal key holders).

The `github` auth method (`auth/github`, a hand-configured user map that was
never in IaC) used to be a third path. It was disabled on 2026-10-10, after
human sign-in had run on ZITADEL for a week (mctlhq/mctl-gitops#1500,
phase 7). Disabling it revoked every token it had issued. Do not re-enable it
as a fallback: a method configured outside this repo is invisible to review.

The Job never disables a mount: its policy has no `delete` on any `sys/auth/` path.
To turn human OIDC sign-in off by hand, an admin runs
`vault auth disable mctl`. That removes the group aliases with it. The next
Job run would re-create everything, so first suspend the CronJob and set
`allowedActions: "no-op read"`.
