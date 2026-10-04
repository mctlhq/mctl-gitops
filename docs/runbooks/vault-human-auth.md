# Vault human sign-in (secrets.mctl.ai via auth.mctl.ai)

Humans sign in to Vault through ZITADEL on the `auth/oidc` mount, in the UI or
with `vault login -method=oidc`. What they may read comes from the `groups`
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
vault-human-auth-iac Job ── Vault: auth/oidc, role `zitadel`,
                           groups human-admins / human-tenant-<tenant>,
                           policies human-tenant-<tenant>
```

| `groups` value | Vault group | Policy |
| --- | --- | --- |
| `admins` | `human-admins` | `admin` (existing, hand-written, not managed here) |
| `<tenant>` | `human-tenant-<tenant>` | `human-tenant-<tenant>`: `read` on `secret/data/teams/<tenant>/*`, `read`+`list` on `secret/metadata/teams/<tenant>/*` |
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
- **Tenant access is read-only.** Tenant secrets are written through the portal and the platform workflows, with their own identities.
- **Token lifetime.** Human tokens live 1h and cannot be renewed past that (`token_max_ttl` 1h); sign in again. Group membership is re-evaluated at every login, so removing the role or the flag takes effect at the user's next login.

Verified before rollout on a local ZITADEL v4.19.2 and Vault 1.17.2, running
these roots with the bootstrap policy as the Job's only credential. Full code
flows through Vault's `auth_url` and `callback`, for both redirects, gave:

| User | Result |
| --- | --- |
| Opted-in tenant user | `identity_policies ["human-tenant-<tenant>"]`, TTL 3600. Reads its own tenant; another tenant's path and any write return 403. |
| Admin | `["admin"]` |
| Unflagged user, or flagged for Argo CD only | Refused by ZITADEL (`Errors.User.GrantRequired`) |

The authorize request carried PKCE S256. Details are in docs/runbooks/zitadel.md, "Vault sign-in".

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
`secret/platform/zitadel/admins` (the owner's is `dmitrii`), using its login
name or e-mail address. It holds `admins` on the Vault project
(`zitadel_user_grant.vault_admin["dmitrii"]`). Use `mctl-admin` only as
break-glass, when the personal account cannot sign in.

1. **CLI login.**

   ```bash
   export VAULT_ADDR=https://secrets.mctl.ai
   vault login -method=oidc
   ```

   A browser opens on `auth.mctl.ai`. After sign-in, the CLI prints
   `Success! You are now authenticated.`
2. **CLI token.** Run `vault token lookup`. Expect:
   - `policies [default]` and `identity_policies [admin]`
   - `ttl` of at most 1h
   - `meta` with `role=zitadel` and your `username`
3. **UI login.** Open `https://secrets.mctl.ai/ui/`, choose method **OIDC**,
   leave the role empty and sign in. You land on the dashboard and can open
   `secret/`.
4. **Tenant isolation, live.** Use a tenant user, for example your own user in
   a tenant organization:
   - Set `"vault": true` in that user's entry at
     `secret/platform/zitadel/users/<tenant>`.
   - Wait for the next hourly zitadel-iac run.
   - Sign in with that account (`vault login -method=oidc` in a fresh shell,
     or a private browser window).
   - Then run:

   ```bash
   vault token lookup        # identity_policies [human-tenant-<tenant>]
   vault token capabilities secret/data/teams/<tenant>/x        # read
   vault token capabilities secret/data/teams/<other-tenant>/x  # deny
   vault token capabilities secret/metadata/teams/              # deny
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
  and the next vault-human-auth-iac run updates `auth/oidc/config`.
- **Drift.** A change made by hand to the mount, the role, a `human-*` group or
  a `human-tenant-*` policy shows up as an update in the next hourly plan, and
  the run reverts it.

## Break-glass

When ZITADEL is down, OIDC logins fail. Already-issued tokens keep working
until they expire.

The admin paths that do not depend on ZITADEL are unchanged:
- the `github` auth method (`auth/github`, a user map). It is the current
  human fallback and stays as it is: retiring it is a separate owner
  decision, made once OIDC sign-in has been in use for a while;
- an existing admin token;
- a root token generated with the unseal keys (`vault operator generate-root`).

The Job never disables a mount: its policy has no `delete` on `sys/auth/oidc`.
To turn human OIDC sign-in off by hand, an admin runs
`vault auth disable oidc`. That removes the group aliases with it. The next
Job run would re-create everything, so first suspend the CronJob and set
`allowedActions: "no-op read"`.
