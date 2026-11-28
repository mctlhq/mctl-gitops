# Design: agent-crashloop-and-remediation

version-status: unverified, see commit SHA

## Source commits
- mctl-agent:36ffb0d — feat(skill): diagnose crash loops from pod state (+ f8308db, 291012c, 303e055, 7b675cf, 9f637f4)
- mctl-agent:2223296 — fix(skill/fixer): rollback handling (+ 46b076b, edbbac4, e234177)
- mctl-agent:b24f23a — fix(skill): scale_up matches only on an HPA signal
- mctl-agent:5880140 — fix(pipeline/monitor): escalation and ticket lifecycle (+ f18d440, 646e713, 5999c9e, 1fe1e9d)
- mctl-agent:610ba08 — docs: list the builtin skills as they are registered

## Current state of documentation
Existing pages (from docs-tree snapshot 2026-04-27, content not re-read): `docs/platform/components.md`, `docs/reference/troubleshooting.md`, `docs/guides/rollbacks.md`, `docs/guides/scaling.md`. Likely lack the behaviours above.

## Proposed solution
UPDATE four pages with short sections (see proposed-content.md as before/after patches). No new page, no sidebar change.

## Alternatives
- New "Self-healing behaviour" page: dropped, would duplicate content spread across the existing task-oriented pages.
- Only update components.md: dropped, rollback/scaling readers would not find it.

## Impact
- Sidebar: none. Mermaid: none. Versioning: main.
