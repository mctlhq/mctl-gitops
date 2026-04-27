# Обновление google/go-github до v85 (Authorization header leak prevention)

## Контекст
mctl-agent использует `google/go-github` **v68** для создания fix-PR в репозитории
`mctlhq/mctl-gitops`. Клиент аутентифицируется через GitHub App installation token,
ротируемый каждые 30 минут.

В версии v85.0.0 (2026-04-20) добавлен **cross-host redirect rejection**: при HTTP-редиректе
на хост, отличающийся от оригинального, клиент теперь отказывается передавать заголовок
`Authorization` стороннему серверу. В v68 эта защита отсутствует — если GitHub API
(или любой настроенный endpoint) вернёт редирект на внешний хост, installation token
будет передан третьей стороне. Installation token даёт права на запись в `mctl-gitops`,
что означает потенциальный supply-chain compromise.

Разрыв: v68 → v85 = 17 мажорных версий; есть breaking changes, требующие адаптации кода.

## User stories

- AS a security engineer I WANT mctl-agent's GitHub client to reject cross-host redirects
  SO THAT the GitHub App installation token cannot be leaked to an untrusted host.
- AS a platform engineer I WANT mctl-agent to use the latest stable go-github client
  SO THAT future security patches are applied with minimal lag.

## Acceptance criteria (EARS)

- WHEN the GitHub API returns an HTTP redirect to a hostname different from the original,
  THE SYSTEM SHALL reject the redirect, NOT forward the Authorization header, and return
  an error to the caller.
- WHEN mctl-agent creates a PR, THE SYSTEM SHALL use `google/go-github` v85 or later.
- IF a cross-host redirect is rejected, THE SYSTEM SHALL log the event at WARN level
  including the original and redirect URLs (without the token value).
- WHILE mctl-agent operates normally, THE SYSTEM SHALL maintain full PR-creation
  functionality unchanged (no regression in existing routed-alert handling).

## Out of scope

- Изменения в логике создания PR или обработки алёртов.
- Ротация или хранение GitHub App secrets (покрывается cwft-rotate-github-token).
- Апгрейд других зависимостей (go, chi, sqlite) — отдельные proposals.
- Добавление новых GitHub API вызовов (beyond текущего функционала PR-creation).
