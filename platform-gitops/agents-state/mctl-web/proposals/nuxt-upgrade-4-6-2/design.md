# Design: nuxt-upgrade-4-6-2

## Current state
Nuxt 4.x per context/architecture.md; static prerender, Worker handles /api/*.

## Proposed solution
Bump nuxt to ~4.6.2 with lockfile refresh, run build, diff prerendered output, and update context docs via a separate doc proposal.

## Alternatives
- Stay on 4.4.x/4.5.x: leaves fixes from later patches unapplied.
- Wait for 4.7: leaves known CVEs open.

## Platform impact
- Migration: none expected (patch/minor within 4.x).
- Prerendered static output means the island/SSR CVEs have low exposure, but the upgrade is cheap.
- No labs impact. Risk: minor regressions; mitigated by prerender diff.
