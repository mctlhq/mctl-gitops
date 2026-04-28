# Design: sass-deprecation-fix

## Current state
As documented in `context/architecture.md`, mctl-web's frontend is built with Nuxt 4.3.1 (SSR enabled, selected routes prerendered). The build tool is Vite (bundled with Nuxt). Sass is a direct devDependency at version 1.98.0; Vite resolves it automatically for `.scss` imports in Vue SFCs and in globally imported style files.

sass 1.98.0 is one minor release behind 1.99.0. The new release adds:
- Support for the parent selector (`&`) at root level.
- User-defined overrides of `calc`/`clamp` function names.
- Deprecation warnings for: legacy CSS color functions used with sass syntax, global built-in functions not accessed through the `sass:*` module system, and other patterns noted in the dart-sass changelog.

Deprecation warnings are printed during `nuxt build` but do not yet fail the build. In sass 2.0 these patterns will be errors.

## Proposed solution
The fix has two parallel workstreams:

**1. Version bump** — Update `"sass"` in the root `package.json` from `"1.98.0"` to `"1.99.0"` (exact pin), run `npm install`, and commit the updated `package-lock.json`.

**2. SCSS audit and remediation** — Run `nuxt build` with sass 1.99.0 and capture all deprecation warnings. For each warning:
   - Replace global built-in function calls (e.g., `darken()`, `lighten()`, `mix()`) with their `sass:color` module equivalents via `@use 'sass:color'; color.adjust(...)`.
   - Replace any legacy `rgb()`/`hsl()` calls that use sass-specific argument syntax with the module-based equivalents.
   - Apply the minimum change needed; do not restructure SCSS architecture.

After remediation, a second `nuxt build` run must produce zero deprecation warnings. A CI check (build step) serves as the regression guard going forward.

The Nuxt/Vite pipeline requires no configuration changes; sass is resolved transparently by Vite's CSS pre-processor support.

## Alternatives

### Option A: Suppress deprecation warnings via sass `quietDeps` or `silenceDeprecations`
Vite and Nuxt expose sass options where individual deprecations can be silenced. This would make the build green without fixing the underlying patterns. Rejected because it is technical debt in a different form: the patterns will still be errors in sass 2.0, and the warnings serve as the only early-warning system.

### Option B: Delay until sass 2.0 forces the issue
No action is taken until a sass 2.0 upgrade is required. Rejected because at that point the build is already broken, creating an unplanned emergency with deployment impact.

### Option C: Migrate to a different CSS pre-processor (e.g., PostCSS only)
Replace sass entirely with PostCSS plugins. Rejected because the scope far exceeds the problem: mctl-web uses sass for a defined set of stylesheets, the migration cost is high, and the problem is solved more cheaply by fixing the deprecated patterns.

## Platform impact

### Migrations
No data migrations. `package-lock.json` is updated. SCSS source files are modified in place.

### Backward compatibility
sass 1.99.0 is backward compatible with 1.98.0 at the compiled CSS output level; the generated CSS is identical for non-deprecated patterns. Fixing deprecated patterns also produces semantically identical CSS output because the deprecated functions and their module replacements compute the same values.

### Resource impact
This is a build-time change only. The compiled static output size is unchanged. There is zero runtime memory or CPU impact on the `admins` Kubernetes tenant. The `labs` tenant is unaffected.

### Risks and mitigations
- **Risk:** The SCSS audit misses a deprecated usage that only appears under certain build conditions (e.g., conditional imports).
  **Mitigation:** Run `nuxt build` with `--verbose` or capture the full sass output; treat any remaining warning as a blocker before merging.
- **Risk:** sass 1.99.0 introduces a bug that causes a style regression in the generated CSS.
  **Mitigation:** Visual regression check (task 4) comparing the built site against the current production build before deploying.
- **Risk:** A transitive dependency (e.g., a Nuxt module) imports SCSS that also triggers deprecation warnings.
  **Mitigation:** Warnings from `node_modules` are typically suppressed by Vite's `quietDeps` option already. If a transitive dep's warnings surface, they are suppressed via `silenceDeprecations` for that specific dep and tracked as a separate upstream issue.
