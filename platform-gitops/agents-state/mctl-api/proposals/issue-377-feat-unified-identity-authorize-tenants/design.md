# Design: issue-377-feat-unified-identity-authorize-tenants

Revision 2. It applies the owner decisions recorded in requirements.md
(Q1-Q5 and the rollout clarification). Facts below were read from mctl-api
`origin/main` `f3d114e`, mctl-gitops `origin/main` and mctl-portal
`origin/main` on 2026-10-12.

## Current state

### Membership and admin are login-keyed

- `platform-gitops/tenants/<t>/values.yaml` holds `tenant.members[]` as
  `{userId, role}`, and multi-team tenants also hold
  `tenant.teams[].members[]` with the same shape. Six tenants exist:
  `admins`, `commerce-proof`, `erpact`, `karabu`, `labs`, `mctl`.
- `gitops.Reader.GetTenantsForUser(login)` / `TryGetTenantsForUser` return the
  namespaces for a login via `Tenant.UserNamespaces` (case-insensitive
  `userId` match; team membership, then tenant-level fallback).
  `Reader.MemberRoles(namespace, login)` returns the written roles, and
  keeps "could not read" apart from "not a member".
- `ADMIN_USERS` (`cmd/api/main.go`) is a comma-separated list of GitHub
  logins, checked by `GitHubValidator.IsAdmin(login)`.
- Roles are `owner > developer > viewer` (`operations.Role`); `RoleAdmin` is
  platform admin only.

### Decisions read group strings and the login

- `User.IsAdmin()` (`internal/auth/oidc.go`) is "`admins` is in
  `User.Groups`". `HasTenantAccess(t)` is admin or `t` in `Groups`.
- `checkTenantRole` (`internal/api/tenant_role.go`) needs
  `user.GitHubLogin()` and refuses a caller without a GitHub-proven login,
  then reads `MemberRoles(tenant, login)`.
- The principal (`prn_`) is resolved per request and attached
  (`auth.AttachPrincipal`), but it is record-only. The only places it already
  decides something are the delegation cross-check and the commerce ledger
  keys.

### How groups are built today, per path

| Path | Tenants | Admin |
|---|---|---|
| GitHub PAT (`legacyGroupSource` -> `resolveGroups`, `oidc.go`) | gitops tenants for the login, **verbatim** | `ADMIN_USERS` |
| OAuth / local JWT (`OAuthServer.resolveGroups` -> `withAdmins`) | gitops tenants, `admins` stripped by `tenantsOnly` | `ADMIN_USERS`, recomputed each read |
| ZITADEL (`OAUTH_UPSTREAM=zitadel`) | via the linked GitHub login, then as OAuth | as OAuth |
| Surface relay / agent delegation | gitops tenants for the `github:<login>` subject, `admins` dropped | never |
| Federated OIDC (`MCTL_OIDC_PROVIDERS`) | provider groups withheld unless `grant_groups` | never (the trusted Dex slot excepted; Dex is off) |

### The `admins` collision (fixed by PR-0)

The tenant `admins` exists in GitOps and has one member today. On the GitHub
PAT row of the table, its name reaches `User.Groups` verbatim, so
`IsAdmin()` is true for **any** member of that tenant whether or not they
are in `ADMIN_USERS`. The OAuth row strips it. No test pins either
behaviour. Today the only member is also in `ADMIN_USERS`, so nobody is
escalated yet, but the next member added to that tenant would be. PR-0
closes it without waiting for this proposal (tasks.md).

### Second authority: the portal

`mctl-portal`'s `tenant-management` plugin keeps a `tenant_members` table
keyed by login (seeded add-only from GitOps, plus portal invites), and the
portal's `oidc-provider-backend` issues groups and roles from it for its
forward-auth clients. GitOps removals do not propagate. mctl-api does not
accept portal-issued tokens (it federates only `zitadel`), so this does not
bypass mctl-api authorization. It is handled in its own issue (Q4).

## Target schema (Q1)

```yaml
tenant:
  name: mctl
  members:
    - principalId: prn_01JABCDEFGHJKMNPQRSTVWXYZ0   # authorization key
      role: owner
      userId: mashkovd                               # optional, display only
    - principalId: prn_01JZZZZZZZZZZZZZZZZZZZZZZZZ   # ZITADEL-only human
      role: developer                                # no userId at all
  teams:
    - name: web
      members:
        - principalId: prn_01J...
          role: developer
```

