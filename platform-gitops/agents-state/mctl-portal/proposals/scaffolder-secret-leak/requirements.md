# Закрыть CVE-2026-32237: утечка серверных env-переменных через dry-run endpoint

## Контекст
CVE-2026-32237 затрагивает `plugin-scaffolder-backend` версий 3.1.0–3.1.4 (исключая
3.1.1+). Аутентифицированный пользователь с правом на dry-run шаблонов получает в ответе
endpoint'а полные значения серверных переменных среды (Vault token, Postgres DSN, GitHub
App credentials) из-за неполной редакции вложенных JSON-объектов. В mctl-portal эти
секреты смонтированы через ExternalSecret и критически важны для безопасности платформы.

Примечательно, что патч для CVE-2026-32237 входит в тот же релиз `plugin-scaffolder-backend`
3.1.1+, что закрывает CVE-2026-24046 (scaffolder-path-traversal). Оба CVE могут и должны
быть закрыты одним PR, что снижает операционную нагрузку и минимизирует количество
production-деплоев.

## User stories
- AS a platform engineer I WANT the scaffolder dry-run endpoint to redact all server-side
  environment variables from its response SO THAT authenticated users cannot extract Vault
  tokens, Postgres DSN, or GitHub App credentials via template preview.
- AS a security officer I WANT both CVE-2026-24046 and CVE-2026-32237 to be closed in a
  single deployment SO THAT the attack surface for scaffolder is eliminated atomically.
- AS a developer I WANT the dry-run functionality to remain available for template
  debugging SO THAT template authors can still preview scaffolder output without
  triggering secrets exposure.

## Acceptance criteria (EARS)
- WHEN a user calls the scaffolder dry-run endpoint THE SYSTEM SHALL return template
  output with all server-side environment variable values replaced by redaction markers.
- WHEN the dry-run response contains nested JSON objects THE SYSTEM SHALL recursively
  redact any field whose key or value matches known secret patterns (tokens, DSNs,
  credentials).
- WHILE `plugin-scaffolder-backend` >= 3.1.1 is running THE SYSTEM SHALL not expose any
  `process.env` values in dry-run API responses.
- IF `yarn audit` is run against the production lockfile THEN THE SYSTEM SHALL report no
  critical or high CVEs related to CVE-2026-32237 or CVE-2026-24046.
- WHEN a dry-run is executed with a valid template and no path-traversal payloads THE
  SYSTEM SHALL return a successful preview response with correctly rendered template
  variables (non-secret).

## Out of scope
- Ограничение прав на вызов dry-run endpoint (RBAC) — отдельная тема.
- Ротация уже скомпрометированных секретов (если утечка произошла до патча) — за рамками
  данного предложения; требует отдельного incident response.
- Изменения в тенанте `labs`.
- Аудит кастомных плагинов на предмет похожих редакционных уязвимостей.
