# Proposed content: vitepress-upgrade-strategy

> **Apply to (A):** `context/decisions/0003-vitepress-2-upgrade-strategy.md` — CREATE
> **Apply to (B):** `mctl-docs/docs/reference/faq.md` — UPDATE (add Q&A section)
> **Source:** GitHub releases vuejs/vitepress v2.0.0-alpha.16 (2025-01-31), v2.0.0-alpha.17 (2025-03-19)
> **version-status: unverified** — confirm current VitePress version in package.json and prod deploy before applying.

---

## (A) CREATE: `context/decisions/0003-vitepress-2-upgrade-strategy.md`

```markdown
# 0003. VitePress 1.6 → 2.x Upgrade Strategy

**Status:** proposed
**Date:** 2026-04-27

## Context

mctl-docs was launched on VitePress 1.6 (ADR 0001, 2026-03-28). As of April 2026,
VitePress 2.0 is at alpha.17 and progressing toward stable release. The v1.6 → v2.x transition
involves breaking changes in sidebar config, theme API, and `config.ts` structure.

Without an explicit upgrade plan, the team risks being caught unprepared when VitePress 2
reaches stable — resulting in rushed migration with limited context.

## Decision

**Do not upgrade to VitePress 2 while it is in alpha or pre-release.**

Begin migration when ALL of the following criteria are met:
1. VitePress 2.x publishes a stable (non-alpha/non-rc) release.
2. No P0 open issues tagged `regression` in the VitePress 2 GitHub tracker.
3. The mermaid VitePress plugin (if used) confirms compatibility with VitePress 2.

**Migration checklist (to execute when criteria are met):**
- [ ] Create a `feat/vitepress-2-migration` branch.
- [ ] Read VitePress 2 CHANGELOG for all breaking changes since 1.6.
- [ ] Update `docs/.vitepress/config.ts` for new sidebar/nav API.
- [ ] Update theme overrides (if any) for v2 theme structure.
- [ ] Verify mermaid renders correctly in dev mode (`npm run dev`).
- [ ] Run `vitepress build docs` — no errors.
- [ ] Deploy to staging, visual QA, then merge to main.

**Review cadence:** Re-evaluate this ADR at each new VitePress 2 alpha/rc release,
or at minimum every 6 months.

## Consequences

- **+** Team has a documented plan — no context loss when VitePress 2 goes stable.
- **+** Clear "go / no-go" criteria prevent premature or delayed upgrade.
- **−** mctl-docs stays on 1.6 for now — no access to VitePress 2-only features.
- **−** The longer the delay past stable release, the larger the migration diff.

## See also

- ADR 0001: VitePress 1.6 selection rationale
- [VitePress 2 CHANGELOG](https://github.com/vuejs/vitepress/blob/main/CHANGELOG.md)
```

---

## (B) UPDATE: `docs/reference/faq.md` — add Q&A block

**Before** (append to existing FAQ entries, or insert at logical position):

_(no existing VitePress version Q&A present)_

**After** — add the following block:

```markdown
## Documentation site

### Which version of VitePress does mctl docs use?

mctl docs currently runs on **VitePress 1.6**. VitePress 2.x is in active alpha development
and will be evaluated for upgrade once it reaches a stable release.

For the full rationale and upgrade criteria, see
[ADR 0003 — VitePress 2.x Upgrade Strategy](https://github.com/mctlhq/mctl-docs/blob/main/context/decisions/0003-vitepress-2-upgrade-strategy.md).
```

---
