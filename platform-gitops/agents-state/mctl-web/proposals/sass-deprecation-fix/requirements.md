# Sass Deprecation Fix for v1.99.0

## Context
mctl-web uses sass 1.98.0 (confirmed in `context/architecture.md`) to compile SCSS stylesheets as part of the Nuxt/Vite build pipeline. sass 1.99.0, released 2026-04-02, introduces deprecation warnings for several function naming patterns—including global built-in function usage and legacy color functions. In the sass project's established policy, deprecation warnings in a minor release become hard errors in the next major release (sass 2.0). If the deprecations are not resolved, the `nuxt build` step will eventually fail unconditionally, blocking all deployments.

Addressing these warnings now, while they are still non-fatal, is significantly cheaper than an emergency fix triggered by a build outage. The change is purely build-time; it does not affect the served static output, the Cloudflare Worker, or any Kubernetes tenant's resource consumption.

## User stories
- AS a frontend engineer I WANT the SCSS codebase to be free of sass 1.99.0 deprecation warnings SO THAT the `nuxt build` pipeline continues to succeed when sass 2.0 is released.
- AS a platform engineer I WANT sass upgraded to 1.99.0 in the project's dependencies SO THAT we build against the current stable compiler and catch future deprecations early.
- AS an on-call engineer I WANT the build pipeline to remain green without emergency SCSS rewrites SO THAT deployments are never blocked by a compiler version upgrade.

## Acceptance criteria (EARS)
- WHEN `nuxt build` runs with sass 1.99.0 THE SYSTEM SHALL complete without any sass deprecation warnings in the build output.
- WHEN a `.scss` file is added or modified THE SYSTEM SHALL emit a CI lint or build error if the file uses any pattern deprecated in sass 1.99.0.
- WHILE the Nuxt/Vite build pipeline is executing THE SYSTEM SHALL use sass version 1.99.0 or above as the style compiler.
- IF any SCSS file uses a global built-in function or legacy color function pattern deprecated in sass 1.99.0 THEN THE SYSTEM SHALL surface a build-time error (not a runtime error) so it can be corrected before deployment.
- WHEN the sass version is updated in `package.json` THE SYSTEM SHALL have a corresponding updated `package-lock.json` committed in the same changeset.

## Out of scope
- Upgrading to sass 2.0 (not yet released; tracked as a future proposal once 2.0 reaches stable).
- Changes to Cloudflare Worker code or wrangler configuration.
- Changes to Nuxt, Vue, or Vite versions.
- Runtime or Kubernetes resource changes for `admins` or `labs` tenants.
- Redesigning or refactoring SCSS architecture beyond the minimum changes needed to remove deprecated patterns.
