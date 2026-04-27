# Tasks: upgrade-to-2026-4-25

- [ ] 1. Прочитать CHANGELOG 2026.3.14 → 2026.4.25 на предмет breaking changes в Plugin SDK, S3 state schema, channel configs — DoD: документ с итогами review создан (или отметка "no breaking changes"), все breaking changes учтены в плане
- [ ] 2. Pre-flight RAM check: запустить тестовый под с образом 2026.4.25 в изолированном окружении с resource limits labs (зависит от 1) — DoD: зафиксированы RSS и working set пода после прохождения restore-state probe; если delta > 50MB — создан тикет на увеличение лимита labs и дальнейшие шаги заблокированы
- [ ] 3. Обновить тег образа в labs gitops-манифесте до `2026.4.25` (зависит от 2) — DoD: PR в mctl-gitops создан, прошёл review; ArgoCD применил изменение; restore-state probe пройдена; s3-sync canary возобновлён с задержкой 60s
- [ ] 4. Наблюдение labs 1 час после rollout (зависит от 3) — DoD: нет ошибок в логах, WhatsApp/Telegram/Discord сессии активны, s3-sync canary успешно выполнил минимум 2 цикла, RAM не превышает лимит
- [ ] 5. Обновить тег образа в admins gitops-манифесте до `2026.4.25` (зависит от 4) — DoD: ArgoCD применил изменение; restore-state probe пройдена; s3-sync canary возобновлён; нет ошибок в логах 30 минут
- [ ] 6. Обновить тег образа в ovk gitops-манифесте до `2026.4.25` в maintenance window (зависит от 5) — DoD: ArgoCD применил изменение; restore-state probe пройдена; s3-sync canary возобновлён; production клиент подтвердил работу основных каналов
- [ ] 7. Закрыть security findings CVE-2026-41349, CVE-2026-41361, CVE-2026-41359, CVE-2026-41353, CVE-2026-41348 в трекере (зависит от 6) — DoD: все 5 CVE помечены как resolved с версией 2026.4.25 и датой деплоя на ovk

## Тесты
- [ ] T1. Smoke test labs: WhatsApp, Telegram, Discord — отправить и получить тестовое сообщение через каждый канал после rollout
- [ ] T2. Smoke test labs: выполнить тестовый agentic skill с explicit execution approval — убедиться, что consent bypass (CVE-2026-41349) не воспроизводится
- [ ] T3. Smoke test labs: проверить SSRF guard через тестовый запрос на IPv6 special-use адрес (например, `::1`) — убедиться что запрос отклонён (CVE-2026-41361)
- [ ] T4. Smoke test labs: проверить, что Telegram send endpoint не позволяет operator-write scope достичь admin-class config (CVE-2026-41359) — проверить через API с restricted credentials
- [ ] T5. Restore-state probe: убедиться что при симулированном рестарте пода в labs сессии восстанавливаются из S3 в течение timeout
- [ ] T6. S3-sync canary: убедиться что canary возобновляется и успешно выполняет цикл записи в S3 после каждого rollout (labs, admins, ovk)
- [ ] T7. RAM monitoring labs: зафиксировать memory usage пода через 5 минут, 30 минут, 1 час после rollout — значения не должны превышать pre-flight baseline + 50MB

## Откат
При провале restore-state probe на любом тенанте ArgoCD автоматически откатывает деплой к предыдущей версии (2026.3.14). Если автооткат не сработал:
1. Вручную обновить `image.tag` в gitops-манифесте обратно на `2026.3.14` и создать PR
2. После применения: убедиться что restore-state probe пройдена, s3-sync canary возобновлён
3. Зафиксировать причину провала в incident log перед повторной попыткой
4. Для ovk: при ручном откате уведомить клиента о кратковременном maintenance
