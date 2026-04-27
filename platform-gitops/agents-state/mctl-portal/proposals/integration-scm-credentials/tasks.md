# Tasks: integration-scm-credentials

- [ ] 1. Выполнить `yarn backstage-cli versions:bump --release 1.50.3` в корне монорепо —
  DoD: все `@backstage/*` пакеты обновлены до версий из манифеста релиза 1.50.3; в том
  числе `@backstage/integration` >= 1.20.1; `yarn.lock` обновлён; `yarn install`
  завершается без ошибок.

- [ ] 2. Запустить `yarn backstage-cli versions:check` и устранить peer-конфликты
  (зависит от 1) — DoD: команда не выдаёт предупреждений о версионных несовместимостях;
  особое внимание — кастомный observability-плагин в `plugins/`.

- [ ] 3. Выполнить `yarn backstage-cli repo build` (зависит от 2) — DoD: TypeScript
  компиляция всех пакетов (`packages/app`, `packages/backend`, `plugins/*`) завершается
  без ошибок.

- [ ] 4. Запустить playwright smoke-тесты в staging (зависит от 3) — DoD: проходят тесты
  для catalog-import (регистрация компонента через URL), scaffolder onboarding-шаблона,
  и github-actions panel (отображение CI статуса).

- [ ] 5. Проверить CHANGELOG Backstage 1.50.3 и community-plugins на deprecated/breaking
  changes (зависит от 1, параллельно с 2–3) — DoD: все используемые API из
  `context/architecture.md` (catalog, scaffolder, kubernetes, techdocs, search,
  github-actions) подтверждены совместимыми или адаптированы.

- [ ] 6. Собрать Docker-образ backend и обновить тег в ArgoCD-манифесте тенанта `admins`
  (зависит от 4 и 5) — DoD: ArgoCD показывает `Synced` и `Healthy`; pod перезапустился
  с новым образом Backstage v1.50.3.

- [ ] 7. Запустить `yarn audit --level high` (зависит от 6) — DoD: нет high/critical CVE
  по CVE-2026-29185.

- [ ] 8. Ротировать GitHub App credentials после деплоя — DoD: новый GitHub App private
  key и App ID записаны в Vault; ExternalSecret обновил Kubernetes Secret; pod
  перезапущен с новыми credentials; старые credentials отозваны в GitHub Organization
  settings; проверен GitHub audit log на подозрительные API-вызовы.

## Тесты

- [ ] T1. Интеграционный тест: подать в catalog-import URL с path-traversal
  последовательностью (`%2F..%2F`) — убедиться, что backend возвращает ошибку валидации
  и не выполняет исходящий запрос к GitHub API.
- [ ] T2. Интеграционный тест: scaffolder git action `publish:github` с `repoUrl`
  содержащим `%252F` (double-encoded) — убедиться в отклонении с ошибкой до отправки
  запроса с token.
- [ ] T3. Smoke-тест: catalog-import с валидным GitHub URL успешно регистрирует компонент.
- [ ] T4. Smoke-тест: scaffolder onboarding-шаблон с валидным `repoUrl` завершается
  успешно.
- [ ] T5. Smoke-тест: github-actions plugin отображает CI статус для зарегистрированного
  компонента.
- [ ] T6. Smoke-тест: кастомный observability-плагин загружает графики Prometheus без
  ошибок.
- [ ] T7. `yarn audit` в CI pipeline фейлит билд при severity >= high.

## Откат
1. Восстановить предыдущий тег Docker-образа в ArgoCD-манифесте тенанта `admins`.
2. Выполнить `argocd app sync mctl-portal --prune` — pod вернётся на Backstage 1.0.1.
3. Уязвимость CVE-2026-29185 возвращается; как временная митигация — отключить
   catalog-import и ограничить scaffolder git actions через Backstage permission
   framework до момента повторного деплоя патча.
4. Если ротация GitHub App credentials (задача 8) уже выполнена — откат её не требуется;
   старые credentials уже отозваны, новые остаются в силе.
