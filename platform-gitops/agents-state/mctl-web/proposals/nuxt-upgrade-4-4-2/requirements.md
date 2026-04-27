# Обновление Nuxt до 4.4.2 и миграция на vue-router v5

## Контекст

Текущий стек использует Nuxt 4.3.1 + vue-router 4.6.4. Nuxt 4.4.2 выпущен 12 марта 2026 и требует vue-router v5; ветка vue-router v4.x объявлена EOL (v4.6.4 — финальный релиз). Откладывание перехода накапливает технический долг: безопасностные патчи и новые фичи Nuxt 4.4+ будут выходить только под vue-router v5.

Для mctl-web с тремя страницами (`/`, `/docs`, `/privacy`) объём необходимых изменений роутинговой конфигурации минимален. Переход также даёт ускорение маршрутизации до 28x (через `unrouting`), типизированные layout props и новый composable `useAnnouncer` для a11y.

## User stories

- AS a developer I WANT to run Nuxt 4.4.2 with vue-router v5 SO THAT the project stays on supported dependency branches and receives future security patches.
- AS a developer I WANT typed layout props and fast routing SO THAT the DX improves and routing bugs are caught at compile time.
- AS a platform operator I WANT critical dependencies (router) to be on a maintained major version SO THAT EOL components do not block future upgrades.

## Acceptance criteria (EARS)

- WHEN the build runs with Nuxt 4.4.2 THE SYSTEM SHALL compile successfully without errors or deprecation warnings related to vue-router v4.
- WHEN a user navigates to `/`, `/docs`, or `/privacy` THE SYSTEM SHALL render the correct page without hydration errors.
- WHEN the prerender step executes THE SYSTEM SHALL generate static HTML for all three prerendered routes (`/`, `/privacy`, `/docs`).
- WHILE vue-router v5 is active THE SYSTEM SHALL preserve all existing route definitions and redirect behaviour of the Cloudflare Worker.
- IF a composable or component uses a vue-router v4-only API THE SYSTEM SHALL be updated to the v5 equivalent before merging.
- WHEN `nuxt build` finishes THE SYSTEM SHALL produce a bundle with no vue-router v4 packages in the dependency graph.

## Out of scope

- Добавление новых страниц или маршрутов.
- Замена vee-validate или yup (запрещено ADR 0001 без конкретного bug/perf-обоснования).
- Изменение Cloudflare Worker (`cloudflare-worker/`) — он не импортирует vue-router.
- Обновление @vueuse/core или sass (уже на актуальных версиях).
