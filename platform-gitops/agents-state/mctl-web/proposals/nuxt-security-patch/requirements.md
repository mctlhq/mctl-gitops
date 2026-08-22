# Upgrade Nuxt past 4.5.1 to close four CVEs

## Context
Our pinned Nuxt version is 4.3.1 (see `context/architecture.md`). Four CVEs affecting
Nuxt versions below 3.21.10 / 4.5.1 were reported: a server-side RCE via runtime
template injection through `/__nuxt_island/` props (CVE-2026-71320), a CPU-exhaustion
DoS via oversized POST bodies to the island renderer, an SSR memory-exhaustion DoS via
an unbounded server-island `v-for` prop, and an incomplete-fix follow-up where
mixed-case `routeRules` keys can bypass `appMiddleware` authorization gates. All four
are fixed in Nuxt 3.21.10 / 4.5.1; our pin is below the fixed version on every one of
them.

mctl-web runs Nuxt in SSR mode with prerender for `/`, `/privacy`, and `/docs`, and it
is our core framework per ADR 0001 — this proposal is a version bump within that
existing architecture, not a framework change.

## User stories
- AS a platform operator I WANT Nuxt upgraded past the CVE-fixed version SO THAT
  mctl-web is not exposed to unauthenticated RCE, DoS, or auth-bypass vectors.
- AS a site visitor I WANT the public site to remain available and my requests
  correctly authorized SO THAT I am not affected by a DoS or an auth-bypass incident.

## Acceptance criteria (EARS)
- WHEN the Nuxt dependency is upgraded THE SYSTEM SHALL run Nuxt version 4.5.1 or
  higher within the 4.x line.
- WHEN the build pipeline runs after the upgrade THE SYSTEM SHALL successfully
  prerender `/`, `/privacy`, and `/docs` with no build errors.
- WHEN a request is sent to `/__nuxt_island/...` with an oversized or malformed JSON
  body after the upgrade THE SYSTEM SHALL reject or safely bound the request without
  unbounded CPU or memory consumption.
- WHEN a `routeRules` key differs only in case from a configured `appMiddleware` rule
  THE SYSTEM SHALL apply the authorization gate consistently regardless of case.
- IF `vue.runtimeCompiler` is enabled anywhere in `nuxt.config.ts` THEN THE SYSTEM
  SHALL treat it as a flag to double-check during the upgrade review, since it is the
  vector for CVE-2026-71320.
- WHILE the upgrade is in progress THE SYSTEM SHALL keep vee-validate, yup, and
  @vueuse/core pinned at their current versions unless the Nuxt upgrade forces a peer
  dependency bump.
- IF the peer dependency resolution requires bumping Vue or vue-router THEN THE SYSTEM
  SHALL document the forced bump explicitly in the ADR rather than upgrading them
  silently.

## Out of scope
- Upgrading Vue core, vue-router, vee-validate, yup, @vueuse/core, or sass unless
  strictly required as a peer dependency of the Nuxt bump (ADR 0001 protects the
  vee-validate+yup pairing from unrelated changes).
- Any framework replacement or reverting to vanilla HTML (explicitly rejected by
  ADR 0001).
- Investigating the vue-router v5.x major release noted in the inbox — that is a
  separate, unrelated evaluation.
