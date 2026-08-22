# Design: nuxt-security-patch

## Current state
Per `context/architecture.md`, mctl-web runs Nuxt 4.3.1 (SSR=true, prerender for `/`,
`/privacy`, `/docs`) with Vue 3.5.30, vue-router 4.6.4, vee-validate 4.15.1 + yup 1.7.1,
and @vueuse/core 14.2.1. The build is `nuxt build` → `dist/` served as static
(Cloudflare Pages / nginx). This stack was chosen in ADR 0001 and is deployed to the
`admins` tenant only.

Four CVEs are fixed in Nuxt 3.21.10 / 4.5.1: an SSR RCE via runtime template injection
through `/__nuxt_island/` props, a CPU-exhaustion DoS on the island renderer, an SSR
memory-exhaustion DoS via server-island `v-for` props, and a `routeRules`
case-sensitivity auth-bypass follow-up. Our pin (4.3.1) predates all four fixes.

## Proposed solution
Bump the `nuxt` dependency in `package.json` from `4.3.1` to `4.5.1` or the latest
patch release in the 4.x line at execution time, resolve any peer dependency shifts
this forces (Vue, vue-router, Nitro), and re-run the full build + prerender pipeline.

Steps:
1. Bump `nuxt` in `package.json`, run the package manager's install/lockfile update.
2. Review `nuxt.config.ts` for `vue.runtimeCompiler` — confirm it is not enabled in
   production config; if it is, evaluate whether it can be disabled entirely (it is
   the vector for CVE-2026-71320).
3. Review `routeRules` config for mixed-case keys that gate `appMiddleware`
   authorization; normalize to lowercase if any are found, independent of the library
   fix, as defense in depth.
4. Rebuild locally and confirm `/`, `/privacy`, `/docs` prerender without errors or
   warnings.
5. Smoke-test SSR behavior and, if reachable in a lower environment, exercise
   `/__nuxt_island/` requests to confirm the fixed behavior.
6. Record the version bump and rationale in a new ADR under `context/decisions/`
   (per the project convention).

This is the minimal-risk path: it stays entirely within the existing Nuxt/Vue stack
that ADR 0001 already committed to, touches only the version pin plus config review,
and does not restructure the app.

## Alternatives
- **Do nothing / accept the risk**: rejected — CVE-2026-71320 is an unauthenticated
  RCE against a public-facing SSR service; the exposure is unacceptable for a service
  reachable at `mctl.ai`.
- **Upgrade only past the minimum fixed version bump without touching config**:
  rejected as insufficient on its own — the `routeRules` case-sensitivity issue is
  described as an "incomplete fix follow-up," so a config-level review (step 3 above)
  is warranted as defense in depth alongside the library fix.
- **Migrate away from Nuxt entirely**: rejected per ADR 0001, which explicitly lists
  "reverting to vanilla HTML / another framework without strong rationale" as
  out-of-scope; a version bump is a proportionate response to a CVE, not grounds for
  a framework migration.

## Platform impact
- **Migrations:** None to data or infrastructure. This is a build-time dependency bump
  plus a re-deploy of the static build output; no database, no schema changes
  (`hasDatabase=false` per mctl service config).
- **Backward compatibility:** Nuxt 4.5.1 is within the same major version (4.x) as our
  current 4.3.1 pin, so no breaking-change migration guide is expected; the plan still
  calls for a full prerender/build verification of all three routes before deploy to
  catch any incidental regressions.
- **Resource impact (labs):** None. mctl-web is deployed only in the `admins` tenant;
  `labs` is not affected by this proposal.
- **Risks and mitigations:**
  - Risk: peer dependency resolution forces an unplanned bump to Vue or vue-router.
    Mitigation: pin explicitly, document the forced bump in the ADR, and re-test.
  - Risk: island rendering or navigation behavior regresses after the bump (the
    researcher's notes mention island-rendering/type-generation/navigation fixes in
    the same release line). Mitigation: manual smoke test of all three prerendered
    routes plus the tenant onboarding form (GitHub OAuth flow) before merging.
  - Risk: deploy window between merge and rollout leaves the RCE window open longer
    than necessary. Mitigation: treat this as a priority-1 patch and merge/deploy as
    soon as build verification passes, ahead of other pending work.
