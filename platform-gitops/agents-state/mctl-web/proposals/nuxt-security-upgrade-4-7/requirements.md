# Upgrade Nuxt to a patched release (>=4.6.4, target 4.7.x)

## Context
Nuxt advisories CVE-2026-128071 and CVE-2026-119200 allow route-rule/auth-middleware bypass via encoded slashes on catch-all pages, and CVE-2026-119201 exposes the dev appSecret in 4.6.0-4.6.2. Nuxt 4.7.0 (23 Nov) also fixes GHSA-jxc9-w3j6-pwp2 and GHSA-vrh2-cfcx-c3fg.

## User stories
- AS a platform owner I WANT nuxt, @nuxt/nitro-server and @nuxt/vite-server upgraded to patched versions SO THAT the public site stays secure and maintainable.

## Acceptance criteria (EARS)
- WHEN the dependency tree is installed THE SYSTEM SHALL resolve nuxt, @nuxt/nitro-server and @nuxt/vite-server to >=4.6.4 (target 4.7.x).
- WHEN a request path contains %2F or %2e segments THE SYSTEM SHALL not serve a page that bypasses route-keyed rules or headers.
- IF the build or prerender fails THEN THE SYSTEM SHALL block the deploy.

## Out of scope
- Nitro v3 and other experimental 4.7 features.
