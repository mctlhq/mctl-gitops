# Tasks: nuxt-upgrade-4-4-2

- [ ] 1. Прочитать официальный migration guide Nuxt 4.3→4.4 и vue-router v4→v5 changelog, зафиксировать список breaking changes применимых к mctl-web. — DoD: список breaking changes задокументирован в PR description.
- [ ] 2. Обновить `nuxt` до `"^4.4.2"` и `vue-router` до `"^5.0.6"` в `package.json`; запустить `npm install` / `pnpm install`. — DoD: lockfile зафиксирован на Nuxt 4.4.x и vue-router 5.x, нет конфликтов peer-зависимостей.
- [ ] 3. Проверить и исправить прямые импорты из `vue-router` во всех `.vue`-файлах и composables (`app/pages/`, `app/components/`, `app/composables/`). — DoD: нет прямых `import ... from 'vue-router'` кроме типов; всё переведено на Nuxt-обёртки или vue-router v5 API.
- [ ] 4. Проверить `nuxt.config.ts` на deprecated опции v4.3 → v4.4; применить необходимые изменения. — DoD: `nuxt build` не выдаёт deprecated-предупреждений.
- [ ] 5. Запустить `nuxt typecheck` — убедиться в отсутствии TypeScript-ошибок. — DoD: exit code 0.
- [ ] 6. Запустить `nuxt generate` — убедиться, что prerender генерирует HTML для `/`, `/docs`, `/privacy`. — DoD: три HTML-файла присутствуют в `dist/`, без ошибок в консоли.
- [ ] 7. Smoke-тест в staging: навигация по всем трём страницам, отправка формы тенанта (вызов `/api/submit`). — DoD: нет консольных ошибок, форма отправляется корректно.
- [ ] 8. Создать и смержить PR; задеплоить через `deploy.yml`. — DoD: prod возвращает корректный HTML для `mctl.ai`, `mctl.ai/docs`, `mctl.ai/privacy`.

## Тесты

- [ ] T1. `nuxt build` завершается с exit code 0.
- [ ] T2. `nuxt typecheck` завершается с exit code 0.
- [ ] T3. `nuxt generate` создаёт HTML для `/`, `/docs`, `/privacy` (проверяется `ls dist/`).
- [ ] T4. В браузере DevTools — нет Vue hydration warnings на всех трёх страницах.
- [ ] T5. `curl https://mctl.ai` возвращает HTTP 200 с корректным HTML после деплоя.
- [ ] T6. `curl https://mctl.ai/docs` и `https://mctl.ai/privacy` — HTTP 200.

## Откат

Восстановить предыдущие версии `nuxt` и `vue-router` в `package.json`, перегенерировать lockfile, пересобрать и задеплоить через `deploy.yml`. Cloudflare Worker не затронут — откат только фронтенда.
