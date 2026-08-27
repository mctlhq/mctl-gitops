# Require authenticated, team-scoped access on github-app-connect-backend routes

## Context
`plugins/github-app-connect-backend/src/plugin.ts` (lines 96-131) registers
`allow: 'unauthenticated'` auth policies for every route the plugin exposes:
`/callback`, `/install-url`, `/repo-access`, `/install-status`, `/repos`,
`/popup-done`, `/repo-tags`, `/service-config`, and `/webhook`. Because the
Backstage backend is publicly reachable at `app.mctl.ai`, any anonymous
caller can hit `/repos?team=<team>` to enumerate a team's connected GitHub
repositories, `/service-config?team=<team>&service=<service>` to read a
deployed service's environment variable names and secret key names (not
values, but still enough to map attack surface), `/repo-tags?repo=...` to
pull semver tags for any org repo the App is installed on, and
`/repo-access` / `/install-status` to probe whether a specific team/service
has a GitHub App connection at all. None of this requires knowing anything
about the target beyond a team or repo name.

This matters because it is a straightforward reconnaissance and
information-disclosure gap: the routes leak per-tenant configuration and
repo metadata to anyone on the internet, with no rate limiting or audit
trail, and it does not match the ownership model the rest of the platform
already uses (`tenant-backend`'s `tenant_members` table, enforced via
`getTenantMember`/`isAdminUser` from `membershipLookup.ts` and consumed by
`vault-secrets-backend`'s `requireTenantRole`/`checkTenantRole`). This
proposal brings `github-app-connect-backend` in line with that existing
pattern.

## User stories
- AS a platform operator I WANT the GitHub App connect read routes to
  require an authenticated Backstage user who is a member of the target
  team SO THAT anonymous callers cannot enumerate a tenant's connected
  repos, tags, or service configuration.
- AS a Backstage user who is not a member of a given team I WANT read
  requests scoped to that team to be rejected SO THAT I cannot see another
  team's GitHub App connection state.
- AS the GitHub platform (OAuth/webhook caller) I WANT `/callback` and
  `/webhook` to remain reachable without a Backstage session SO THAT the
  GitHub App installation flow and tag-push webhook keep working, since
  GitHub cannot present a Backstage bearer token.
- AS a developer using the "Grant access" popup flow in
  `GitHubRepoPicker.tsx` I WANT the popup confirmation page to keep working
  without requiring a fresh Backstage auth context in that window SO THAT
  the existing install UX is not broken.

## Acceptance criteria (EARS)
- WHEN an unauthenticated request is made to `/repos`, `/repo-tags`,
  `/service-config`, `/repo-access`, or `/install-url` THE SYSTEM SHALL
  respond 401.
- WHEN an authenticated Backstage user who is not a member of the `team`
  the request is scoped to (and not a platform admin, i.e. not an `owner`
  in the `admins` tenant) calls `/repos`, `/service-config`, `/repo-access`,
  or `/install-url` with that `team` THE SYSTEM SHALL respond 403.
- WHEN an authenticated Backstage user who is a member of the `team` (or a
  platform admin) calls `/repos`, `/service-config`, `/repo-access`, or
  `/install-url` with that `team` THE SYSTEM SHALL respond 200 with the
  existing response body shape, unchanged.
- WHEN `/repo-tags?repo=owner/name` is called by an authenticated user THE
  SYSTEM SHALL serve the response without requiring team membership, since
  the route is not team-scoped (it is keyed only by `repo`) and instead
  SHALL require any authenticated Backstage user (no anonymous access).
- WHEN GitHub redirects a browser to `/callback` with `installation_id` and
  an encrypted `state` parameter THE SYSTEM SHALL continue to accept the
  request without a Backstage session, gated solely by the existing
  `decryptState`/HMAC-derived-key validation, matching the issue's
  instruction to keep `/callback`'s state-token check as the security gate.
- WHEN GitHub redirects a browser to `/popup-done` (no state or team data
  consumed by that route) THE SYSTEM SHALL continue to serve it without a
  Backstage session, since it renders no team-scoped data and exists only
  as a same-tab landing page for the install popup.
- WHEN GitHub POSTs to `/webhook` THE SYSTEM SHALL continue to accept the
  request without a Backstage session, gated solely by the existing
  `X-Hub-Signature-256` HMAC verification — GitHub cannot supply a
  Backstage bearer token, and the HMAC check is the equivalent crypto gate
  the issue asks to preserve for `/callback`.
- WHILE the `github-app-connect` plugin is running THE SYSTEM SHALL NOT
  register any `allow: 'unauthenticated'` policy for `/repos`,
  `/repo-tags`, `/service-config`, `/repo-access`, `/install-url`, or
  `/install-status` — these fall back to Backstage's default
  authentication requirement.
- IF a request to a team-scoped route omits the `team` query parameter
  THEN THE SYSTEM SHALL respond 400 (existing validation), evaluated before
  any membership check that would need a team to check against.
- IF the caller is a platform admin (owner role in the `admins` tenant, per
  `isAdminUser`) THEN THE SYSTEM SHALL allow the request regardless of
  membership in the target team, mirroring `vault-secrets-backend`'s
  `checkTenantRole` admin bypass, and SHALL be auditable (logged) the same
  way `vault-secrets-backend`'s `auditSecretRead` logs bypassed reads.
- WHEN the existing GitHub App connect flow (install popup ->
  `/callback` -> `/popup-done` -> `GitHubRepoPicker` re-fetching `/repos`
  and `POST /repos/sync`) is exercised end-to-end by an authenticated user
  who is a member of the target team THE SYSTEM SHALL complete the flow
  successfully, with no route in the chain returning 401/403 for that user.

## Out of scope
- `custom-domains-backend` tenant checks (tracked separately; note that
  `plugins/custom-domains-backend/src/plugin.ts` already documents in a
  comment that only `/health` is public and cites a removed
  `/domains*` unauthenticated policy — the router-level team-membership
  check on `/domains` itself is not evaluated here).
- `permission-backend-module-team-policy` default-allow behavior (tracked
  separately).
- Changing `/callback`'s Flow 3 (direct GitHub install, no `state`
  parameter) trust model — it already relies solely on GitHub-issued
  `installation_id` verified against the GitHub API, independent of
  Backstage auth, and the issue does not ask to change that.
