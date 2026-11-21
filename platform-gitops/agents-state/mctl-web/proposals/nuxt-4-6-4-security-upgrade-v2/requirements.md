# Upgrade Nuxt to 4.6.4

## Context
Nuxt 4.6.4 (2 Nov 2026) fixes advisories CVE-2026-128077, -128071, -128074, -128075 and others, and bumps nitropack to 2.13.6. Earlier proposals for this upgrade exist; this one re-confirms it against the current release.

## User stories
- AS a platform owner I WANT this change SO THAT mctl.ai stays secure and maintainable

## Acceptance criteria (EARS)
- WHEN the build runs THE SYSTEM SHALL use nuxt >= 4.6.4 and nitropack >= 2.13.6.
- WHEN a server render error occurs in production THE SYSTEM SHALL expose only createError message/data.
- WHEN a request path begins with // or contains %2F THE SYSTEM SHALL apply route rules consistently.
- IF the build or prerender fails THEN THE SYSTEM SHALL block deployment.

## Out of scope
- vue-router 5 / vueuse 15 migrations
- Changes to tenant `labs`
