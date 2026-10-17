# Upgrade Nuxt to 4.6.2

## Context
Nuxt 4.6.2 (2026-10-16) contains the July 2026 security fixes (4.5.1: island RCE, payload disclosure, SSR memory/CPU DoS) and a follow-up making route rules case-insensitive. Documented baseline is 4.3.1.

## User stories
- AS a maintainer I WANT the latest patched Nuxt SO THAT known CVEs are closed.

## Acceptance criteria (EARS)
- WHEN the build runs THE SYSTEM SHALL use nuxt >= 4.6.2.
- WHEN `nuxt build` completes THE SYSTEM SHALL prerender /, /docs and /privacy without errors.
- IF the build or prerender fails THEN THE CI SHALL block the merge.

## Out of scope
- Vue, vue-router v5, vueuse v15 upgrades.