- Rate limiting or additional abuse protections beyond auth + team
  membership.
- `POST /repos/sync` was not named in the issue's route list, but shares
  the same team-scoping and leak profile as `/repos`; see Open questions.

## Open questions
- The issue's "Expected fix" section lists `/repos`, `/repo-tags`,
  `/service-config`, `/repo-access`, `/install-url` as the read routes to
  gate, but the cited evidence range (`plugin.ts:96-131`) also covers
  `/install-status` and `/popup-done`. `/install-status` returns the same
  kind of team/service/repo connection data as `/repo-access` (it is a CLI
  polling variant of it), so this proposal treats it as in-scope and gates
  it the same way. `/popup-done` renders no team-scoped data (static HTML,
  no query params consumed), so this proposal leaves it unauthenticated.
  Reviewer should confirm this reading matches intent.
- `POST /repos/sync` (router.ts:530) has no explicit `addAuthPolicy` entry
  of its own. `vault-secrets-backend/src/plugin.ts` notes that Backstage's
  `addAuthPolicy` path matching is exact, not prefix-based, so `/repos/sync`
  is a distinct path from `/repos` and is likely already implicitly
  authenticated today by Backstage's default-deny. This proposal verifies
  that assumption during implementation (task 1) and, regardless, brings
  `/repos/sync` under the same team-membership check applied to `/repos`
  for consistency, since it accepts and trusts a client-supplied `user`
  query parameter with no verification against the caller's identity
  today.
- `GitHubRepoPicker.tsx` and `GitTagPicker.tsx` currently call `/repos`,
  `/repos/sync`, and `/repo-tags` with the raw global `fetch()`, not
  Backstage's `fetchApiRef`-backed `fetchApi.fetch()`, so no Authorization
  header is attached. Making these routes require authentication will
  break those call sites unless they are updated to use `fetchApi.fetch()`
  (the pattern `CurrentConfigField.tsx` already uses for `/service-config`
  and `vault-secrets`' `/teams/:team/:app/secrets`). This proposal treats
  that frontend fix as required to meet the "existing flow still completes
  end-to-end" acceptance criterion — see design.md and tasks.md.
- No evidence was found in this repo of an external CLI or non-browser
  caller of `/install-url` or `/repo-access`. If one exists outside this
  repo, gating these behind Backstage user auth would break it; absent
  evidence, this proposal proceeds with requiring Backstage user auth on
  both, as the issue explicitly asks for.
- The issue does not specify the exact membership model (viewer vs. owner
  role). This proposal uses `checkTenantRole(..., 'viewer')` (any team
  member, matching `vault-secrets-backend`'s read routes) rather than
  `'owner'`, since these are read/connect operations, not secret writes.
