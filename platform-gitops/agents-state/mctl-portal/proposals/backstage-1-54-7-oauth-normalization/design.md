# Design: backstage-1-54-7-oauth-normalization

## Current state
mctl-portal runs Backstage (yarn workspaces, `packages/app` + `packages/backend` +
custom `plugins/*`) on revision `2.6.3`, currently Healthy/Synced in the `admins`
tenant (per 2026-09-12 ArgoCD status). Authentication is handled via Dex JWT
(`ops.mctl.me/api/dex`), with sessions persisted in Postgres and RBAC via group
mapping (see `context/architecture.md`, "Auth" section). The OAuth profile
normalization logic that this patch fixes lives in Backstage's core
`@backstage/plugin-auth-backend` (or equivalent core auth package depending on the
tracked version), which mctl-portal consumes as an upstream dependency rather than
a fork.

## Proposed solution
Bump the relevant Backstage core auth package(s) (and, if the repo pins a unified
Backstage release line via `backstage-cli`, the overall release line) to v1.54.7 or
the latest 1.x patch that includes this fix. This is a dependency-version bump inside
the existing yarn workspaces monorepo, not a structural change:

1. Update `package.json` / `backstage.json` (release line) and run
   `backstage-cli versions:bump` or the project's standard upgrade command to pull in
   v1.54.7 across `packages/app`, `packages/backend`, and shared deps.
2. Rebuild and run the full yarn workspace build to confirm no dependency
   incompatibilities are introduced (monorepo build is already known to be
   noticeably slow — ADR 0001 consequence — budget time accordingly).
3. Run the existing e2e (Playwright) and auth-specific integration tests against the
   Dex login flow in a lower environment before promoting.
4. Deploy via the standard path: Docker build → mctl-gitops → ArgoCD sync in `admins`.

This is the minimal, contained way to pick up the fix: it stays within a patch
version, requires no schema or session-storage changes, and does not touch the Dex
provider configuration itself.

## Alternatives
- **Wait and bundle with the next scheduled Backstage upgrade** — rejected because
  this is a security/correctness fix on the auth surface; deferring it leaves a known
  identity-normalization bug in production for an unbounded time.
- **Cherry-pick only the specific upstream commit/patch into a fork** — rejected as
  higher effort and higher long-term maintenance cost (diverges from upstream,
  complicates future upgrades) for a fix that is already released as an official
  patch version.
- **Skip straight to the next Backstage minor/major to "get it over with"** — rejected
  per ADR 0001 and `architecture.md` guardrail: major/minor bumps require waiting for
  community-plugins compatibility; mixing that risk with an urgent auth patch is
  unnecessary.

## Platform impact
- **Migrations:** None. No database schema or session-storage changes are expected;
  this is an auth-backend logic fix, not a data model change.
- **Backward compatibility:** Existing sessions and catalog user entities are expected
  to remain valid. Users whose profiles were previously normalized incorrectly may see
  their identity re-resolved correctly on next login — this should be verified in a
  lower environment first.
- **Resource impact (`labs`):** None — mctl-portal runs only in the `admins` tenant;
  `labs` is not affected by this change.
- **Risks and mitigations:**
  - *Risk:* a custom plugin (kubernetes, observability, scaffolder) has an implicit
    dependency on the exact auth-backend behavior being changed.
    *Mitigation:* run full plugin smoke tests before promoting; roll out to a lower
    environment first.
  - *Risk:* monorepo build/install overhead (known ADR 0001 consequence) delays
    validation.
    *Mitigation:* schedule the bump as a normal dependency-update task with the usual
    CI build budget, not an emergency same-day hotfix, unless active exploitation is
    observed.
