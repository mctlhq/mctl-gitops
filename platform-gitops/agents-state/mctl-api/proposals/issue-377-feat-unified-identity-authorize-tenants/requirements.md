# Authorize tenants by canonical principal instead of GitHub login

## Context

mctl-api resolves a canonical principal (`prn_<ulid>`, mctl-api#373) on every
authenticated request, links provider identities to it explicitly (#435) and
authenticates through a provider-agnostic registry (#374). Authorization
does not use any of that. It still runs on GitHub login spelling:

- Tenant membership is `members[].userId` (a GitHub login) in
  `platform-gitops/tenants/*/values.yaml`, read by `gitops.Reader`
  (`GetTenantsForUser`, `MemberRoles`).
- Platform admin is `ADMIN_USERS`, a list of GitHub logins
  (`cmd/api/main.go`).
- Handlers decide on `User.Groups` strings (`HasTenantAccess`, `IsAdmin`) and
  on `checkTenantRole` (`internal/api/tenant_role.go`), which needs
  `GitHubLogin()`.
- The production human path is ZITADEL, then the linked GitHub identity, then
  the login, then the groups for that login. A ZITADEL-only human has no
  login and therefore no tenant at all.

This is revision 2. Revision 1 (the 2026-10-12 audit) ended with five owner
questions. The answers are recorded below and the design follows them.

## Owner decisions (2026-10-12)

**Q1, membership authority: APPROVED.** GitOps stays the tenant membership
authority for #377. Each member entry gains `principalId`, and that field
becomes the authorization key. `userId` becomes legacy/display metadata and
is **not required** in principal mode, because a ZITADEL-only principal may
have no GitHub login. No membership table is added to mctl-api in #377. The
consequence that `prn_` ids become public, because mctl-gitops is public, is
accepted: a `prn_` id is an opaque identifier and grants nothing by itself.

**Q2, platform admin: APPROVED.** Platform admin authority is
`ADMIN_PRINCIPALS`, a list of canonical principal ids, separate from tenant
membership. The tenant named `admins` has no privileged meaning. The
privilege escalation found during the audit (a member of the `admins` tenant
signing in with a GitHub PAT is a platform admin) is fixed now, in an
isolated PR-0 that does not wait for this proposal.

**Q3, per-object ownership: APPROVED, out of scope.** The `github:<login>`
owner strings on work items, human input, surface links and idempotency keys
migrate in a separate follow-up. #377 only identifies the minimal approvals
change that shared-tenant work needs, and ships it as its own dependency if it
really blocks.

**Q4, portal `tenant_members`: APPROVED DIRECTION, separate issue.** The
portal table becomes a non-authoritative projection/cache keyed by principal
id, reconciled in both directions (a GitOps removal deletes the row). Direct
portal membership writes stop being a second authority; a portal invite may
later open a governed GitOps membership change instead. This is tracked as its
own issue and is not part of the #377 implementation, because the portal's
membership does not reach mctl-api authorization (verified: mctl-api
federates only ZITADEL; Dex is off; portal-issued tokens are not accepted).

**Q5, ZITADEL-only humans: APPROVED, in scope.** A principal with no GitHub
identity must receive tenant authorization from a GitOps membership keyed by
its `principalId`. This is a base property of unified identity, not a
Commerce feature, and is proved in #377, not in mctl-agents#631. No Commerce
code is involved.

**Rollout clarification.** PR-B may be implemented and merged behind the mode
flag before the shadow window ends. Only switching production authorization
to `principal` waits for the declared zero-diff, zero-unresolved shadow
window. In principal mode no provider group, login, email, display name or
ZITADEL subject is ever an authorization fallback.

## Invariant after #377

```text
provider credential
    -> authentication / explicit linking
canonical principal prn_...
    -> GitOps tenant membership (principalId, role)
authorization

GitHub login, email, ZITADEL sub, provider groups
  = metadata or authentication inputs, never authorization keys
```

## User stories

- AS a tenant member I WANT the same access whether I sign in through
  ZITADEL or a linked GitHub identity SO THAT my access follows me, not my
  provider.
- AS a human with only a ZITADEL identity I WANT to be added to a tenant by
  principal id SO THAT I do not need a GitHub account to use mctl.
- AS a platform operator I WANT removing a member's entry in GitOps to revoke
  their access through every linked provider SO THAT revocation has one
  place.
- AS a security reviewer I WANT no provider-issued group, login or email to
  be able to grant a tenant or admin SO THAT a renamed or foreign account
  cannot inherit access.
- AS a platform operator I WANT a shadow mode that reports every decision the
  new path would make differently SO THAT the cut-over is a flag flip after a
  measured window, and rollback is the same flip back.

## Acceptance criteria

1. A tenant member signs in through ZITADEL and receives exactly the tenant
   access of their linked GitHub identity (same tenants, same roles).
2. A principal with **only** a ZITADEL identity and a GitOps entry
   `{principalId: prn_X, role: developer}` gets developer on that tenant, with
   no `userId` on the entry and no GitHub identity linked.
3. Renaming the GitHub login of a linked identity does not change access in
   principal mode.
4. An unlinked ZITADEL identity whose email or display name matches a member
   gets nothing: it resolves to its own principal, which has no membership.
5. Deleting the member entry in GitOps revokes access through every linked
   provider on the next reader refresh.
6. No provider group, caller-supplied login or tenant name can grant tenant
   membership or platform admin. A member of the tenant `admins` is not a
   platform admin by that membership (already true after PR-0).
7. Platform admin in principal mode is exactly `ADMIN_PRINCIPALS` plus the
   static platform service principal; `ADMIN_USERS` is ignored and a warning
   is logged if it is still set.
8. A request whose principal cannot be resolved (store unreachable, timeout)
   is refused with 503 in principal mode; it is never authorized by login.
   "Could not resolve" is not "has no membership".
9. In shadow mode every divergence between the legacy and principal decision
   is counted and logged with its kind; an unresolved principal is counted
   separately from a divergence.
10. Mutation-pinned tests: putting a GitHub-login comparison back into the
    principal-mode decision, or letting a tenant named `admins` confer admin,
    makes a named test fail.

## Out of scope

- Per-object ownership (`github:<login>` on work items, human input, surface
  links, idempotency keys): follow-up issue (Q3).
- Portal `tenant_members` projection: follow-up issue (Q4).
- A mctl-api membership table or membership API (Q1).
- Commerce shared-tenant behaviour (mctl-agents#631), beyond the minimal
  approvals dependency named in design.md.
- The trusted Dex slot's unfiltered groups (`LegacyDexGroups`): Dex is off in
  production, and principal mode ignores provider groups entirely, so it
  needs no separate change here; deleting the Dex code is its own cleanup.
