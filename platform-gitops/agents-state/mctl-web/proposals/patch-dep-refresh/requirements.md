# Patch-level dependency refresh (vue-core, vueuse, sass)

## Context
Three in-stack frontend dependencies have newer releases ahead of their currently pinned versions: Vue 3 (3.5.30 → 3.5.33), @vueuse/core (14.2.1 → 14.3.0), and sass (1.98.0 → 1.99.0). All three are patch or minor bumps within their respective stable lines and carry no documented breaking changes for the API surface used by `mctl-web`.

Batching these into a single PR minimises review overhead and keeps the dependency graph current. A current dependency graph reduces the blast radius of future security patches (fewer versions to traverse), lowers the chance of transitive conflicts when a more significant upgrade is applied, and avoids the accumulation of changelogs that must be reviewed all at once later. None of these bumps affect the Cloudflare Worker or the Kubernetes cluster, so there is no risk to the `labs` tenant memory budget.

## User stories
- AS a frontend developer I WANT all patch-level dependencies to be at their latest releases SO THAT I am protected against known bugs fixed in those patches and experience less friction in future upgrades.
- AS a platform engineer I WANT the project's dependency graph to be current SO THAT security scanners do not flag stale-but-non-vulnerable packages as noise.

## Acceptance criteria (EARS)
- WHEN the root `package.json` is read THE SYSTEM SHALL declare version constraints that resolve to Vue 3 ≥ 3.5.33, @vueuse/core ≥ 14.3.0, and sass ≥ 1.99.0 (within their respective minor lines).
- WHEN `nuxt build` is executed after the bumps THE SYSTEM SHALL complete without errors and produce the same three prerendered routes (`/`, `/docs`, `/privacy`) as before.
- WHEN `npm audit --audit-level=high` is run against the updated lockfile THE SYSTEM SHALL report no new High or Critical vulnerabilities.
- WHILE `nuxt build` is running with sass 1.99.0 THE SYSTEM SHALL not emit deprecation warnings related to user-defined function names that clash with CSS built-in functions (e.g., `calc`, `clamp`), or any such clash shall be resolved in the same PR.
- IF @vueuse/core 14.3.0 introduces a change to the signature of any composable used in the project THEN THE SYSTEM SHALL update the call sites to match the new signature before the PR is merged.

## Out of scope
- Upgrading Vue beyond the 3.5.x line.
- Upgrading @vueuse/core beyond the 14.3.x line.
- Upgrading sass beyond the 1.99.x line.
- Upgrading vue-router (separate proposal — major version jump).
- Upgrading Nuxt (separate proposal — `nuxt-minor-upgrade`).
- Any changes to the Cloudflare Worker (`cloudflare-worker/`).
- Introducing new composables or sass features made available by these upgrades.
