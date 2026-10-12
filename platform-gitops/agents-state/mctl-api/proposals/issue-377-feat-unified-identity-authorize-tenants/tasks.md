# Tasks: issue-377-feat-unified-identity-authorize-tenants

PR-0 is approved by the owner and proceeds on its own. Everything from PR-A
on waits for this proposal's approval. Each slice leaves `main` working, and
none changes behaviour while `TENANT_AUTHZ_MODE` is `legacy`.

---

## PR-0 — the tenant `admins` never confers platform admin (independent)

Scope is exactly this; nothing from PR-A onwards rides along.

- [ ] 0.1 In `resolveGroups` (`internal/auth/oidc.go`), pass the resolver's
  tenants through the existing `tenantsOnly` before appending them, so the
  only source of `"admins"` on that path is `validator.IsAdmin(login)`
  (`ADMIN_USERS`). This one function serves both GitHub PAT entry points:
  the legacy middleware branch (`oidc.go`, "GitHub token path") and the
  registry's `legacyGroupSource` (`internal/auth/provider_github.go`). The
  OAuth path (`withAdmins`) and the relay/delegation constructors already
  strip it and are not touched.
- [ ] 0.2 Tests in `internal/auth`:
  - a resolver returning `["admins", "mctl"]` for a login **not** in
    `ADMIN_USERS` yields groups `["mctl"]`, `IsAdmin() == false`,
    `HasTenantAccess("labs") == false`;
  - the same through `githubProvider` / `legacyGroupSource`, so the registry
    path is pinned too, not only the helper;
  - a login in `ADMIN_USERS` that is also a member of the tenant `admins`
    gets exactly one `"admins"` entry and `IsAdmin() == true`;
  - a resolver error still yields no tenants (unchanged behaviour).
- [ ] 0.3 Mutation check: revert 0.1 locally and confirm the first two tests
  fail; record that in the PR body.
- [ ] 0.4 PR body states the behaviour change honestly: a non-admin member of
  the tenant `admins` signing in with a GitHub PAT loses platform admin **and**
  tenant access to the `admins` namespace via `HasTenantAccess`, which is
  what the OAuth/ZITADEL path already does today. Tenant-role checks
  (`checkTenantRole` via `MemberRoles`) are unaffected. Today the tenant has
  one member, who is in `ADMIN_USERS`, so no current caller changes.

DoD: `go test ./internal/auth/...` green; CI green; Claude review with no
open P1/P2; released and deployed like any mctl-api fix.

Not in PR-0: reserving the name `admins` (see design.md), Dex groups,
`ADMIN_PRINCIPALS`, any principal-mode code.

---

## PR-A — principal-keyed reading, shadow mode, backfill plan

- [ ] A1 Parser: `principalId` (validated format) on tenant and team member
  entries; `userId` optional; malformed or duplicate `principalId`, or an
  entry with neither key, makes that tenant unreadable (error, not
  "not a member"). Tests for each refusal and for a ZITADEL-only entry with
  no `userId`.
- [ ] A2 Reader: `NamespacesForPrincipal`, `TryNamespacesForPrincipal`,
  `MemberRolesForPrincipal`, with the same team/tenant-fallback semantics as
  the login versions (table-driven parity test over the same fixtures).
- [ ] A3 `TENANT_AUTHZ_MODE` (`legacy` default, `shadow`; `principal` refused
  at boot until PR-B). Unknown value refuses boot.
- [ ] A4 Shadow comparison at the authorization points (`HasTenantAccess`
  decisions in handlers and `checkTenantRole`) plus metrics from design.md;
  `unresolved` never counted as `match` or `diff`. Test: a fixture where the
  two decisions differ increments the right `kind`; a store error increments
  `unresolved` only.
- [ ] A5 Backfill plan command: read-only, resolves through the live GitHub
  identity (numeric id), prints proposed `principalId`s and an unresolved
  list; exits non-zero when the unresolved list is non-empty.
- [ ] A6 `docs/principals.md` and `docs/federation.md`: membership keyed by
  principal, the mode flag, the switch criterion, rollback.

## gitops — backfill and shadow

- [ ] G1 PR adding `principalId` to every member entry from A5's output,
  reviewed by the owner; unresolved list empty.
- [ ] G2 Values change: `TENANT_AUTHZ_MODE=shadow` for mctl-api.

## PR-B — principal mode (mergeable behind the flag before the window ends)

- [ ] B1 `User.platformAdmin`, set only by `ADMIN_PRINCIPALS` or the static
  service principal; in principal mode `IsAdmin()` reads only that field.
  Mutation-pinned test: a tenant named `admins`, a provider group `admins`
  and a `Groups` entry `admins` each fail to make an admin.
- [ ] B2 `ADMIN_PRINCIPALS` parsing and validation; boot refused in principal
  mode when empty; warning when `ADMIN_USERS` is set in principal mode.
- [ ] B3 Local OAuth JWT `pid` claim at mint; principal mode refuses a local
  JWT without `pid` (401).
- [ ] B4 Principal-mode group and role resolution (design.md steps 3-4);
  resolution failure is 503; `checkTenantRole` no longer needs
  `GitHubLogin()`. Mutation-pinned test: re-introducing a login comparison
  fails a named test.
- [ ] B5 Surface relay and agent delegation resolve the subject's principal
  and use the principal lookup; unresolvable subject refused.
- [ ] B6 ZITADEL-only integration test (design.md, Q5), including removal and
  the unlinked same-email negative.
- [ ] B7 mctl-gitops: `wft-create-tenant` writes `principalId` for the owner;
  CI check refusing an unkeyed member entry.

## Switch

- [ ] S1 Switch criterion met (design.md), evidence attached to the issue.
- [ ] S2 Values change: `TENANT_AUTHZ_MODE=principal` and `ADMIN_PRINCIPALS`
  in one PR.
- [ ] S3 Live checks: GitHub PAT, ZITADEL MCP OAuth, ZITADEL bearer, a
  ZITADEL-only principal on `commerce-proof`, and the unlinked negative.

## PR-C — remove legacy (after 14 days in principal mode)

- [ ] C1 Delete the login-keyed decision path, `ADMIN_USERS`, `legacy` and
  `shadow` modes, and the login reader methods. `userId` stays as optional
  display data.

## Follow-up issues (open when this proposal is approved)

- [ ] F1 Per-object ownership migration from `github:<login>` (Q3).
- [ ] F2 Portal `tenant_members` as a principal-keyed projection with
  deletion reconciliation (Q4).
- [ ] F3 Approval self-decision by principal id, only if mctl-api#489 /
  mctl-agents#631 need it first (design.md).
