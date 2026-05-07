# Upgrade Nuxt from 4.3.1 to 4.4.3 (with companion dependency bumps)

## Context
`mctl-web` currently runs Nuxt 4.3.1, Vue 3.5.30, @vueuse/core 14.2.1, and sass 1.98.0.
Nuxt 4.4.3 was released on 2026-04-29 and is two minor versions ahead of what is deployed.
Minor releases in the Nuxt 4.x line carry bug fixes, performance improvements, and
compatibility refinements for the Vue 3.5.x patch series. Nuxt is the most foundational
dependency of the frontend build; staying two minor versions behind creates compounding upgrade
risk, because each skipped minor may introduce internal API changes that make future upgrades
harder.

Three companion updates — Vue 3.5.34 (resolved transitively via Nuxt 4.4.3),
@vueuse/core 14.2.1 → 14.3.0, and sass 1.98.0 → 1.99.0 — carry no breaking changes for
this service's usage profile and are bundled in the same pull request to minimise
context-switching and keep the dependency graph consistent. The vue-router v5 migration is
explicitly out of scope and is tracked in a separate proposal.

## User stories
- AS a frontend engineer I WANT Nuxt upgraded to 4.4.3 together with the three companion
  dependencies SO THAT the dependency graph is internally consistent and upgrade debt is
  cleared in a single, reviewable change.
- AS a site visitor I WANT the landing, docs, and privacy pages to continue loading correctly
  after the upgrade SO THAT my browsing experience is unaffected.
- AS a platform engineer I WANT the GitHub Actions build and Wrangler deploy to succeed on
  the upgraded dependency set SO THAT no manual intervention is needed after merging.

## Acceptance criteria (EARS)
- WHEN `nuxt build` is executed against the updated `package.json` THE SYSTEM SHALL complete
  without errors and produce a `dist/` directory containing prerendered output for `/`,
  `/docs`, and `/privacy`.
- WHEN `package.json` is read after the upgrade THE SYSTEM SHALL declare `nuxt` at
  `^4.4.3`, `@vueuse/core` at `^14.3.0`, and `sass` at `^1.99.0`.
- WHEN the lockfile is inspected after `npm install` THE SYSTEM SHALL resolve Vue to
  3.5.34 or a later patch, consistent with Nuxt 4.4.3's peer-dependency range.
- WHEN the upgraded application is served THE SYSTEM SHALL render all three routes (`/`,
  `/docs`, `/privacy`) with correct content and no JavaScript console errors.
- WHEN a user submits the tenant onboarding form THE SYSTEM SHALL validate input via
  vee-validate 4.15.1 and yup 1.7.1 and forward the request to `/api/submit` exactly as
  it did before the upgrade.
- WHILE the GitHub Actions deploy workflow runs THE SYSTEM SHALL pass lint, type-check,
  and build steps before the Wrangler deploy step is reached.
- IF any deprecation warning is emitted by `nuxt build` or the sass compiler THE SYSTEM
  SHALL have a documented mitigation applied in the same pull request, or a follow-up issue
  filed and linked before merging.
- IF a runtime error is detected on any prerendered route after deploy THE SYSTEM SHALL
  allow rollback to the previous Cloudflare Pages deployment within five minutes.

## Out of scope
- vue-router v4 to v5 migration (tracked in a separate proposal).
- Any changes to vee-validate or yup versions (ADR 0001 prohibits replacing them without
  a specific bug or performance reason; both are already current).
- Reverting from Nuxt to vanilla HTML (prohibited by ADR 0001).
- Changes to the Cloudflare Worker (`cloudflare-worker/`) source code or its secrets.
- Upgrading vite-svg-loader, wrangler, or workerd — these are not part of this batch.
- Upgrading Nuxt beyond the 4.4.x line (e.g., 4.5.x) in this proposal.