Parser rules (`internal/gitops/reader.go`):

- `principalId` must match `^prn_[0-9A-HJKMNP-TV-Z]{26}$`. A malformed value,
  or the same `principalId` twice in one member list, makes **that tenant
  unreadable**: membership queries touching it return an error (503
  upstream), never "not a member". The rest of the tenants stay readable.
- An entry with neither `principalId` nor `userId` is unreadable the same way.
- `userId` is optional. In principal mode it is ignored for authorization.
- The ordering and role semantics of teams versus tenant-level membership are
  unchanged; only the key changes.

New reader methods mirror the login ones:
`NamespacesForPrincipal(prn) ([]string, error)`,
`TryNamespacesForPrincipal(prn)`, `MemberRolesForPrincipal(namespace, prn)`.

## Platform admin (Q2)

- `ADMIN_PRINCIPALS`: comma-separated `prn_` ids, validated at boot (a
  malformed entry refuses boot).
- `User` gains an unexported `platformAdmin bool`, set only by
  (a) `ADMIN_PRINCIPALS` matching the request's resolved principal, or
  (b) the static platform service principal (`NewServiceUser`).
  In principal mode `IsAdmin()` reads that field and ignores `Groups`
  entirely, so no group string, tenant name or provider claim can make an
  admin. This removes the class that PR-0 patches; after the switch the
  tenant `admins` is an ordinary tenant whose members get ordinary tenant
  roles on it.
- In principal mode with an empty `ADMIN_PRINCIPALS`, boot is refused: a
  mode switch must not silently remove every human admin.
- `ADMIN_USERS` is ignored in principal mode, with a startup warning while it
  is still set. It is deleted in PR-C.

## Authorization mode

`TENANT_AUTHZ_MODE = legacy | shadow | principal`, default `legacy`. Any
other value refuses boot.

- **legacy**: today's behaviour (with PR-0 applied).
- **shadow**: decide exactly as legacy; in addition compute the principal
  decision for the same request and compare. Nothing the principal path
  computes is used to authorize.
- **principal**: the principal path decides; the legacy path is not
  consulted at all. There is no login fallback.

Rollback is setting the mode back in the same mctl-api values file. No data
moves in either direction, so rollback creates no second authority.

### Principal-mode resolution

1. Authentication yields a verified provider identity
   `(provider, issuer, subject)`, exactly as today.
