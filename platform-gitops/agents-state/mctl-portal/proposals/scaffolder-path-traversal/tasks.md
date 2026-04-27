# Tasks: scaffolder-path-traversal

- [ ] 1. Обновить `@backstage/backend-defaults` до ^0.12.2 и `plugin-scaffolder-backend`
  до ^3.1.1 в `packages/backend/package.json` и корневом `package.json` — DoD: `yarn
  install` завершается без ошибок; `yarn backstage-cli versions:check` не выдаёт
  peer-конфликтов; в `yarn.lock` зафиксированы версии >= 0.12.2 и >= 3.1.1 соответственно.

- [ ] 2. Выполнить `yarn backstage-cli repo build` (зависит от 1) — DoD: сборка
  завершается без TypeScript-ошибок и warning'ов об устаревшем API.

- [ ] 3. Запустить playwright smoke-тест шаблона создания сервиса в staging-окружении
  (зависит от 2) — DoD: тест проходит; scaffolder успешно создаёт тестовый компонент
  через onboarding-форму.

- [ ] 4. Собрать новый Docker-образ backend и обновить тег в ArgoCD-манифесте тенанта
  `admins` (зависит от 3) — DoD: ArgoCD показывает статус `Synced` и `Healthy`; pod
  перезапустился с новым образом.

- [ ] 5. Запустить `yarn audit --level high` против production lockfile (зависит от 4) —
  DoD: нет критических или высоких CVE по CVE-2026-24046 и CVE-2026-32237.

## Тесты

- [ ] T1. Интеграционный тест: загрузить в scaffolder архив, содержащий symlink вида
  `../../../../etc/passwd`, и убедиться, что scaffolder возвращает ошибку шага, не
  создавая файл за пределами workspace.
- [ ] T2. Интеграционный тест: вызвать `fs:delete` с path `../../secret`, убедиться,
  что action завершается с ошибкой `path traversal detected`, файл вне workspace не
  затронут.
- [ ] T3. Smoke-тест: полный прогон шаблона создания сервиса (стандартный onboarding)
  должен завершаться успешно без регрессий.
- [ ] T4. `yarn audit` в CI pipeline должен фейлить билд при наличии CVE severity >= high.

## Откат
1. Восстановить предыдущий тег Docker-образа в ArgoCD-манифесте тенанта `admins`.
2. Выполнить `argocd app sync mctl-portal --prune` — pod вернётся на старую версию.
3. Уязвимость при этом возвращается; как временная митигация — отключить доступ к
   scaffolder через Backstage permission framework (запретить роль `scaffolder.template.execute`
   для всех групп до момента повторного деплоя патча).
