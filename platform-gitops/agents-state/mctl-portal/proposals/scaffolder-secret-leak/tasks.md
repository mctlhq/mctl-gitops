# Tasks: scaffolder-secret-leak

Примечание: задачи 1–5 полностью совпадают с задачами `scaffolder-path-traversal`,
так как оба CVE закрываются одним PR. Если предложение `scaffolder-path-traversal`
уже реализовано, задачи 1–5 считаются выполненными для данного proposal тоже.

- [ ] 1. Обновить `@backstage/backend-defaults` до ^0.12.2 и `plugin-scaffolder-backend`
  до ^3.1.1 в `packages/backend/package.json` и корневом `package.json` (единый PR с
  `scaffolder-path-traversal`) — DoD: `yarn install` завершается без ошибок; в `yarn.lock`
  зафиксированы версии >= 0.12.2 и >= 3.1.1; `yarn backstage-cli versions:check` без
  peer-конфликтов.

- [ ] 2. Выполнить `yarn backstage-cli repo build` (зависит от 1) — DoD: сборка
  завершается без TypeScript-ошибок.

- [ ] 3. Запустить playwright smoke-тест шаблона создания сервиса в staging (зависит от
  2) — DoD: тест проходит; onboarding-форма работает корректно.

- [ ] 4. Собрать Docker-образ и обновить тег в ArgoCD-манифесте тенанта `admins` (зависит
  от 3) — DoD: ArgoCD статус `Synced` и `Healthy`.

- [ ] 5. Запустить `yarn audit --level high` (зависит от 4) — DoD: нет high/critical CVE
  по CVE-2026-32237 и CVE-2026-24046.

- [ ] 6. Инициировать ротацию всех секретов, смонтированных в backend-pod через
  ExternalSecret (зависит от 4) — DoD: новые значения Vault token, Postgres DSN, GitHub
  App credentials записаны в Vault; ExternalSecret обновил Kubernetes Secret; pod
  перезапущен с новыми секретами; old credentials отозваны.

## Тесты

- [ ] T1. Интеграционный тест: вызвать dry-run endpoint с шаблоном, который явно
  обращается к `process.env.VAULT_TOKEN` — убедиться, что в ответе значение заменено на
  `[REDACTED]`, а не возвращено в открытом виде.
- [ ] T2. Интеграционный тест: dry-run ответ с вложенным JSON-объектом, содержащим ключ
  `credentials` с чувствительным значением — убедиться в рекурсивной редакции.
- [ ] T3. Smoke-тест: dry-run легитимного шаблона (без обращения к секретам) возвращает
  корректный preview без `[REDACTED]` в несекретных полях.
- [ ] T4. `yarn audit` в CI должен фейлить билд при severity >= high.

## Откат
1. Восстановить предыдущий тег Docker-образа в ArgoCD-манифесте тенанта `admins`.
2. Выполнить `argocd app sync mctl-portal --prune`.
3. Уязвимость CVE-2026-32237 возвращается; как временная митигация — отключить dry-run
   endpoint через Backstage permission framework (запретить действие
   `scaffolder.template.parameter.read` для всех групп).
4. Если ротация секретов (задача 6) уже выполнена — откат её не требуется; новые
   credentials остаются в силе.
