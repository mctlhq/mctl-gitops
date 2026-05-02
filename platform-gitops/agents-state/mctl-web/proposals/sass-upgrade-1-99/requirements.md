# Upgrade sass from 1.98.0 to 1.99.0

## Context
mctl-web uses `sass 1.98.0` as the SCSS compiler integrated into the Nuxt/Vite build pipeline
(confirmed in `context/architecture.md`). sass 1.99.0 was released on 2026-04-02 and introduces
two user-facing changes: native support for the parent selector (`&`) at the document root level
(previously a syntax error), and deprecation notices for a set of CSS-conflicting built-in
function names.

The related `sass-deprecation-fix` proposal already targets suppressing the new deprecation
warnings at the SCSS source level. This proposal is complementary: it covers the version step
itself — bumping `package.json` from 1.98.0 to 1.99.0 — so that the deprecation-fix work and
any future `&`-at-root stylesheet additions have the correct compiler under them. sass is a
build-only tool; there is zero runtime or Kubernetes resource impact.

## User stories
- AS a frontend engineer I WANT sass upgraded to 1.99.0 SO THAT the build pipeline runs on the
  current stable compiler and any SCSS using `&` at document root produces correct CSS output.
- AS a platform engineer I WANT the compiler version aligned with the `sass-deprecation-fix`
  proposal work SO THAT both changes can be merged together or in the correct order without
  version mismatch.
- AS an on-call engineer I WANT the build pipeline to remain green after this bump SO THAT no
  deployment is blocked by an unexpected compiler incompatibility.

## Acceptance criteria (EARS)
- WHEN `nuxt build` runs after the version bump THE SYSTEM SHALL invoke sass 1.99.0 as the
  style compiler, confirmed by the Vite/sass build log.
- WHEN `nuxt build` completes THE SYSTEM SHALL exit with code 0 and produce the same set of
  compiled CSS artefacts as under 1.98.0 for all existing SCSS files.
- IF any existing SCSS file emits a new deprecation warning under 1.99.0 THEN THE SYSTEM SHALL
  surface that warning in the CI build output so it can be resolved (this is expected and handled
  by the companion `sass-deprecation-fix` proposal).
- WHILE the Nuxt dev server is running with sass 1.99.0 THE SYSTEM SHALL hot-reload SCSS changes
  without errors.
- WHEN the version is updated in `package.json` THE SYSTEM SHALL include a matching
  `package-lock.json` update in the same changeset.

## Out of scope
- Fixing or suppressing individual deprecation warnings — covered by `sass-deprecation-fix`.
- Upgrading to sass 2.0 (not yet released; tracked for a future proposal when stable).
- Changes to Cloudflare Worker code, wrangler configuration, or Kubernetes manifests.
- Refactoring SCSS architecture beyond the minimum needed to compile cleanly on 1.99.0.
