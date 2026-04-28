# Mermaid Dependency Security Advisory Documentation

## Context

Mermaid 11.x (used in docs.mctl.ai via VitePress) transitively depends on lodash-es,
in which vulnerabilities CVE-2026-4800 and CVE-2026-2950 have been disclosed. A fixed
version lodash-es 4.18.1 exists, however as of the run date (2026-04-27) mermaid has not
updated the dependency. docs.mctl.ai bundles mermaid in production and therefore contains
vulnerable code.

Although the attack vector is limited (a static site without user-supplied mermaid input),
the platform must take an explicit decision (patch / pin / accept risk) and document it
for transparency. Source: CVE-2026-4800, CVE-2026-2950 (public advisories as of 2026-04-27).

## User stories

- AS **platform admin** I WANT to know that docs.mctl.ai is not serving vulnerable JavaScript bundles
  SO THAT I can make an informed decision about dependency pinning or upgrading mermaid.
- AS **security auditor** I WANT a documented decision record for known dependency vulnerabilities
  SO THAT I can confirm the risk has been acknowledged and either mitigated or accepted.
- AS **tenant owner** I WANT to trust that docs.mctl.ai does not expose my browser to known CVEs
  SO THAT I can safely use the documentation portal without browser-based risk.

## Acceptance criteria (EARS)

- WHEN a platform admin reads `context/decisions/0002-mermaid-dep-security.md`
  THE SYSTEM SHALL clearly state the CVE identifiers, affected versions, chosen mitigation strategy,
  and the date of the decision.
- IF the decision is "upgrade mermaid to patched version"
  THEN THE SYSTEM SHALL reference the target mermaid version that ships with a fixed lodash-es.
- IF the decision is "accept risk"
  THEN THE SYSTEM SHALL document the rationale (e.g., static site, no user input, limited attack surface).
- WHILE CVE-2026-4800 / CVE-2026-2950 remain unpatched in the mermaid bundle
  THE SYSTEM SHALL display a note in `docs/reference/troubleshooting.md` under "Known dependency advisories"
  linking to the ADR.
- WHEN `vitepress build docs` runs in CI
  THE SYSTEM SHALL not introduce new high-severity vulnerabilities beyond those documented in the ADR.

## Out of scope

- Full vulnerability scan of all npm deps (beyound mermaid/lodash-es).
- Replacing mermaid with an alternative diagramming library.
- Adding Content Security Policy headers (separate infrastructure concern).
- Retroactive security changelog for all past versions of docs.mctl.ai.
