# Design: go-github-v85-authz-fix

## Текущее состояние

`go.mod` содержит `github.com/google/go-github/v68 v68.x.x`. Все файлы, работающие с
GitHub API, импортируют `github.com/google/go-github/v68/github`. Клиент используется
в `internal/skill/builtin/` (как минимум PR-creation skill) и в HTTP-обработчике
токен-инициализации. Согласно `context/architecture.md`, используется **Google/go-github v68**
для открытия PR с фиксами в `mctlhq/mctl-gitops`.

## Предлагаемое решение

Апгрейд в три фазы:

### Фаза 1 — Обновить go.mod
```diff
-require github.com/google/go-github/v68 v68.x.x
+require github.com/google/go-github/v85 v85.0.0
```
Запустить `go mod tidy`.

### Фаза 2 — Переписать импорты
Все строки вида:
```go
import "github.com/google/go-github/v68/github"
```
заменить на:
```go
import "github.com/google/go-github/v85/github"
```
Выполняется автоматически командой:
```bash
find . -name '*.go' | xargs sed -i 's|go-github/v68|go-github/v85|g'
```

### Фаза 3 — Устранить breaking changes
Задокументированные breaking changes между v68 и v85:
- `MarkThreadDone` — возвращаемый тип изменён; если используется — адаптировать.
- Custom Organization Role API — изменились типы; проверить `Audit` на использование.
- Прочие breaking changes — выявляются через `go build ./...` на шаге компиляции.

Cross-host redirect rejection активируется автоматически в v85 — дополнительного кода
не требуется. Можно добавить тест на поведение при редиректе (см. tasks.md T2).

## Альтернативы

| Вариант | Почему отброшен |
|---|---|
| Остаться на v68, вручную настроить `http.Client` с кастомной `CheckRedirect` | Высокий maintenance overhead; при следующем апгрейде конфликт конфигураций; не получаем будущие security-патчи go-github. |
| Поэтапный апгрейд через промежуточные версии (v68 → v75 → v85) | Go modules поддерживают прямой переход; промежуточные версии только увеличивают риск. |
| Переключиться на прямые GitHub REST API вызовы без библиотеки | Полная потеря типизации и будущих security-патчей; высокий Effort; противоречит существующей архитектуре. |

## Влияние на платформу

- **Migration**: изменения в go.mod и импортах — чисто в коде mctl-agent, ничего
  в GitOps манифестах или CRD.
- **Backward compatibility**: runtime поведение PR-creation не меняется; меняется только
  поведение при аномальном cross-host redirect (теперь возвращает ошибку вместо следования).
- **Resource impact**: библиотека client-side, нет роста потребления памяти. Нейтрально
  для `labs`.
- **Риски и митигации**:
  - *Риск*: неизвестные breaking changes между v68 и v85 (17 мажорных версий).
  - *Митигация*: `go build ./...` на CI выявит все compile-time ошибки; полный `go test ./...`
    выявит runtime-регрессии. Сделать feature-ветку, пройти все тесты до merge.
  - *Откат*: revert коммита в git → пересборка образа → обновление тега в GitOps.
