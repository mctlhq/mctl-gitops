# Design: techdocs-zensical-evaluation

## Current state
TechDocs serves markdown docs (context/architecture.md); builder uses MkDocs with Material.

## Proposed solution
Time-boxed spike: install `@backstage/plugin-techdocs-backend-module-zensical` and `@techdocs/cli` Zensical support locally/CI, build sample sites, compare rendering, search, build time and memory. Output a report; any adoption would be a separate proposal and possibly an ADR.

## Alternatives
- Do nothing until sunset: risks a rushed migration.
- Pin Material for MkDocs forks: unsupported long-term.

## Platform impact
- Migrations: none in the spike.
- Backward compatibility: experimental module, not enabled in production.
- Resource impact: run builds locally/CI only so `labs` (near its memory limit) is unaffected; measure memory to inform any future cutover.
- Risks: experimental, API may change — keep the spike isolated.
