# Requirements — wrangler-node22-ci-upgrade

## Context

Wrangler (workers-sdk) @4.87.0, released 2026-04-30, introduced a hard
Node.js version gate: it exits at startup with a fatal error when run on
Node.js < 22. The `deploy.yml` GitHub Actions workflow that is the sole
pipeline for deploying the mctl-web Cloudflare Worker presumably pins an
older Node version (18 or 20). Until both the CI Node version and the
wrangler package version are updated together, every Worker deploy will
fail before any user code is evaluated.

Because this is the only in-repo deploy pipeline on the platform (an
explicit exception from centralized mctl-gitops builds), the breakage is
fully contained here — but it is also entirely the mctl-web team's
responsibility to fix.

## User stories

- AS A developer I WANT to push a change to `cloudflare-worker/` SO THAT
  the CI pipeline deploys it via wrangler without a Node.js version error.
- AS A platform engineer I WANT the wrangler version in `package.json` to
  stay current SO THAT the Worker benefits from the latest Cloudflare
  runtime fixes and security patches.
- AS A developer I WANT the Nuxt SSG build step to be unaffected by the
  Node version change SO THAT landing-page and docs deployments continue
  to work normally.

## Acceptance criteria (EARS notation)

- WHEN the `deploy.yml` workflow runs on a commit that touches
  `cloudflare-worker/` THE SYSTEM SHALL execute wrangler using Node.js 22
  or higher.
- WHEN wrangler starts up in CI THE SYSTEM SHALL not exit with a
  "Node.js version too old" fatal error.
- WHEN `npm ci` runs in the Worker deploy job THE SYSTEM SHALL install
  wrangler at version 4.87.0 or later as declared in `package.json`.
- WHEN the wrangler deploy step completes successfully THE SYSTEM SHALL
  report a zero exit code and the Worker revision shall be visible in the
  Cloudflare Dashboard.
- WHILE the Node.js version in `deploy.yml` is set to 22 THE SYSTEM SHALL
  continue to build the Nuxt SSG site without errors or regressions.
- IF the Node.js version in CI is set to a value lower than 22 THEN THE
  SYSTEM SHALL fail fast at the version-check step rather than producing a
  misleading wrangler error.

## Out of scope

- Upgrading any runtime dependency other than wrangler in this change.
- Migrating the Worker deploy pipeline to mctl-gitops centralized builds.
- Changing the Cloudflare Worker business logic, routes, or secrets.
- Enforcing Node 22 on developer workstations (`.nvmrc` / Volta is a
  complementary nicety, not a requirement of this proposal).
