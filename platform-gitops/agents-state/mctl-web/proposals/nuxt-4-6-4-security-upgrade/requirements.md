# Upgrade Nuxt to 4.6.4 (nitropack 2.13.6)

## Context
Nuxt v4.6.4 (published 02 Nov) is reported to fix about eight Nuxt advisories and, via nitropack 2.13.6, three Nitro advisories. Behaviour changes: production error details are stripped and the dev server gains Host header checks. The inbox also lists CVEs (CVE-2026-128077, -128071, -128074, -128075) that this release is said to address.

All CVE details come from a single source (OpenCVE search) and are UNVERIFIED. They must be confirmed against the official Nuxt GitHub security advisories before being cited in a PR or ADR. Also, the baseline is unclear: `context/architecture.md` and ADR 0001 say Nuxt 4.3.1, while `context/current-version.md` says 4.6.2 (possibly the service version, not Nuxt). The real version must be read from `package.json` and the lockfile.

## Items to verify before implementation
- V1. Nuxt baseline: 4.3.1 (architecture.md) vs 4.6.2 (current-version.md). Confirm from `package.json`/lockfile.
- V2. Each CVE ID, severity, affected range and fixed version against official Nuxt GitHub advisories. Note the inbox says CVE-2026-128071 affects "3.0.0 up to 4.6.4", which conflicts with 4.6.4 being a full fix; confirm whether 4.6.4 fixes it or a later release is needed.
- V3. Whether the prerendered site actually uses affected features (islands, early-404, routeRules).

## User stories
- AS a platform owner I WANT mctl-web on the patched Nuxt release SO THAT known advisories are not shipped in production.
- AS a maintainer I WANT the behaviour changes documented SO THAT no regression surprises us.

## Acceptance criteria (EARS)
- WHEN the baseline Nuxt version is read from `package.json` and lockfile THE SYSTEM SHALL record it in the PR and in the ADR, and the context docs discrepancy SHALL be reported.
- WHEN the upgrade is applied THE SYSTEM SHALL resolve `nuxt` to 4.6.4 and `nitropack` to 2.13.6 or later in the lockfile.
- WHEN `nuxt build` runs THE SYSTEM SHALL complete and prerender `/`, `/docs`, `/privacy` without errors.
- WHEN a production request triggers an error THE SYSTEM SHALL NOT expose error details (stack, internals) in the response.
- WHILE running the dev server THE SYSTEM SHALL reject requests with unexpected Host headers per the new checks, and developer docs SHALL note this.
- IF an advisory cannot be confirmed in the official Nuxt advisories THEN THE SYSTEM SHALL NOT cite it in the ADR as fact and SHALL mark it unverified.
- WHEN the upgrade merges THE SYSTEM SHALL update `context/current-version.md` and add an ADR (done by a human or the owning process, as `context/` is read-only for this agent).
- WHEN Vue core 3.5.45 is compatible with the resolved Nuxt THE SYSTEM MAY include it in the same dependency refresh.

## Out of scope
- vue-router 5.x, vueuse 15, sass bump, vee-validate/yup changes.
- Worker toolchain (see worker-toolchain-bump-compat-date).
- New regression tests (see nuxt-path-confusion-regression-tests).
- Any change to tenant `labs`.