2. The principal is resolved through `external_identities` (#373/#435). Local
   OAuth JWTs carry a `pid` claim (added in PR-B) holding the `prn_` minted
   at sign-in, so a local token never re-derives its principal from a login.
   A local JWT without `pid` is refused with 401 in principal mode (re-auth).
3. Outcomes:
   - resolved, principal active -> continue;
   - principal disabled / identity revoked -> refused as today (401/403);
   - resolution **failed** (store error, timeout) -> **503** for any request
     that needs authorization; never "no tenants";
   - identity has no principal linked -> it gets a fresh principal of its own
     (existing #373 behaviour) with no membership, so it is authenticated and
     authorized for nothing. An email or display-name match never links.
4. `User.Groups` = `NamespacesForPrincipal(prn)`. Provider groups are never
   read. `checkTenantRole` uses `MemberRolesForPrincipal(tenant, prn)` and no
   longer needs `GitHubLogin()`.
5. Surface relay and agent delegation resolve the subject's principal from
   the link/grant and use the same principal lookup. A subject whose
   principal cannot be resolved is refused (the delegation path already fails
   closed on `AttachPrincipal`; the relay is aligned to it).
6. Service and agent callers (#376) are unchanged: the static service
   principal keeps `platformAdmin`; agent principals are never admin.

## Shadow comparison and metrics

Computed in shadow mode for every authenticated human request that reaches
an authorization decision:

- `tenant_authz_shadow_total{result="match|diff|unresolved"}`
- `tenant_authz_shadow_diff_total{kind="tenant_only_legacy|tenant_only_principal|role_mismatch|admin_mismatch"}`
- `tenant_authz_principal_unresolved_total{reason="no_pid|store_error|timeout|disabled|revoked"}`
- `tenant_member_entry_unkeyed` (gauge): GitOps member entries with no
  `principalId`, per tenant.

An unresolved principal is counted as `unresolved`, never as a `match` and
never as a `diff`: a decision that could not be computed is not evidence
either way. Each diff also logs the request path, the principal id, the
legacy login and the two decisions, so every diff can be explained.

**Switch criterion.** At least 7 consecutive days with
`tenant_authz_shadow_diff_total` = 0, `unresolved` = 0 for human callers,
`tenant_member_entry_unkeyed` = 0, and traffic through each sign-in path
(GitHub PAT, ZITADEL MCP OAuth, ZITADEL bearer) observed at least once in the
window. A window in which a path saw no traffic does not count for that path.

## Backfill

A read-only plan command (`mctl-api tenant-members plan`, or an admin-only
MCP tool) reads every GitOps member entry, resolves its `userId` through the
live GitHub identity (numeric GitHub id, never the login string alone) to an
`external_identities` row, and prints:

- the proposed `principalId` for each resolvable entry;
- an **unresolved** list (no linked identity, ambiguous, disabled), which is
  a blocker, not a skip.

The output becomes a human-reviewed mctl-gitops PR that adds `principalId`
to every entry. `wft-create-tenant` starts writing `principalId` for the
creating owner in PR-B. Once every entry is keyed, a gitops CI check refuses
a member entry without `principalId`.

## ZITADEL-only proof (Q5)

An integration test and a live check, both required before the switch:

- test: a principal with exactly one external identity
  `(zitadel, <issuer>, <sub>)`, no GitHub identity, and a GitOps entry
  `{principalId, role: developer}` with no `userId` gets `HasTenantAccess`
  and `developer` on that tenant in principal mode; removing the entry
  removes both; a second ZITADEL identity with the same email and no link
  gets nothing.
- live: one ZITADEL-only test principal added to a test tenant
  (`commerce-proof`) by principal id, exercised through MCP OAuth, after the
  switch; plus the unlinked negative.

## Minimal approvals dependency (Q3)

Generic ownership stays out of scope. The one comparison that shared tenants
need early is the action-approval self-decision rule
(`workitems.ErrApprovalSelfDecision`, `RequestedBy` compared with the
decider, `internal/api/handlers_action_approvals.go`). It compares actor
strings, so a human reaching mctl-api through two providers is two different
deciders. The minimal change is: when both the request and the decider carry
a principal id, compare principal ids; otherwise keep today's rule. It is a
separate small PR, opened only if mctl-api#489 / mctl-agents#631 actually
need it before the generic migration.

## Rollout

1. **PR-0** (independent, now): `admins` tenant-name fix. See tasks.md.
2. **PR-A**: parser (`principalId`, optional `userId`), principal reader
   methods, `TENANT_AUTHZ_MODE` with `legacy|shadow`, shadow comparison,
   metrics, backfill plan command. Default `legacy`; no behaviour change.
3. **gitops backfill PR**: `principalId` on every member entry, from the plan
   output; unresolved list empty.
4. **Enable shadow** in production (values change).
5. **PR-B** (may merge before the window ends, behind the flag): `principal`
   mode, `platformAdmin` field and `ADMIN_PRINCIPALS`, JWT `pid`, relay and
   delegation by principal, `checkTenantRole` by principal,
   `wft-create-tenant` writes `principalId`, gitops CI check for unkeyed
   entries.
6. **Switch** to `principal` once the switch criterion holds, with
   `ADMIN_PRINCIPALS` set in the same values change; then the live checks
   (GitHub PAT, ZITADEL MCP OAuth, ZITADEL bearer, ZITADEL-only principal,
   unlinked negative).
7. **PR-C** after 14 days in principal mode with no rollback: delete the
   legacy path, `ADMIN_USERS`, `TENANT_AUTHZ_MODE=legacy|shadow`, and the
   `userId`-keyed reader methods. `userId` stays as optional display data.

## Follow-up issues to open

- Per-object ownership migration from `github:<login>` to principal ids
  (work items, human input, surface links, idempotency keys).
- Portal `tenant_members` as a non-authoritative projection keyed by
  principal id, with deletion reconciliation; portal invites become a
  governed GitOps membership change.
- Reserve the tenant name `admins` for new tenants? Not proposed: the tenant
  exists and admins re-run `create-tenant` on it to reprovision, which a
  reservation would block. After PR-B the name carries no meaning anyway.
