# VitePress 1.6 → 2.x Upgrade Strategy Documentation

## Context

mctl-docs adopted VitePress 1.6 as its stack (ADR 0001, 2026-03-28). By April 2026 VitePress 2.x
has reached the alpha.17 iteration (2025-03-19) and is moving toward a stable release. The
existing ADR captures the choice of 1.6 but does not contain a plan for moving to the next
major — creating a risk: when VitePress 2 reaches stable, the platform will be without a
roadmap and accumulate tech debt around a rushed migration.

We need an ADR with an explicit upgrade strategy (decision points, transition criteria) and
a short public note in the FAQ about the current version choice — for transparency to
tenants and contributors.

Source: GitHub releases vuejs/vitepress — v2.0.0-alpha.16 (2025-01-31), v2.0.0-alpha.17 (2025-03-19).

## User stories

- AS **platform maintainer** I WANT a documented upgrade decision record for VitePress 2.x
  SO THAT when VitePress 2 goes stable I can execute migration without scrambling for context.
- AS **documentation contributor** I WANT to know which VitePress version mctl-docs targets
  SO THAT I can use the correct API and component syntax when writing or reviewing doc PRs.
- AS **tenant owner** I WANT to understand why the docs portal might look or behave differently
  after a major upgrade SO THAT I am not surprised by UI changes.

## Acceptance criteria (EARS)

- WHEN a platform maintainer reads `context/decisions/0003-vitepress-2-upgrade-strategy.md`
  THE SYSTEM SHALL list concrete criteria for triggering the upgrade (e.g., "VitePress 2 reaches stable release").
- WHEN a contributor reads `docs/reference/faq.md`
  THE SYSTEM SHALL answer "What version of VitePress does mctl-docs use?" with the current version
  and a pointer to the ADR for upgrade context.
- IF VitePress 2 stable is released
  THEN THE SYSTEM SHALL reference the ADR checklist so the migration can begin without new research.
- WHILE VitePress 2 is in alpha/pre-release
  THE SYSTEM SHALL explicitly state "do not upgrade to VitePress 2 until stable" in the ADR.

## Out of scope

- Actual VitePress 2 migration (code changes, theme updates) — this is a planning/documentation proposal only.
- Replacing VitePress with a different tool (blocked by ADR 0001).
- VitePress 2 theme customisation decisions (future ADR after stable release).
- i18n support (blocked by ADR 0001).
