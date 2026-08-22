# Update wrangler to 4.125.0 for KV-corruption and auth fixes

## Context
The Cloudflare Worker in `cloudflare-worker/` (routes: `/api/github/login`,
`/api/github/callback`, `/api/submit`, `/api/contact`, plus domain redirects) is
deployed via Wrangler through `deploy.yml`, which lives in this repo as an explicit
exception from centralized `mctl-gitops` builds. wrangler 4.125.0 fixes a binary KV
value corruption bug and multi-login authentication handling issues, and adds several
unrelated features (raw TCP `connect` trigger, worker-preview container support,
workflow instance deletion). Our current pin is not specified in `architecture.md`
(wrangler is a devDependency of the deploy pipeline, not a runtime dependency of the
Worker itself), so this proposal treats the bump as a general devDependency update
driven specifically by the KV-corruption and auth-handling fixes.

## User stories
- AS the engineer maintaining the `deploy.yml` pipeline I WANT wrangler upgraded to
  4.125.0 SO THAT Worker deploys are not exposed to the known binary KV value
  corruption bug or multi-login auth handling issues.
- AS a service owner I WANT this bump scoped narrowly to the deploy tooling SO THAT it
  carries no runtime risk to the deployed Worker or Nuxt site.

## Acceptance criteria (EARS)
- WHEN the wrangler devDependency is upgraded THE SYSTEM SHALL pin wrangler to version
  4.125.0 (or the latest patch available at execution time within the same major
  line) in the deploy pipeline's dependency manifest.
- WHEN `deploy.yml` runs after the upgrade THE SYSTEM SHALL successfully build and
  deploy the Worker with no pipeline errors attributable to the wrangler version
  change.
- IF the Worker writes or reads binary values to/from a KV namespace THEN THE SYSTEM
  SHALL do so using the corrected wrangler tooling that avoids the known corruption
  bug.
- WHILE the deploy pipeline authenticates to Cloudflare (including any multi-login
  scenarios in CI) THE SYSTEM SHALL use the corrected auth handling from 4.125.0.
- IF the bump introduces any breaking CLI flag or config changes in `wrangler.toml`
  THEN THE SYSTEM SHALL update the pipeline configuration accordingly before merging.

## Out of scope
- Any change to the Worker's runtime code, routes, secrets, or rate-limit
  configuration — this is a build-time tooling bump only.
- Adopting new wrangler 4.125.0 features unrelated to the fixes (raw TCP `connect`
  trigger, worker-preview container support, workflow instance deletion) — those are
  not part of this proposal's driving rationale and can be considered separately if
  useful.
- Any change to `mctl-gitops` or the centralized build process — `deploy.yml` remains
  an explicit per-repo exception, unchanged by this proposal.
