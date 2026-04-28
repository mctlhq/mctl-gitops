# Design: vitepress-upgrade-strategy

## Source commits
- n/a — signal from GitHub releases (no sibling-repo git SHA)
- vuejs/vitepress@v2.0.0-alpha.17 (2025-03-19) — latest alpha release
- vuejs/vitepress@v2.0.0-alpha.16 (2025-01-31) — previous alpha

## Current documentation state
- Existing ADR: `context/decisions/0001-vitepress-stack.md` — adopted VitePress 1.6, listed
  pros/cons, added constraints (no i18n, no replacing VitePress). **Does not contain** an
  upgrade plan to VitePress 2.
- `docs/reference/faq.md` — exists, but no question about the VitePress version.
- **Conclusion:** a new ADR is needed and a minor FAQ addition.

## Proposed solution

### A. New ADR: `context/decisions/0003-vitepress-2-upgrade-strategy.md`
Documents:
- Current VitePress 2 status (alpha → awaiting stable).
- Criteria for starting the migration: VitePress 2 ships a stable release + no blocker issues.
- Known breaking changes from 1.6 to 2.x: new sidebar config, theme changes, possible
  config-file breaking changes (`config.ts` API).
- Checklist of preparatory steps (create a branch, compare CHANGELOG, update config.ts).
- Review date (proposed: review on every new alpha/rc release, or every 6 months).

### B. Add a Q&A to `docs/reference/faq.md`
A single question: "Which VitePress version does mctl docs use?" with a short answer
(version 1.6, upgrade planned when v2 stable, link to the ADR).

### Related VitePress config changes
None — the proposal only documents the plan, it does not execute it.

## Alternatives
1. **Do not document the upgrade strategy, wait for stable** — risk: when stable arrives, the
   decision context will be lost; rejected.
2. **Move to VitePress 2-alpha now** — violates the stability-first principle from ADR 0001;
   rejected.

## Impact
- VitePress sidebar / nav: not affected (FAQ already exists).
- Mermaid diagrams: not needed.
- Versioning: no concept of versioning — applies to the current branch.
