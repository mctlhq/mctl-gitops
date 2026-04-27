# Обновление Go toolchain до 1.26.2

## Контекст
mctl-agent собирается на Go 1.24. Релиз Go 1.26.2 (2026-04-07) содержит security-фиксы
в `crypto/tls`, `crypto/x509`, `html/template` и пакете `os`. Каждое исходящее соединение
агента с GitHub API и Anthropic API проходит через TLS — уязвимости в crypto/tls напрямую
затрагивают основной operational path. Текущий toolchain отстаёт на два minor-релиза, что
накапливает CVE-долг в стандартной библиотеке. Дополнительно Go 1.26.0 включил Green Tea GC
по умолчанию, снижающий GC overhead на 10–40% без роста потребления памяти.

## User stories

- AS a platform engineer I WANT mctl-agent to be built with Go 1.26.2 SO THAT known
  security vulnerabilities in crypto/tls and crypto/x509 are remediated.
- AS a platform operator I WANT mctl-agent to benefit from Green Tea GC SO THAT GC
  latency spikes do not affect alert-processing throughput.

## Acceptance criteria (EARS)

- WHEN mctl-agent is built, THE SYSTEM SHALL use Go toolchain 1.26.2 or later.
- WHEN mctl-agent establishes a TLS connection to GitHub API or Anthropic API,
  THE SYSTEM SHALL use a runtime free of known CVEs in `crypto/tls` and `crypto/x509`.
- WHILE mctl-agent is running under load, THE SYSTEM SHALL exhibit GC overhead reduced
  by the Green Tea GC compared to Go 1.24 baseline (verifiable via `go tool pprof`).
- IF any existing unit or integration test fails after the toolchain bump,
  THE SYSTEM SHALL NOT be released until all tests pass.

## Out of scope

- Изменения в Go-коде приложения (только тулчейн).
- Апгрейд сторонних Go-зависимостей (chi, go-github и др.) — отдельные proposals.
- Изменения в CRD или GitOps-манифестах.
