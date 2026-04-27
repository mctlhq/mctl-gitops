# VitePress 1.6 → 2.x Upgrade Strategy Documentation

## Контекст

mctl-docs принял VitePress 1.6 как стек (ADR 0001, 2026-03-28). К апрелю 2026 VitePress 2.x
прошёл итерацию alpha.17 (2025-03-19) и движется к stable release. Текущий ADR фиксирует
выбор 1.6, но не содержит плана перехода на следующий major — создавая риск: когда VitePress 2
выйдет stable, платформа окажется без roadmap и накопит tech debt на миграцию в сжатые сроки.

Нужно ADR с явной upgrade strategy (точки принятия решения, критерии перехода) и краткая
публичная заметка в FAQ о текущем выборе версии — для прозрачности перед tenants и
contributors.

Источник: GitHub releases vuejs/vitepress — v2.0.0-alpha.16 (2025-01-31), v2.0.0-alpha.17 (2025-03-19).

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
