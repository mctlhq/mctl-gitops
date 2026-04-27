# Закрыть CVE-2026-29185: path traversal в SCM URLs утечка GitHub App token

## Контекст
CVE-2026-29185 описывает уязвимость в `@backstage/integration`: закодированные
path-traversal последовательности (например, `%2F..%2F`, `%252F`) в user-supplied SCM
URL позволяют перенаправить запросы к произвольным SCM API-эндпоинтам с серверными
credentials — в первую очередь с GitHub App token. Уязвимость затрагивает catalog-import,
scaffolder git actions и github-actions plugin.

В mctl-portal все три точки поражения активно используются: catalog-import применяется
для регистрации сервисов, scaffolder git actions — для коммитов в mctl-gitops, а
github-actions plugin — для отображения статуса CI. GitHub App token, используемый
платформой, предоставляет широкие права на чтение и запись в организации. Фикс доступен
в `@backstage/integration` v1.20.1, входящей в Backstage v1.50.3.

## User stories
- AS a platform engineer I WANT all SCM URLs provided by users to be validated and
  normalized before use SO THAT path-traversal sequences cannot redirect requests to
  arbitrary SCM API endpoints with server-side GitHub App credentials.
- AS a security officer I WANT Backstage upgraded to v1.50.3 SO THAT CVE-2026-29185 is
  closed and the GitHub App token cannot be exfiltrated through crafted SCM URLs.
- AS a developer I WANT catalog-import, scaffolder git actions, and the github-actions
  plugin to continue working correctly after the upgrade SO THAT existing workflows are
  not disrupted.

## Acceptance criteria (EARS)
- WHEN a user submits a SCM URL containing path-traversal sequences (encoded or
  double-encoded) to catalog-import, scaffolder git actions, or the github-actions plugin
  THE SYSTEM SHALL reject the URL with a validation error before making any outbound
  request.
- WHEN `@backstage/integration` v1.20.1+ processes a SCM URL THE SYSTEM SHALL normalize
  and validate the URL to ensure it resolves to an allowed SCM host without path
  manipulation.
- WHILE Backstage v1.50.3 is running THE SYSTEM SHALL not forward server-side GitHub App
  tokens to endpoints other than the configured SCM integration hosts.
- WHEN a catalog-import is performed with a valid repository URL THE SYSTEM SHALL
  successfully register the component without errors or regressions.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-29185.
- WHEN `@backstage/integration` processes a URL with a non-allowed host THEN THE SYSTEM
  SHALL return an error and not attach authentication headers to the request.

## Out of scope
- Обновление Backstage до версии выше 1.50.3 (только закрытие конкретного CVE).
- Изменения в тенанте `labs`.
- Ограничение списка разрешённых SCM-хостов через allowlist (может быть отдельным
  предложением).
- Аудит кастомных плагинов на предмет аналогичных URL-validation уязвимостей.
- Замена GitHub App на другой механизм аутентификации.
