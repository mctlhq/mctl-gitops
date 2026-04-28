# Design: mermaid-dep-security

## Source commits
- n/a — signal from CVE advisories, not a git commit in sibling repos
- CVE-2026-4800: lodash-es vulnerability (version-status: unverified, see advisory published ~2026-04)
- CVE-2026-2950: lodash-es vulnerability (version-status: unverified, see advisory published ~2026-04)
- Reference: https://security.snyk.io/package/npm/mermaid

## Current documentation state
- `docs/security/authentication.md` — covers platform auth/JWT/OAuth; does not concern docs-site dependencies.
- `docs/security/authorization.md` — platform RBAC; likewise not relevant.
- `docs/reference/troubleshooting.md` — exists, but has no section on known dependency advisories.
- `context/decisions/` — only 0001-vitepress-stack.md is present; no explicit ADR on dependency security.
- **Conclusion:** the page is missing; the CVE decision is not documented anywhere.

## Proposed solution

Two artefacts:

### A. New ADR: `context/decisions/0002-mermaid-dep-security.md`
An internal (read-only) ADR capturing:
- Description of CVE-2026-4800 and CVE-2026-2950 in lodash-es.
- Attack-surface assessment (static site, no user input → low real-world risk).
- Decision: upgrade mermaid to a version ≥ 11.15.0 (or whichever pins lodash-es ≥ 4.18.1)
  as soon as it ships, or pin lodash-es via `overrides` in package.json.
- Decision date and owner.

### B. Add a section to `docs/reference/troubleshooting.md`
A public note "Known dependency advisories" for transparency — a short table of CVE + status + link to ADR.

### Related VitePress config changes
None (purely markdown changes).

## Alternatives

1. **ADR only, no public note** — hides information from tenant auditors; rejected: transparency matters.
2. **Replace mermaid with a different renderer** — violates ADR 0001 (high migration cost); rejected.

## Impact
- VitePress sidebar / nav config: not affected (troubleshooting.md is already in the nav).
- Mermaid diagrams: not needed.
- Versioning: no concept of versioning in mctl-docs — the ADR + troubleshooting update apply to the current branch.
