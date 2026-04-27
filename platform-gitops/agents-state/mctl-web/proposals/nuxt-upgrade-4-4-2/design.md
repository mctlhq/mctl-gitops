# Design: nuxt-upgrade-4-4-2

## Текущее состояние

Согласно `context/architecture.md` и `context/current-version.md`:
- Nuxt **4.3.1** (SSR=true, prerender `/`, `/privacy`, `/docs`)
- Vue **3.5.30**
- vue-router **4.6.4** (EOL — финальная версия ветки v4)
- Три страницы: `app/pages/index.vue`, `app/pages/docs/index.vue`, `app/pages/privacy/index.vue`

vue-router v4.x больше не получает обновлений. Nuxt 4.4.2 включает `unrouting` (ускорение роутинга до 28x) и требует vue-router v5, который включает `unplugin-vue-router` в ядро.

## Предлагаемое решение

**Поэтапный bump зависимостей:**

1. Обновить `nuxt` до `"^4.4.2"` в `package.json`.
2. Убрать явный `vue-router` из `dependencies`/`devDependencies` — Nuxt 4.4.2 транзитивно подтянет vue-router v5; либо явно указать `"vue-router": "^5.0.6"`.
3. Проверить использование vue-router API в страницах и composables:
   - `useRoute()`, `useRouter()`, `navigateTo()` — совместимы с v5 через Nuxt-обёртки.
   - Прямые импорты из `vue-router` (например, `import { RouterLink } from 'vue-router'`) могут потребовать замены на Nuxt-компоненты (`<NuxtLink>`).
4. Обновить `nuxt.config.ts` при наличии deprecated опций (проверить по migration guide Nuxt 4.4).
5. Запустить `nuxt build` и `nuxt generate` для валидации prerender-а.

**Nuxt 4.4.2 новые возможности (опциональные для использования):**
- `useAnnouncer()` — улучшение a11y для SPA-навигации.
- Typed layout props — можно включить постепенно.

## Альтернативы

1. **Оставаться на Nuxt 4.3.1 + vue-router 4.6.4** — EOL, без security-патчей для router. Отброшено: технический долг будет только расти.
2. **Перейти сразу на Nuxt 5 (если существует)** — излишне, Nuxt 4.4.x активно поддерживается и является текущим стабильным. Отброшено: избыточный риск без выгоды.
3. **Использовать `@vitejs/plugin-vue-router` вместо встроенного** — добавляет сложность без необходимости, unplugin-vue-router уже входит в Nuxt 4.4. Отброшено.

## Влияние на платформу

- **Migration/миграции:** изменения только в `app/` (фронтенд), Worker не затронут. Prerender-пути не меняются.
- **Backward compatibility:** vue-router v5 содержит breaking changes в части прямых импортов; Nuxt-обёртки (`useRoute`, `useRouter`, `NuxtLink`) обратно совместимы. Нужна проверка страниц на прямые импорты из `vue-router`.
- **Resource impact:** нулевой для тенантов `labs` и `admins` — это статический фронтенд и Worker, не подовые workloads в k8s.
- **Риски и митигации:** основной риск — breaking change в vue-router v5 API. Митигация: запуск `nuxt typecheck` + тест prerender'а в staging. Бундл может незначительно измениться в размере из-за нового `unrouting` модуля — это приемлемо.
