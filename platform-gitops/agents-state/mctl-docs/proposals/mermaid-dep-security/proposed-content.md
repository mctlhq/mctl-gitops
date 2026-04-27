# Proposed content: mermaid-dep-security

> **Apply to (A):** `context/decisions/0002-mermaid-dep-security.md` — CREATE
> **Apply to (B):** `mctl-docs/docs/reference/troubleshooting.md` — UPDATE (add section)
> **Source:** CVE-2026-4800, CVE-2026-2950 (lodash-es dep of mermaid 11.x); no sibling-repo commit SHA — signal from public CVE advisories.
> **version-status: unverified** (mcp__mctl__* unavailable; confirm mermaid version in production before applying).

---

## (A) CREATE: `context/decisions/0002-mermaid-dep-security.md`

```markdown
# 0002. Mermaid Dependency Security — lodash-es CVE Mitigation

**Status:** proposed
**Date:** 2026-04-27

## Context

mctl-docs bundles mermaid 11.x for rendering architecture and platform diagrams in docs.mctl.ai.
Mermaid 11.x has a transitive dependency on lodash-es, which carries two known vulnerabilities
as of 2026-04-27:

- **CVE-2026-4800** — lodash-es < 4.18.1 (specific vector: <TODO: confirm with CVE author>)
- **CVE-2026-2950** — lodash-es < 4.18.1 (specific vector: <TODO: confirm with CVE author>)

A patched version (lodash-es 4.18.1) exists, but mermaid has not yet updated its dependency.

**Attack surface assessment:**
docs.mctl.ai is a static site (VitePress SSG output). No user-supplied content is rendered.
Mermaid diagrams are authored exclusively by platform engineers in reviewed PRs.
The real-world exploitability of these CVEs against a static docs site is assessed as **low**.

## Decision

1. Pin `lodash-es` to `^4.18.1` via `package.json` `overrides` field immediately as a temporary
   mitigation:
   ```json
   {
     "overrides": {
       "lodash-es": "^4.18.1"
     }
   }
   ```
2. Monitor mermaid releases for a version that natively ships lodash-es ≥ 4.18.1.
   Once available, remove the `overrides` pin and upgrade mermaid.
3. Re-evaluate when CVE details (attack vector) are fully published.

## Consequences

- **+** `npm audit` clean for CVE-2026-4800, CVE-2026-2950 after pin.
- **+** No user-facing change — purely a dependency version constraint.
- **−** `overrides` pin may conflict with future mermaid major version bump — requires manual review at next mermaid upgrade.
- **−** If lodash-es 4.18.1 introduces breaking changes for mermaid internals, diagrams may render incorrectly — covered by build test (T1) and visual check (T3).
```

---

## (B) UPDATE: `docs/reference/troubleshooting.md` — add section

**Before** (end of existing file):

```markdown
<!-- existing content ends here -->
```

**After** — append the following section:

```markdown
## Known dependency advisories

The table below tracks security advisories in mctl-docs' own dependency tree.
For each advisory, a decision record (ADR) documents our mitigation strategy.

| CVE | Affected package | Status | Decision |
|-----|-----------------|--------|----------|
| CVE-2026-4800 | lodash-es < 4.18.1 (via mermaid) | Mitigated (overrides pin) | [ADR 0002](/decisions/0002-mermaid-dep-security) |
| CVE-2026-2950 | lodash-es < 4.18.1 (via mermaid) | Mitigated (overrides pin) | [ADR 0002](/decisions/0002-mermaid-dep-security) |

> **Note:** These advisories affect the docs site's JavaScript bundle, not the mctl platform itself.
> The real-world risk to readers of docs.mctl.ai is assessed as low (static site, no user input).
> See the linked ADR for full rationale.
```

---
