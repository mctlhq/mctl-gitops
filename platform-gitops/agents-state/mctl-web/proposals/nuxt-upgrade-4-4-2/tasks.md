# Tasks: nuxt-upgrade-4-4-2

- [ ] 1. Применить Vue 3.5.33 patch (предложение `vue-patch-3-5-33`) — DoD: `vue` в `package.json` = `^3.5.33`, `nuxt build` проходит без ошибок.
- [ ] 2. Аудит прямых импортов из `vue-router` в кодовой базе — DoD: составлен список файлов с `import ... from 'vue-router'`; для каждого определено, есть ли breaking change в v5 (по официальному migration guide vue-router v5).
- [ ] 3. Обновить `nuxt` до `^4.4.2` и `vue-router` до `^5.0.0` в `package.json` — DoD: `npm install` завершается без ошибок; `package-lock.json` содержит nuxt >= 4.4.2 и vue-router >= 5.0.0.
- [ ] 4. Устранить breaking changes из аудита (зависит от 2, 3) — DoD: все файлы с прямыми импортами vue-router скомпилированы без ошибок TypeScript/Vite.
- [ ] 5. Запустить `nuxt build` и исправить ошибки сборки — DoD: `nuxt build` завершается с кодом 0; директория `dist/` содержит все prerender-страницы (`index.html`, `docs/index.html`, `privacy/index.html`).
- [ ] 6. Проверить совместимость vee-validate с новым стеком — DoD: форма заявки на тенант рендерится без ошибок в браузере; валидация полей работает корректно (зависит от 5).
- [ ] 7. Обновить CI (deploy.yml) при необходимости — DoD: `npm ci && nuxt build` успешно проходит в GitHub Actions; деплой на Cloudflare Pages завершается без ошибок (зависит от 5).
- [ ] 8. Открыть PR, пройти code review и смёрджить — DoD: PR одобрен, все CI-checks зелёные, production-деплой успешен (зависит от 7).

## Тесты

- [ ] T1. `nuxt build` завершается с кодом 0 без предупреждений об устаревшем API vue-router.
- [ ] T2. Prerender: файлы `dist/index.html`, `dist/docs/index.html`, `dist/privacy/index.html` существуют и содержат ожидаемый HTML (не пустые, нет тегов `<nuxt-error>`).
- [ ] T3. Браузерный smoke-тест: навигация `/` → `/docs` → `/privacy` → `/` не вызывает ошибок в консоли браузера.
- [ ] T4. Форма заявки на тенант: заполнение и отправка формы не вызывает JS-ошибок; вee-validate отображает ошибки валидации корректно.
- [ ] T5. Worker endpoints не регрессировали: `GET /api/github/login` возвращает redirect, `POST /api/submit` возвращает 200/422/429 (не 500).
- [ ] T6. `npm audit --audit-level=high` не выводит новых уязвимостей относительно baseline до обновления.

## Откат
1. Вернуть `package.json` к версиям `nuxt: 4.3.1`, `vue-router: 4.6.4`, `vue: 3.5.30`.
2. Запустить `npm install` для восстановления lock-файла.
3. Если изменения уже задеплоены на Cloudflare Pages — использовать Cloudflare Dashboard → Pages → Deployments → выбрать предыдущий deployment → "Rollback to this deployment".
4. Смёрджить hotfix-ветку в main для восстановления CI-пайплайна.
