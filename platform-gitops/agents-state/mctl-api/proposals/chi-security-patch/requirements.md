# Обновление chi/v5 до v5.2.5 (security fix RedirectSlashes)

## Контекст
chi/v5 v5.2.5 (выпущен 2025-02-05) содержит security fix в middleware `RedirectSlashes`, а также исправление двойного вызова обработчика в `RouteHeaders`. mctl-api использует chi/v5 5.2.1 в качестве HTTP-роутера для всех REST- и MCP-эндпоинтов, включая публичный `https://api.mctl.ai`. Отставание составляет 4 patch-версии при наличии явного security fix.

Уязвимость в `RedirectSlashes` middleware потенциально позволяет манипулировать путями запроса через некорректный redirect, что при определённых конфигурациях может использоваться для обхода маршрутизации или auth-middleware. Обновление — patch-bump без breaking changes в API chi/v5, минимальный effort при непосредственном security-эффекте.

## User stories
- AS a platform security engineer I WANT chi/v5 upgraded to v5.2.5 SO THAT the known security vulnerability in RedirectSlashes middleware is remediated on the public API endpoint.
- AS a developer I WANT the router library to be on the latest patch version SO THAT the RouteHeaders double-handler bug does not cause unexpected behaviour in API routing.

## Acceptance criteria (EARS)
- WHEN mctl-api handles any HTTP request with a trailing slash THE SYSTEM SHALL apply the patched RedirectSlashes behaviour from chi v5.2.5 without path manipulation vulnerability.
- WHEN the application starts THE SYSTEM SHALL load chi/v5 v5.2.5 or later (verified via `go.mod` and `go.sum`).
- WHILE the service is running THE SYSTEM SHALL route all existing REST endpoints and the `/mcp` endpoint correctly without regression.
- IF a RouteHeaders middleware is configured and a matching request arrives THE SYSTEM SHALL invoke the handler exactly once (no double-call regression).
- WHEN the updated binary is deployed to the `admins` tenant THE SYSTEM SHALL return correct HTTP status codes for all routes covered by existing integration tests.

## Out of scope
- Изменение конфигурации middleware chi (добавление или удаление `RedirectSlashes` — отдельное решение).
- Обновление зависимостей chi (httprate и т.д.) сверх транзитивных требований v5.2.5.
- Оценка замены chi на другой роутер.
- Изменение логики маршрутизации или auth-middleware.
