# Design: scaffolder-task-events-ordering-cves

## Current state
See context/architecture.md; portal runs in tenant `admins` on Node 22||24.

## Proposed solution
Extend the acceptance and test list of backstage-security-patch-bundle with these two CVEs; no separate bump needed beyond scaffolder-backend 4.1.0.

## Alternatives
- Do nothing: leaves the exposure/regression open.
- Opt out via dangerous/ignore flags: rejected, weakens hardening.

## Platform impact
- Migrations: none.
- Backward compatibility: patch/minor level only.
- Resource impact: negligible; `labs` unaffected (portal is in `admins`).
- Risks: regressions; mitigated by tests and rollback below.
