# Design: playwright-1-65-upgrade

## Current state
Playwright e2e in the yarn workspace (context/architecture.md); exact version not recorded.

## Proposed solution
Bump the dependency, reinstall browsers, run the suite, triage failures against the 1.65 breaking-change list (cookies, ARIA, inert, TS class fields). Add the `failures` reporter alongside the existing one in CI only.

## Alternatives
- Stay on current version: accumulates drift, Node 20 no longer tested upstream (we are on 22/24, so low urgency).
- Adopt Bun runner: unsupported watch mode, unnecessary risk.

## Platform impact
- Migrations: snapshot updates possible.
- Backward compatibility: dev/CI only, no runtime effect.
- Resource impact: CI only; none on `labs`.
- Risks: flaky tests from browser bumps — mitigate by running the suite 3x before merge.
