# Tasks: go-upgrade

- [ ] 1. Обновить Go директиву в go.mod и toolchain в CI/Dockerfile — DoD: `go.mod` содержит `go 1.26`, `Dockerfile` использует `golang:1.26.2-alpine` (или актуальный patch), CI workflow (`*.yml`) обновлён, изменения зафиксированы в PR.
- [ ] 2. Проверить совместимость прямых зависимостей с Go 1.26 (зависит от 1) — DoD: для каждой прямой зависимости (chi, pgx, mcp-go, client-go, go-oidc, prometheus/client_golang, httprate) проверена `go` директива в их `go.mod`; при необходимости выполнены bump'ы, `go mod tidy` завершён успешно.
- [ ] 3. Сборка и прогон unit-тестов под Go 1.26 (зависит от 1, 2) — DoD: `go build ./...` и `go test ./...` завершаются без ошибок; ни один тест не упал из-за смены toolchain.
- [ ] 4. Проверка `GODEBUG` defaults и release notes (зависит от 1) — DoD: release notes Go 1.25 и 1.26 проверены на изменения `GODEBUG` defaults, влияющих на TLS, HTTP, crypto; при необходимости добавлены явные `GODEBUG=...` переменные в конфиг деплоя.
- [ ] 5. Прогон интеграционных тестов (зависит от 3, 4) — DoD: все интеграционные тесты, включая TLS-соединения с внешними сервисами (Vault, ArgoCD, Argo Workflows, Backstage), проходят в staging-окружении.
- [ ] 6. `govulncheck ./...` (зависит от 3) — DoD: нет findings по stdlib CVE из Go 1.25/1.26 security fixes; результат зафиксирован в PR description.
- [ ] 7. Деплой в `admins` через ArgoCD (зависит от 5, 6) — DoD: ArgoCD sync завершён, pod перешёл в Running, `/healthz` отвечает 200, `/metrics` доступны, логи не содержат TLS-ошибок.

## Тесты
- [ ] T1. `go version` в CI build output показывает `go1.26.x`.
- [ ] T2. `govulncheck ./...` — нет stdlib findings.
- [ ] T3. Интеграционный тест TLS: исходящий запрос к Vault (`secrets.mctl.ai`) завершается успешно (200/204 ответ, нет TLS handshake error).
- [ ] T4. Интеграционный тест Auth: Dex JWT verification через JWKS работает корректно (crypto/x509 chain validation).
- [ ] T5. Smoke test после деплоя: все три типа bearer-аутентификации (GitHub PAT, Dex JWT, OAuth JWT) принимаются и корректно авторизуют запросы.
- [ ] T6. Проверка `/metrics` и `/healthz` после деплоя — оба endpoint возвращают 200.

## Откат
1. В `go.mod` вернуть директиву `go 1.24`, Dockerfile и CI workflow — предыдущие значения.
2. Пересобрать образ с тегом rollback через CI.
3. Задеплоить предыдущую версию образа через ArgoCD.
4. Открытые CVE stdlib остаются unfixed — зафиксировать как known issue в security tracker с обоснованием и датой повторной попытки апгрейда.
5. Если причина отката — несовместимость зависимости, открыть отдельный issue с конкретной зависимостью и версионным конфликтом.
