# Патч-обновление Vue 3.5.30 → 3.5.33

## Контекст
Vue 3.5.33 — последний patch-релиз ветки 3.5.x на момент 2026-04-27. mctl-web использует Vue 3.5.30. Патч-версии в семантическом версионировании содержат только bugfix'ы и не вносят breaking changes, поэтому обновление безрисково и является стандартной гигиеной зависимостей.

Выполнение этого обновления перед обновлением Nuxt до 4.4.2 (предложение `nuxt-upgrade-4-4-2`) обеспечивает чистую базовую линию: если при обновлении Nuxt возникнут проблемы, они не будут смешаны с изменениями в Vue.

## User stories
- AS a developer I WANT Vue updated to the latest patch version SO THAT known bugs fixed in 3.5.31–3.5.33 are resolved and the dependency is current.
- AS a developer I WANT Vue updated before the Nuxt upgrade SO THAT debugging the Nuxt upgrade involves fewer simultaneous variables.

## Acceptance criteria (EARS)
- WHEN `npm install` runs after the change THE SYSTEM SHALL install Vue 3.5.33 (or newer patch in 3.5.x).
- WHEN `nuxt build` runs after the update THE SYSTEM SHALL complete without errors or new warnings.
- WHILE Vue version is 3.5.33 THE SYSTEM SHALL produce identical prerender output for `/`, `/docs`, `/privacy` compared to Vue 3.5.30.
- IF a breaking change is detected during build or tests THE SYSTEM SHALL block the PR and require investigation (this should not occur for a patch update).

## Out of scope
- Обновление Nuxt, vue-router, vee-validate или любых других зависимостей в рамках этого предложения.
- Изменение конфигурации Nuxt или Cloudflare Worker.
- Добавление новых функциональностей.
