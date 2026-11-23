# Design: techdocs-markdown-extensions-allowlist

## Current state
See context/architecture.md; portal runs in tenant `admins` on Node 22||24.

## Proposed solution
Audit every mkdocs.yml in the catalog for markdown_extensions, map them to allowlisted names, fix docs, then upgrade to 1.56.5 (as part of backstage-security-patch-bundle) and verify build logs.

## Alternatives
- Do nothing: leaves the exposure/regression open.
- Opt out via dangerous/ignore flags: rejected, weakens hardening.

## Platform impact
- Migrations: none.
- Backward compatibility: patch/minor level only.
- Resource impact: negligible; `labs` unaffected (portal is in `admins`).
- Risks: regressions; mitigated by tests and rollback below.
