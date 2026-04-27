# Tasks: clawhub-skills-allowlist

- [ ] 1. Инвентаризация текущих Layer 3 (remote) skills на всех трёх тенантах (ovk, labs, admins) — DoD: список всех зарегистрированных remote skill origins/URLs зафиксирован, легитимные origins определены и подтверждены operators'ами каждого тенанта
- [ ] 2. Определить механизм enforcement allowlist в openclaw: нативный config vs ingress middleware (зависит от 1) — DoD: проверен upstream changelog и конфигурация openclaw на наличие встроенного allowlist-механизма для remote skills; выбран подход (config-based или middleware), зафиксировано решение
- [ ] 3. Добавить поле `skills.remoteAllowlist` в Helm values schema и шаблон для каждого тенанта (зависит от 2) — DoD: поле добавлено в values schema с документацией; fail-closed дефолт (пустой список = deny-all) задан явно в шаблоне
- [ ] 4. Реализовать enforcement allowlist в openclaw config или ingress middleware (зависит от 3) — DoD: при попытке зарегистрировать Layer 3 skill с origin не из allowlist API возвращает 403; при пустом allowlist все регистрации блокируются
- [ ] 5. Заполнить allowlist для admins подтверждёнными origins из инвентаризации и задеплоить (зависит от 4) — DoD: manifests обновлены в mctl-gitops, PR прошёл review, ArgoCD применил конфиг, легитимные skills в admins работают
- [ ] 6. Заполнить allowlist для labs подтверждёнными origins и задеплоить (зависит от 5) — DoD: аналогично admins; RAM не изменился (конфигурационное изменение)
- [ ] 7. Заполнить allowlist для ovk подтверждёнными origins и задеплоить (зависит от 6) — DoD: аналогично; production клиент подтвердил работу всех используемых Layer 3 skills
- [ ] 8. Добавить CI-шаг в mctl-gitops: проверка новых remote skill sources в PR diff (зависит от 3) — DoD: CI-скрипт добавлен, тест показывает блокировку PR с новым неодобренным origin и прохождение PR с origin, уже присутствующим в allowlist
- [ ] 9. Задокументировать процесс одобрения нового skill-источника (allowlist update workflow) (зависит от 8) — DoD: инструкция для операторов добавлена в README или runbook; процесс включает security review и обновление allowlist в values.yaml

## Тесты
- [ ] T1. Попытаться зарегистрировать тестовый Layer 3 skill с произвольным URL `https://evil.example.com/skill` на каждом тенанте — ожидаемый результат: 403, skill не зарегистрирован
- [ ] T2. Зарегистрировать тестовый Layer 3 skill с URL из allowlist тенанта — ожидаемый результат: 200, skill зарегистрирован и работает
- [ ] T3. Проверить fail-closed: удалить allowlist из values тенанта (или задать пустой список) — ожидаемый результат: все попытки регистрации Layer 3 skills блокируются
- [ ] T4. CI-тест: создать PR с новым origin в skill-манифесте, не добавив его в allowlist — ожидаемый результат: CI шаг падает с информативным сообщением
- [ ] T5. CI-тест: создать PR с origin, уже присутствующим в allowlist — ожидаемый результат: CI шаг проходит
- [ ] T6. Проверить что существующие легитимные Layer 3 skills на всех тенантах продолжают работать после включения allowlist

## Откат
Если allowlist вызвал неожиданную блокировку легитимных skills в production (ovk):
1. Временно расширить allowlist: добавить заблокированный origin в `values.yaml` ovk и задеплоить через gitops — изменение применяется без рестарта (hot-reload)
2. Если hot-reload не сработал: выполнить rolling restart пода ovk (restore-state probe обеспечит восстановление сессий из S3)
3. Провести инвентаризацию и добавить пропущенный origin в allowlist permanently
4. Если enforcement механизм сломан и нужно полностью отключить allowlist: удалить поле `skills.remoteAllowlist` из values или выставить `null` — возврат к поведению до внедрения (без ограничений)
