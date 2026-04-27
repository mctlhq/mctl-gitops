# Обновление Vue до 3.5.33

## Контекст

Продакшн использует Vue 3.5.30, выпущен в феврале 2025. Актуальная версия — Vue 3.5.33 (выпущена 22 апреля 2026). Это патч-релиз в рамках ветки v3.5.x, без объявленных breaking changes. Патч-версии Vue обычно содержат исправления регрессий, улучшения типизации и минорные performance-фиксы.

Обновление до 3.5.33 является обязательной гигиеной зависимостей и рекомендуется сделать до более крупного обновления Nuxt/vue-router, чтобы изолировать потенциальные источники проблем.

## User stories

- AS a developer I WANT Vue to be on the latest patch version SO THAT known bugs and regressions are fixed without any API changes.
- AS a platform operator I WANT dependencies to be kept current within minor/patch bounds SO THAT security fixes in patch releases are not missed.

## Acceptance criteria (EARS)

- WHEN `nuxt build` runs after the update THE SYSTEM SHALL complete without errors.
- WHEN the application is loaded in a browser THE SYSTEM SHALL produce no Vue-related console errors or hydration warnings.
- WHILE Vue 3.5.33 is active THE SYSTEM SHALL maintain all existing functionality of pages `/`, `/docs`, `/privacy` and the tenant form.
- IF Vue 3.5.34 or later is released THE SYSTEM SHALL be updated in the next daily cycle as part of regular dependency maintenance.

## Out of scope

- Использование новых Vue 3.5.x API, появившихся между .30 и .33.
- Изменение компонентной архитектуры.
- Обновление vueuse/core или vue-router (отдельные задачи).
