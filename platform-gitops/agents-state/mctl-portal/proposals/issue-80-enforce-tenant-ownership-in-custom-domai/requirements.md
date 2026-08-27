# Enforce tenant ownership in custom-domains-backend

## Context
`plugins/custom-domains-backend/src/router.ts` authenticates callers (only
`/health` is registered as an unauthenticated route in `plugin.ts`'s
`registerAuthPolicies`), but none of the `/domains*` handlers check whether
the authenticated user actually belongs to the `team` the request operates
on. `GET /domains?team=X`, `POST /domains`, `POST /domains/:id/verify`, and
`DELETE /domains/:id` all trust the `team` value taken from the query
string, request body, or the stored row without comparing it against the
caller's tenant memberships. Any logged-in Backstage user can therefore
list, register, "verify", or delete another tenant's custom-domain mappings
by simply supplying a different `team` value or a guessed/enumerated
domain `id` — a cross-tenant IDOR on the public `app.mctl.ai` surface.
Combined with the missing verify/delete RBAC in `mctl-api` (companion
issue, out of scope here), this is a complete cross-tenant compromise path
for custom domain configuration.

The platform already has a canonical way to close this class of bug:
`plugins/tenant-backend/src/membershipLookup.ts` exports `getTenantMember`
and `isAdminUser`, built specifically so that plugins other than
tenant-backend can authorize a caller against a team via a cross-schema
Knex query. `plugins/vault-secrets-backend/src/router.ts`
(`checkTenantRole` / `requireTenantRole`) and
`plugins/argo-workflows-backend/src/teamAccessAction.ts` both already
consume this helper to gate their tenant-scoped routes. This proposal
brings `custom-domains-backend` in line with that established pattern
instead of inventing a new authorization mechanism.

## User stories
- AS a tenant member I WANT to manage only my own team's custom domains
  SO THAT another team cannot read, register, verify, or delete my domain
  configuration.
- AS a platform admin (owner of the `admins` tenant) I WANT to retain
  cross-tenant access to custom-domains routes SO THAT support and
  incident response are not blocked by per-tenant membership checks.
- AS an anonymous caller I WANT to be rejected outright SO THAT no
  custom-domain data or existence information is exposed without a
  session.

## Acceptance criteria (EARS)
- WHEN an unauthenticated request hits any `/domains*` route (other than
  `/health`) THE SYSTEM SHALL respond `401` before any tenant or DB lookup
  is performed.
- WHEN an authenticated user who is a member of tenant `team` (any role) or
  an owner of the `admins` tenant calls `GET /domains`, `POST /domains`,
  `POST /domains/:id/verify`, or `DELETE /domains/:id` for that `team` THE
  SYSTEM SHALL process the request exactly as it does today (unchanged
  response shape and status codes).
- WHEN an authenticated user who is NOT a member of tenant `team` and NOT
  an `admins`-tenant owner calls `GET /domains?team=<other>`,
  `POST /domains` with `team=<other>`, `POST /domains/:id/verify` where the
  stored entry's `team` is `<other>`, or `DELETE /domains/:id` where the
  stored entry's `team` is `<other>` THE SYSTEM SHALL respond `403` and
  SHALL NOT list, create, verify, or delete the resource.
- IF the caller is authenticated and the target `/domains/:id/*` entry does
  not exist THEN THE SYSTEM SHALL continue to respond `404` (existing
  behavior), evaluated only after the `401` authentication check.
- WHILE resolving ownership for `:id`-scoped routes (verify/activate/
  delete) THE SYSTEM SHALL derive the tenant to authorize against from the
  stored `custom_domains.team` column of the fetched row, not from any
  client-supplied value.
- WHEN a Backstage service-to-service credential (used by the Argo
  ingress-update workflow calling `POST /domains/:id/activate`) is
  presented THE SYSTEM SHALL treat it as authorized, mirroring the
  service-credential tier already used by `tenant-backend`'s
  `resolveAuth()`.
- WHERE the caller is unauthenticated or lacks tenant/admin authorization,
  THE SYSTEM SHALL NOT reveal whether a given domain `id` or `team` exists
  beyond the generic `401`/`403` response.

## Out of scope
- `mctl-api`'s verify/delete RBAC (tracked in the companion mctl-api
  issue referenced from #80).
- Any change to DNS verification logic, domain validation regex, or the
  `custom_domains` table schema.
- Role-tiered authorization within a tenant (e.g. requiring `owner` role
  specifically for delete vs `viewer` for list). The issue only asks for
  tenant-membership enforcement, not per-role gating.
- Changes to the frontend (`packages/app/src/components/catalog/
  EntityDomainsCard.tsx`) beyond what is needed to surface a 403 message,
  if any; this proposal is backend-only.

## Open questions
- The issue enumerates "list/add/verify/delete" but the router also has a
  `POST /domains/:id/activate` route not mentioned in the issue, described
  as "called by workflow after ingress update." It has the same IDOR shape
  today. This proposal includes it and authorizes it via tenant membership
  OR Backstage service credentials (the tier already used by
  tenant-backend/vault-secrets-backend for plugin-to-plugin calls), since
  the actual Argo workflow caller lives outside this repo and its exact
  auth mechanism cannot be verified from this clone. If the workflow in
  fact calls this route with a user token today, that call will start
  failing with 403 unless the caller is a tenant member/admin — this
  should be verified against the Argo WorkflowTemplate before merge.
- Whether "member" should be gated by role (e.g. `delete` requiring
  `owner`, mirroring vault-secrets-backend's `owner`-only Telegram intake).
  Resolved as: no role gating — any tenant role authorizes all four
  routes, since the issue's acceptance criteria only distinguish
  member/non-member/anonymous, not roles within a tenant.
- `POST /domains` includes a `created_by` field taken from the request
  body today. Whether it should be forced to the resolved `userId` instead
  of trusting the client-supplied value is not explicitly asked for by the
  issue; treated as a related-but-separate hardening item and left
  unchanged here (recorded for a follow-up, not blocking this proposal).
