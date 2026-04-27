# Обновление Go с 1.24 на актуальную поддерживаемую ветку (1.26)

## Контекст
Go придерживается политики поддержки двух последних major-веток. Ветка Go 1.24 получила последний security-патч (1.24.13) в феврале 2026 и с тех пор не получает исправлений. Security-патчи для `crypto/tls`, `crypto/x509`, `archive/tar`, `html/template`, `os` и компилятора выходят только в ветках 1.25 и 1.26 (релизы 1.25.9 и 1.26.2 от 2026-04-07).

mctl-api реализует три типа bearer-аутентификации (GitHub PAT, Dex JWT, OAuth JWT) и устанавливает TLS-соединения с Vault, ArgoCD, Argo Workflows и Backstage. Уязвимости в `crypto/tls` и `crypto/x509` напрямую угрожают конфиденциальности и целостности этих соединений. Актуальная стабильная ветка — 1.26 (последний патч 1.26.2).

## User stories
- AS a platform security engineer I WANT mctl-api built with Go 1.26 SO THAT all TLS/PKI security patches are applied and the runtime is on a supported release branch.
- AS a developer I WANT to use Go 1.26 language features and standard library improvements SO THAT code quality and toolchain support are maintained.

## Acceptance criteria (EARS)
- WHEN the CI pipeline builds mctl-api THE SYSTEM SHALL use Go 1.26.x toolchain (verified via `go version` in build output and `go.mod` `go` directive).
- WHEN mctl-api establishes outbound TLS connections (Vault, ArgoCD, Argo Workflows, Backstage) THE SYSTEM SHALL use the TLS stack from Go 1.26 with all published security fixes applied.
- WHILE running under Go 1.26 THE SYSTEM SHALL pass all existing unit and integration tests without modification to business logic.
- IF `govulncheck` is run against the built binary THE SYSTEM SHALL report no findings related to the Go standard library CVEs fixed in 1.25/1.26.
- WHEN the service starts under Go 1.26 THE SYSTEM SHALL expose correct `/metrics` and `/healthz` responses, confirming no runtime regressions.
- IF any direct dependency requires a minimum Go version higher than 1.26 THE SYSTEM SHALL surface a build error and the dependency shall be pinned to a compatible version before merging.

## Out of scope
- Миграция на Go 1.27+ или переход на go toolchain директиву автоматического обновления.
- Обновление зависимостей, не требующих изменений для совместимости с Go 1.26.
- Рефакторинг кода для использования новых языковых возможностей Go 1.25/1.26 (range-over func, improved type inference и т.д.) — отдельная задача после апгрейда.
- Обновление базовых Docker-образов и CI-раннеров (сопутствующая инфра-задача, не в scope mctl-api repo).
