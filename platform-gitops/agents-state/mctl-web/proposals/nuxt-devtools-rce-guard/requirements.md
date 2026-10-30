# Guard against Nuxt DevTools RCE (CVE-2026-71319)

## Context
CVE-2026-71319 (CVSS 9.6) allows unauthenticated command execution via the DevTools RPC over the Vite HMR WebSocket in @nuxt/devtools < 3.3.1. Exposure is dev-only, but dev servers can be reachable on shared hosts or tunnels.

## User stories
- AS a maintainer I WANT DevTools patched and disabled outside local dev SO THAT no dev-time RCE path exists.

## Acceptance criteria (EARS)
- WHEN dependencies are installed THE SYSTEM SHALL resolve @nuxt/devtools to >= 3.3.1.
- WHILE building for production THE SYSTEM SHALL have devtools disabled.
- IF the lockfile resolves @nuxt/devtools < 3.3.1 THEN THE CI SHALL fail.

## Out of scope
- Nuxt core upgrade (see nuxt-upgrade-4-6-2).
