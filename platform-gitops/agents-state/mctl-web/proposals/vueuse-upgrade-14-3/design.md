# Design: vueuse-upgrade-14-3

## Current state
`@vueuse/core` is pinned at `14.2.1` in `package.json` (confirmed in `context/architecture.md`).
It is used throughout the Nuxt 4 frontend as the composables library for reactive browser-API
abstractions. The Nuxt/Vite build resolves the package at build time; no version is pinned in
`wrangler.toml` or any Worker config — this change is purely frontend.

## Proposed solution
Bump the `@vueuse/core` version specifier in `cloudflare-worker/../package.json` (the Nuxt app's
`package.json`) from `14.2.1` to `^14.3.0` (or `14.3.0` exact if the project uses exact pins).
Run `npm install` to regenerate `package-lock.json` and commit both files together.

**Why this approach:**
- A minor semver bump with no documented breaking changes requires no source-code changes.
- The `^14.3.0` range allows patch-level fixes within 14.3.x to be picked up automatically on
  the next `npm install`, which is standard practice for non-security-critical frontend libraries.
- No Nuxt module configuration, Vite plugin, or composable call site needs to change.

## Alternatives

### A — Stay on 14.2.1 until a security advisory forces an upgrade
Rejected. Accumulating known bug-fix debt (useWebSocket, useWakeLock) for no gain increases the
delta of a future forced upgrade and risks running known-buggy composable code in production.

### B — Upgrade to @vueuse/core 15.x (next major, not yet released)
Not applicable today; 15.x does not exist as of this writing. Track in a future daily cycle.

### C — Replace @vueuse/core with custom composables
Rejected per ADR 0001's principle of staying within the accepted Nuxt/Vue ecosystem stack.
Removing a well-maintained shared library for custom implementations increases maintenance burden
with no architectural benefit.

## Platform impact

**Migrations:** None. No API surface changed between 14.2.1 and 14.3.0.

**Backward compatibility:** Full. The 14.x API contract is preserved. Existing SFC composable
call sites (`useXxx()`) require no modification.

**Resource impact:** Negligible. @vueuse/core is tree-shaken by Vite at build time; the delta
between 14.2.1 and 14.3.0 bundle sizes is not measurable in practice. No impact on Kubernetes
tenant memory for `admins` or `labs` — this is a static-site build dependency only.

**Risks and mitigations:**
- *Risk:* An undocumented behavioural change in 14.3.0 breaks a composable used in the form or
  navigation. *Mitigation:* Run the full `nuxt build` and smoke-test the tenant onboarding form
  and all three routes in `wrangler dev` before merging.
- *Risk:* `package-lock.json` drift if other developers run `npm install` before the lock is
  committed. *Mitigation:* Commit both `package.json` and `package-lock.json` atomically.
