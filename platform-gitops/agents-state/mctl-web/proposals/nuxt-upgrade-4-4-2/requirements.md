# Обновление Nuxt до 4.4.2 и vue-router до v5

## Контекст
vue-router v4.6.4 является финальным релизом ветки v4 (EOL). Nuxt 4.4.2 требует vue-router v5, который обеспечивает роутинг до 28x быстрее (за счёт нового движка unrouting), типизированные layout props и composable `useAnnouncer` для улучшения доступности. mctl-web сейчас работает на Nuxt 4.3.1 + vue-router 4.6.4.

Оставаться на EOL-версии vue-router означает отсутствие security patches и новых возможностей. Nuxt 4.4.2 — минорный релиз в рамках мажорной версии 4, что снижает риски breaking changes. Сервис имеет всего 3 страницы (`/`, `/docs`, `/privacy`) и Cloudflare Worker для API, поэтому объём затронутого кода невелик.

## User stories
- AS a developer I WANT mctl-web to run on Nuxt 4.4.2 with vue-router v5 SO THAT I receive security updates and performance improvements for the router.
- AS a site visitor I WANT page navigations to be faster SO THAT the site feels more responsive.
- AS a developer I WANT typed layout props and `useAnnouncer` composable available SO THAT I can build more accessible and type-safe page layouts.

## Acceptance criteria (EARS)
- WHEN `nuxt build` runs after the upgrade THE SYSTEM SHALL complete without errors or warnings about vue-router version incompatibility.
- WHEN a user navigates between `/`, `/docs`, and `/privacy` THE SYSTEM SHALL render the correct page without hydration errors in the browser console.
- WHILE the site is pre-rendered (SSR=true, prerender targets) THE SYSTEM SHALL produce valid HTML for `/`, `/privacy`, `/docs` with HTTP 200.
- IF `vue-router` version in `package.json` is < 5.0.0 THE SYSTEM SHALL fail CI with an explicit error message.
- WHEN the Cloudflare Worker handles requests to `/api/*` THE SYSTEM SHALL continue to respond correctly after the frontend upgrade (no regression).
- WHEN `npm audit` runs after the upgrade THE SYSTEM SHALL report no critical or high vulnerabilities introduced by the new dependencies.

## Out of scope
- Рефакторинг маршрутов или добавление новых страниц.
- Изменение логики Cloudflare Worker.
- Обновление vee-validate, yup, @vueuse/core в рамках этого предложения.
- Переход с SSR на полностью статический (SSG-only) режим.
- Оптимизация Cloudflare Pages конфигурации.
