# Upgrade Nuxt from 4.3.1 to 4.4.4

## Context
The `mctl-web` frontend is built with Nuxt 4 in SSG mode, prerendering three routes: `/`, `/docs`, and `/privacy`. The project is currently pinned to Nuxt 4.3.1. Nuxt 4.4.4 was released on 29 April 2026 (4.4.3 was immediately superseded by 4.4.4 due to a release-script issue; the effective release is 4.4.4). Minor version bumps within the Nuxt 4 line are expected to include bug fixes and performance improvements with no breaking API changes.

Staying one or more minor versions behind accumulates upgrade debt. As the Nuxt 4 ecosystem matures, the gap between minor releases grows larger, making future upgrades more risky. Given the highly constrained scope of this site (three prerendered routes, no dynamic SSR at runtime, no Nuxt modules beyond standard composables), upgrading now while the delta is small is low-risk and high-value.

## User stories
- AS a frontend developer I WANT the project to run on the latest Nuxt 4.4.x release SO THAT I benefit from upstream bug fixes and performance improvements without carrying upgrade debt.
- AS a site visitor I WANT the prerendered pages to load as fast as possible SO THAT the user experience matches the platform's quality standards.
- AS a platform engineer I WANT the dependency audit to show no outdated minor-version packages SO THAT future security patches land on a current base.

## Acceptance criteria (EARS)
- WHEN `nuxt build` is executed after the upgrade THE SYSTEM SHALL complete without errors and produce a valid `dist/` output.
- WHEN the prerendered output for `/`, `/docs`, and `/privacy` is inspected THE SYSTEM SHALL contain the same HTML structure and content as the output produced by Nuxt 4.3.1.
- WHEN `package.json` is read THE SYSTEM SHALL declare a nuxt version constraint that resolves to 4.4.4 or later within the 4.4.x range.
- WHILE the upgraded site is being served THE SYSTEM SHALL pass all existing end-to-end smoke tests with no regressions.
- IF a Nuxt 4.4.x release introduces a deprecation warning for any API used in this project THEN THE SYSTEM SHALL address that deprecation within the same PR or open a follow-up issue before merging.
- WHEN `npm audit` is run against the updated lockfile THE SYSTEM SHALL report no new High or Critical vulnerabilities introduced by the upgrade.

## Out of scope
- Upgrading Nuxt beyond the 4.4.x line (e.g., to 4.5.x or later).
- Upgrading vue-router from 4.6.4 to the 5.x major line (separate, high-effort proposal).
- Enabling additional Nuxt modules or features not already in use.
- Changes to the Cloudflare Worker (`cloudflare-worker/`).
- SSR runtime changes (the site remains fully prerendered / SSG).
- Migrating the build pipeline out of `deploy.yml`.
