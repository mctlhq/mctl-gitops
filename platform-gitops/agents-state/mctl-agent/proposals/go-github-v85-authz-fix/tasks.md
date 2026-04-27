# Tasks: go-github-v85-authz-fix

- [ ] 1. Аудит использования go-github в codebase —
  DoD: список всех `.go`-файлов, импортирующих `go-github/v68`, и всех вызовов API
  (`github.Client` методов), зафиксирован в комментарии к PR. Особо отмечены вызовы
  `MarkThreadDone` и Custom Org Role API (known breaking changes).

- [ ] 2. Обновить `go.mod` (зависит от 1) —
  DoD: `go.mod` содержит `github.com/google/go-github/v85`; `go mod tidy` завершается
  без ошибок; `go.sum` обновлён.

- [ ] 3. Заменить все импорты `v68` → `v85` (зависит от 2) —
  DoD: `grep -r "go-github/v68" .` возвращает пустой результат в .go-файлах;
  все импорты переключены на v85.

- [ ] 4. Устранить breaking changes (зависит от 3) —
  DoD: `go build ./...` завершается без ошибок; все изменения типов/сигнатур задокументированы
  в commit message.

- [ ] 5. Запустить тест-сьют (зависит от 4) —
  DoD: `go test ./... -race` — все тесты зелёные; нет новых race conditions.

- [ ] 6. Добавить тест на cross-host redirect rejection (зависит от 4) —
  DoD: тест создаёт мок-сервер, который возвращает redirect на другой хост; убеждается,
  что `github.Client` возвращает ошибку и NOT выполняет запрос к redirect-URL.

- [ ] 7. Интеграционный smoke-тест PR-creation (зависит от 5) —
  DoD: тестовый алёрт `PodCrashLooping` проходит через полный pipeline → PR открывается
  в mctl-gitops с корректным содержимым; никаких 401/403 от GitHub API.

## Тесты

- [ ] T1. `go test ./internal/skill/builtin/... -v` — все builtin skills компилируются
  и тесты проходят с новой версией go-github.
- [ ] T2. Cross-host redirect test (создаётся в задаче 6) — `go test ./... -run TestCrossHostRedirect`.
- [ ] T3. `go vet ./...` — нет новых предупреждений.
- [ ] T4. Staging deploy: образ с v85 задеплоен в admins/staging; в течение одного цикла
  ротации токена (30 мин) проверить, что GitHub API вызовы успешны.

## Откат

```bash
# В репозитории mctl-agent:
git revert <commit-sha-upgrade>
# Пересобрать образ с v68
# Обновить тег образа в GitOps манифесте admins-тенанта
```

ArgoCD синхронизирует откат автоматически. GitHub token не затрагивается — ротация
продолжается независимо от версии go-github.
