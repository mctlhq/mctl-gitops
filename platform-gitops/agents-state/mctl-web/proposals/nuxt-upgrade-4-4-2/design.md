# Design: nuxt-upgrade-4-4-2

## Текущее состояние
Согласно `context/architecture.md`:
- Nuxt 4.3.1 (SSR=true, prerender для `/`, `/privacy`, `/docs`)
- Vue 3.5.30 + vue-router 4.6.4
- Три страницы: `app/pages/index.vue`, `app/pages/docs/index.vue`, `app/pages/privacy/index.vue`
- Cloudflare Worker как отдельный деплой через wrangler (не затрагивается этим предложением)
- Деплой: `nuxt build` → `dist/` → Cloudflare Pages

vue-router 4.6.4 — EOL (финальный релиз ветки v4). Nuxt 4.4.2 переходит на vue-router v5.

## Предлагаемое решение
Обновление в рамках мажорной версии Nuxt 4 (4.3.1 → 4.4.2), которое тянет за собой переход на vue-router v5.

**Шаги обновления:**

1. **Vue 3.5.33** — сначала применить патч-апдейт Vue (см. предложение `vue-patch-3-5-33`) для чистой baseline. Это снижает число переменных при отладке.

2. **Обновить `package.json`:**
   - `nuxt`: `4.3.1` → `^4.4.2`
   - `vue-router`: `4.6.4` → `^5.0.0` (Nuxt 4.4.2 управляет совместимостью)
   - Vue транзитивно подтянется до совместимой версии через Nuxt; явный пин `vue` оставить на `^3.5.33`.

3. **Проверить использование vue-router API в компонентах и composables:**
   - `useRoute()`, `useRouter()`, `navigateTo()` — эти Nuxt-composables абстрагируют vue-router и, как правило, не требуют изменений.
   - Если есть прямые импорты из `vue-router` (например, `RouterLink`, `RouterView`, `createRouter`) — проверить на breaking changes v5. В Nuxt-приложении с 3 страницами и без custom router setup вероятность минимальна.

4. **Запустить `nuxt build`** и устранить предупреждения/ошибки компилятора.

5. **Проверить prerender** — убедиться, что `/`, `/privacy`, `/docs` рендерятся без ошибок.

**Новые возможности (опционально, не в scope этого PR):**
- `useAnnouncer()` — composable для screen reader announcements при навигации.
- Typed layout props — типизация через `definePageMeta`.

## Альтернативы

### 1. Остаться на Nuxt 4.3.1 и vue-router 4.6.4 бессрочно
Отклонено: vue-router v4 EOL означает отсутствие security patches. Технический долг будет только расти.

### 2. Перейти на Nuxt 4.4.2 без явного обновления vue-router (позволить Nuxt управлять версией транзитивно)
Рассматривается как часть основного решения: Nuxt 4.4.2 сам устанавливает совместимый vue-router v5. Явный пин vue-router в package.json нужен только если требуется контроль минорной/патч-версии.

### 3. Перепрыгнуть сразу на следующий мажор Nuxt (если выйдет Nuxt 5)
Отклонено: избыточный риск, нет данных о выходе Nuxt 5 на момент написания. Инкрементальное обновление предпочтительно.

## Влияние на платформу

### Migration/миграции
Нет миграций данных или схем. Изменения только в `package.json`, `package-lock.json` и возможно в компонентах при наличии прямых импортов из `vue-router`.

### Backward compatibility
- Nuxt 4.3.1 → 4.4.2: минорный релиз в мажоре 4. Nuxt придерживается semver; breaking changes в минорных версиях крайне редки и документируются в migration guide.
- vue-router v4 → v5: может содержать breaking changes в API (особенно в `createRouter`, типах, именованных views). Для Nuxt-приложения с 3 простыми страницами риск низкий — прямые вызовы vue-router маловероятны.
- vee-validate 4.15.1 использует vue-router косвенно через Nuxt; проверить совместимость после обновления.

### Resource impact
Не затрагивает тенант labs. Сборка выполняется в CI (GitHub Actions), производительность в тенанте admins не меняется. Возможное уменьшение bundle size за счёт нового движка unrouting.

### Риски и митигации
| Риск | Вероятность | Митигация |
|---|---|---|
| Breaking changes в vue-router v5 API | Средняя | Аудит всех `import ... from 'vue-router'` в кодовой базе перед обновлением |
| Регрессия в prerender `/`, `/docs`, `/privacy` | Низкая | Запустить `nuxt build` локально и проверить `dist/` до merge |
| Несовместимость vee-validate с новым стеком | Низкая | Запустить форму заявки тенанта в staging после обновления |
| Nuxt 4.4.2 тянет Vue >3.5.x с breaking changes | Очень низкая | Проверить peer dependencies Nuxt 4.4.2 перед установкой |
