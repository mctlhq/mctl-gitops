# Закрыть CVE-2026-24046: symlink path traversal в scaffolder

## Контекст
CVE-2026-24046 описывает уязвимость symlink-based path traversal в scaffolder actions
(`debug:log`, `fs:delete`, archive extraction) пакетов `@backstage/backend-defaults` и
`plugin-scaffolder-backend`. Аутентифицированный пользователь, имеющий право запускать
шаблоны, способен через специально сформированные symlink-конструкции читать, записывать
и удалять произвольные файлы на сервере — в том числе секреты Vault, смонтированные
через ExternalSecret как файлы в backend-pod.

В mctl-portal scaffolder является центральным инструментом онбординга; Vault-секреты
(Vault token, Postgres DSN, GitHub App credentials) смонтированы в том же pod, что делает
поверхность атаки критически широкой. Backstage развёрнут в тенанте `admins` под ArgoCD;
изменение затрагивает только этот тенант и не влияет на тенант `labs`.

## User stories
- AS a platform engineer I WANT the scaffolder backend to reject any file operation that
  resolves outside the task workspace SO THAT a malicious template cannot exfiltrate or
  corrupt Vault secrets and other server-side files.
- AS a security officer I WANT all scaffolder dependencies pinned to patched versions in
  the production Docker image SO THAT the CVE-2026-24046 attack surface is fully closed
  after the next deploy.
- AS a developer I WANT the scaffolder to remain fully functional for legitimate templates
  SO THAT onboarding workflows are not disrupted by the security fix.

## Acceptance criteria (EARS)
- WHEN a scaffolder action (`debug:log`, `fs:delete`, or archive extraction) resolves a
  file path that exits the task workspace directory THE SYSTEM SHALL reject the operation
  with an error and abort the template step.
- WHEN a symlink inside an extracted archive points to a path outside the workspace THE
  SYSTEM SHALL refuse to create that symlink and mark the step as failed.
- WHILE a scaffolder task is executing THE SYSTEM SHALL enforce that all file-system
  operations remain within the ephemeral task workspace directory.
- WHEN the backend pod is deployed with `@backstage/backend-defaults` >= 0.12.2 and
  `plugin-scaffolder-backend` >= 3.1.1 THE SYSTEM SHALL pass all existing scaffolder
  integration tests without regressions.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-24046 or CVE-2026-32237.

## Out of scope
- Ограничение прав пользователей на запуск шаблонов (RBAC) — отдельная тема.
- Обновление самого Backstage до v1.50.3 (покрывается в `integration-scm-credentials`).
- Изменения в тенанте `labs`.
- Аудит кастомных scaffolder-плагинов на наличие собственных path-traversal уязвимостей.
