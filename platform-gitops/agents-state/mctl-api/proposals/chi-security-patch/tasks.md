# Tasks: chi-security-patch

- [ ] 1. Обновить зависимость chi/v5 до v5.2.5 — DoD: `go.mod` содержит `github.com/go-chi/chi/v5 v5.2.5`, `go.sum` обновлён, `go mod tidy` выполнен без ошибок, diff `go.sum` проверен в ревью.
- [ ] 2. Прогон unit-тестов (зависит от 1) — DoD: `go test ./...` завершается успешно без новых failure.
- [ ] 3. Прогон интеграционных тестов маршрутизации (зависит от 1) — DoD: все HTTP маршруты (REST endpoints, `/mcp`, `/metrics`, `/healthz`) возвращают ожидаемые статус-коды; slash-redirect тесты проходят с новым поведением RedirectSlashes.
- [ ] 4. Деплой в `admins` через ArgoCD (зависит от 2, 3) — DoD: ArgoCD sync завершён, pod перешёл в Running, `/healthz` отвечает 200, `/metrics` доступны.

## Тесты
- [ ] T1. Тест RedirectSlashes: запрос `GET /api/v1/services/` (с trailing slash) обрабатывается корректно — либо redirect на `/api/v1/services`, либо 200 согласно конфигурации; проверить, что патч убирает уязвимое поведение (нет манипуляции путём).
- [ ] T2. Тест RouteHeaders: если `RouteHeaders` middleware используется, обработчик вызывается ровно один раз при matching-запросе (assertion на счётчик вызовов).
- [ ] T3. Smoke test после деплоя: REST API endpoint (например, `GET /api/v1/tenants`) возвращает 200/401 корректно.
- [ ] T4. Smoke test после деплоя: `/mcp` endpoint принимает POST-запрос и возвращает корректный ответ (не 404/500).
- [ ] T5. Smoke test после деплоя: `/metrics` возвращает 200 с prometheus-метриками.

## Откат
1. В `go.mod` откатить `github.com/go-chi/chi/v5` на `v5.2.1`, выполнить `go mod tidy`, пересобрать бинарь.
2. Задеплоить предыдущую версию образа через ArgoCD (тег предыдущего successful deploy).
3. Security fix остаётся неприменённым — зафиксировать как known issue в security tracker; при необходимости временно отключить `RedirectSlashes` middleware как mitigation.
