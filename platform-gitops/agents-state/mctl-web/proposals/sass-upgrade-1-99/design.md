# Design: sass-upgrade-1-99

## Current state
`sass 1.98.0` is listed as a direct dev-dependency in `context/architecture.md`. It is invoked
by the Vite/Nuxt build pipeline to compile all `.scss` files in the frontend. The compiler is
not referenced from the Cloudflare Worker or any Kubernetes manifest; it is strictly a
build-time tool.

The companion proposal `sass-deprecation-fix` addresses the deprecation warnings that sass 1.99.0
introduces for CSS-conflicting built-in function names. That proposal assumes sass 1.99.0 is
already installed; this proposal provides the version bump itself.

## Proposed solution
Update the `sass` version specifier in `package.json` from `1.98.0` to `^1.99.0` (or `1.99.0`
exact). Run `npm install` and commit both `package.json` and `package-lock.json`. The change
should be made before or alongside the `sass-deprecation-fix` work so that both land on the
same compiler baseline.

**Recommended sequencing:**
1. Land this proposal (`sass-upgrade-1-99`) first: bump the version, confirm `nuxt build` passes
   with any new deprecation warnings visible in the CI log.
2. Land `sass-deprecation-fix` second: silence the deprecation warnings identified in step 1.

**Why this approach:**
- sass is a build-only dependency — there is no runtime surface to regress.
- Minor semver bump with two additive changes (root `&` support and new deprecation notices);
  no removals or breaking changes documented.
- Keeping the compiler at the current stable release is the lowest-effort way to stay aligned
  with the sass release cadence before a hard-breaking sass 2.0 arrives.

## Alternatives

### A — Wait for sass 2.0 and upgrade in a single jump
Rejected. sass 2.0 will make current deprecation warnings hard errors. A single large jump
creates an unknown number of SCSS files to fix under time pressure. The incremental approach
(1.99.0 now, fix warnings, then 2.0 when stable) is lower risk.

### B — Pin to 1.98.0 indefinitely
Rejected. Accumulates version debt and eventually forces an emergency upgrade when 2.0 ships and
compatibility shims are removed.

### C — Switch SCSS compiler (e.g. to Lightning CSS or postcss-sass)
Rejected per ADR 0001's guidance not to replace established tooling without a specific bug or
performance finding. No such finding exists today.

## Platform impact

**Migrations:** None. The compiled CSS output for existing SCSS files is identical under 1.99.0
unless those files use `&` at document root (new feature, not a regression) or the deprecated
built-in function names (generates a warning, not an error in 1.99.0).

**Backward compatibility:** Full for the static output served to users. The build artefact
(`dist/`) is unaffected.

**Resource impact:** Zero runtime impact. Build time delta is negligible (sass compiler binary
size difference between patch versions is under 1 MB). No memory or CPU impact on `admins` or
`labs` Kubernetes tenants.

**Risks and mitigations:**
- *Risk:* An SCSS file in the repo uses a pattern that triggers a new deprecation warning,
  causing CI to emit noise or (in strict mode) fail the build. *Mitigation:* Review CI output
  after the bump and coordinate with `sass-deprecation-fix` to resolve warnings promptly.
- *Risk:* Vite's sass integration has a version constraint that conflicts with 1.99.0.
  *Mitigation:* Verify `vite` peer-dependency range against sass 1.99.0 before merging; the
  Nuxt 4 / Vite ecosystem is expected to be compatible with sass 1.99.x.
