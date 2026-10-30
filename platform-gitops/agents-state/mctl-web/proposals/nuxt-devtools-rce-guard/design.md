# Design: nuxt-devtools-rce-guard

## Current state
Nuxt per context/architecture.md; DevTools version unverified.

## Proposed solution
Pin @nuxt/devtools >= 3.3.1 (override if transitive), set `devtools: { enabled: false }` unless NODE_ENV is development, and add a CI check on the lockfile.

## Alternatives
- Remove DevTools entirely: loses DX.
- Rely on Nuxt upgrade only: version coupling, slower.

## Platform impact
- No migration; backward compatible; no runtime or labs memory impact.
- Risk: DX change for devs; mitigated by dev-only enablement.
