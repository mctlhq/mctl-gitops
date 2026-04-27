# Design: integration-scm-credentials

## Текущее состояние
Согласно `context/architecture.md`, mctl-portal работает на Backstage версии, указанной
в root `package.json` как `1.0.1`. Пакет `@backstage/integration` в этой версии содержит
уязвимость CVE-2026-29185: при формировании запросов к SCM API URL передаётся без
декодирования и нормализации path-traversal последовательностей. Это позволяет
аутентифицированному пользователю через catalog-import форму, scaffolder git action или
github-actions plugin подставить URL вида
`https://api.github.com/repos/org/repo%2F..%2F..%2F../evil-org/evil-repo`, который
резолвится в произвольный GitHub API endpoint с серверным GitHub App token.

Затронутые точки:
- `catalog-import` — форма регистрации нового сервиса принимает URL репозитория.
- Scaffolder git actions (`fetch:plain`, `publish:github`, и др.) — принимают `repoUrl`
  от пользователя.
- `github-actions` plugin — подставляет `repoUrl` из каталога.

## Предлагаемое решение

### Обновление Backstage до v1.50.3
Фикс CVE-2026-29185 входит в `@backstage/integration` v1.20.1, которая является частью
Backstage v1.50.3. Подход — мажорное обновление Backstage через стандартный backstage-cli
upgrade process:

```bash
yarn backstage-cli versions:bump --release 1.50.3
```

Команда обновляет все `@backstage/*` пакеты до версий, задекларированных в манифесте
релиза 1.50.3, включая `@backstage/integration` v1.20.1.

После обновления:
1. Запустить `yarn backstage-cli versions:check` — убедиться в отсутствии peer-конфликтов.
2. Выполнить `yarn backstage-cli repo build` — проверить TypeScript-совместимость.
3. Запустить playwright smoke-тесты: catalog-import, scaffolder onboarding, github-actions
   panel.
4. Собрать Docker-образ; ArgoCD sync в тенанте `admins`.

Апстрим-фикс в `@backstage/integration` v1.20.1 добавляет нормализацию URL перед
добавлением auth-заголовков: `decodeURIComponent` + `URL` constructor с проверкой
hostname против списка сконфигурированных SCM-интеграций. Запросы к хостам вне списка
не получают credentials.

### Связь с другими предложениями
`scaffolder-path-traversal` и `scaffolder-secret-leak` обновляют
`plugin-scaffolder-backend` до 3.1.1+. Backstage v1.50.3 совместим с этой версией
(3.1.1 входит в линейку v1.50.x). Все три предложения могут быть выполнены в одном
большом PR или в двух последовательных:
- PR 1: `backend-defaults` 0.12.2 + `plugin-scaffolder-backend` 3.1.1 (быстрый, Effort:2).
- PR 2: Backstage 1.50.3 (более широкий апгрейд, требует дополнительного тестирования).

Рекомендуется именно такой порядок: сначала закрыть два scaffolder CVE (меньший риск
регрессии), затем поднять Backstage целиком.

## Альтернативы

**A. Точечно обновить только `@backstage/integration` до 1.20.1 без апгрейда всего
Backstage**
Теоретически возможно через `yarn up @backstage/integration@^1.20.1`. Однако пакеты
Backstage сильно взаимозависимы по peer-версиям; рассинхронизация версий пакетов
создаёт риск скрытых несовместимостей. Backstage рекомендует обновлять все пакеты
консистентно через `versions:bump`. Отклонено.

**B. Добавить собственную валидацию URL в middleware перед передачей в `@backstage/integration`**
Потребует поддержки кастомного кода для обработки всех точек входа (catalog-import API,
scaffolder actions, github-actions plugin). Высокий риск пропустить один из путей.
Апстрим-патч надёжнее. Отклонено.

**C. Ограничить доступ к catalog-import и scaffolder для всех пользователей до патча**
Нарушает core-функциональность портала. Приемлемо как краткосрочная митигация, но не
как основное решение. Отклонено как единственная мера.

## Влияние на платформу

### Migration/миграции
Backstage 1.50.3 — minor/patch обновление в рамках semver-политики backstage. Ломающих
изменений в публичном API не ожидается. Необходимо проверить CHANGELOG backstage на
предмет deprecated API, используемых в кастомном observability-плагине.

### Backward compatibility
Все стандартные плагины (`catalog`, `scaffolder`, `kubernetes`, `techdocs`, `search`,
`github-actions`) совместимы с v1.50.3 согласно backstage release notes. Кастомный
observability-плагин требует проверки на TypeScript-совместимость (задача 2).

### Resource impact
Обновление Backstage не добавляет новых сервисов или значительных зависимостей.
Потребление памяти backend-pod не должно существенно измениться. Тенант `labs` не затронут
(Backstage развёрнут только в `admins`).

### Риски и митигации
| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| GitHub App token уже скомпрометирован до патча | Неизвестна | Ротировать GitHub App credentials после деплоя; проверить GitHub audit log на подозрительные API-вызовы |
| Регрессия в кастомном observability-плагине | Средняя | TypeScript build + playwright smoke-тест до merge |
| Backstage 1.50.3 несовместим с community-plugins (kubernetes, techdocs) | Низкая | Проверить backstage/community-plugins compatibility matrix перед деплоем |
| ArgoCD sync race с параллельными изменениями | Низкая | Деплоить в maintenance window |
