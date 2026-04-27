# Design: upgrade-to-2026-4-25

## Текущее состояние
Согласно `context/architecture.md` и `context/current-version.md`, все три тенанта (labs, admins, ovk) работают на openclaw 2026.3.14. Деплой организован по схеме Docker → mctl-gitops → ArgoCD. Rollout-маршрут: labs → admins → ovk (ADR 0001). Состояние защищается двумя механизмами: s3-sync canary (проверяет запись в S3) и restore-state readiness probe (проверяет восстановление сессий из S3 при старте пода). Тенант labs близок к лимиту памяти — любой прирост RAM требует обоснования перед накатом.

Пять CVE, открытых в текущей версии:
- CVE-2026-41349 (CVSS 8.8) — исправлено в >= 2026.3.28
- CVE-2026-41361 (High) — исправлено в >= 2026.3.28
- CVE-2026-41359 (High) — исправлено в >= 2026.3.28
- CVE-2026-41353 — исправлено в >= 2026.3.22
- CVE-2026-41348 (CVSS 5.4) — исправлено в >= 2026.3.31

## Предлагаемое решение
Обновить тег образа openclaw с `2026.3.14` до `2026.4.25` в gitops-манифестах каждого тенанта, последовательно: labs → admins → ovk.

**Шаг 0 — Pre-flight RAM check (labs)**
Перед коммитом изменения в labs-манифест запустить тестовый под с образом 2026.4.25 в изолированном namespace или через `kubectl run --restart=Never` с resource limits labs. Зафиксировать RSS/working set после прохождения restore-state probe. Если прирост > 50MB относительно текущего labs-baseline — остановиться, создать тикет на поднятие лимита перед продолжением.

**Шаг 1 — labs rollout**
Обновить `image.tag` в labs Helm values (`mctl-gitops/tenants/labs/values.yaml` или аналог). ArgoCD применяет изменение. S3-sync canary останавливается на время rollout (аннотация или ручной suspend). После прохождения readiness probe — возобновить canary с задержкой 60s. Наблюдать 1 час: метрики ошибок, WhatsApp/Telegram session healthcheck.

**Шаг 2 — admins rollout**
При отсутствии регрессий в labs повторить для admins. Blast radius минимален (внутренний деплой), можно делать без дополнительного окна.

**Шаг 3 — ovk rollout**
Только после успешного прогона в labs и admins. Выбрать maintenance window с минимальной активностью клиента. Отдельно убедиться, что restore-state probe проходит в timeout перед переключением трафика. S3-sync canary — аналогично: suspend → rollout → resume с задержкой.

**Почему именно так:**
Маршрут labs → admins → ovk уже закреплён в ADR 0001 и проверен на практике. Обновление тега образа — наименее инвазивное изменение: не трогает конфигурацию каналов, skills, extensions. Upstream-образ 2026.4.25 является минорным релизом без breaking changes в публичном API (200+ изменений внутри). RAM check перед labs — митигация риска OOM, специфичного для labs-тенанта.

## Альтернативы

**Альтернатива 1: Промежуточный апгрейд до 2026.3.31 (минимально закрывает все 5 CVE)**
Версия 2026.3.31 закрывает последнюю из пяти CVE (CVE-2026-41348). Можно обновиться до неё вместо 2026.4.25. Отброшено: нет смысла делать два rollout, когда 2026.4.25 — актуальный стабильный релиз и закрывает всё то же самое плюс имеет дополнительные улучшения. Двойной rollout удваивает операционный риск.

**Альтернатива 2: Точечный патч только CVE-2026-41349 через конфигурацию**
CVE-2026-41349 (agentic consent bypass) теоретически можно смягчить через конфигурацию execution approval политики, не обновляя версию. Отброшено: не закрывает остальные четыре CVE; временный workaround хуже upstream fix; создаёт расхождение с upstream, усложняющее будущие обновления.

**Альтернатива 3: Обновление только ovk (production), пропустить labs и admins**
Быстрее с точки зрения security exposure на production. Отброшено: нарушает ADR 0001 (rollout-маршрут); labs служит именно для проверки перед production; риск OOM в labs не выявится до production. Неприемлемо для ovk с высоким SLA.

## Влияние на платформу

**Migration/миграции**
Изменение только тега образа в gitops-манифестах. Changelog 2026.4.25 не содержит breaking migration для S3 state schema (необходимо подтвердить при изучении upstream CHANGELOG перед rollout).

**Backward compatibility**
Минорный релиз, upstream придерживается semver. Plugin SDK и `extensions/*` должны остаться совместимы. При rollout в labs проверить, что extensions собираются и загружаются корректно.

**Resource impact**
- labs: HIGH RISK. Тенант близок к лимиту RAM. Обязательный pre-flight RAM check с тестовым подом перед коммитом в labs-манифест. Если прирост > 50MB — блокировка и тикет на увеличение лимита.
- admins: LOW RISK. Внутренний деплой, лимиты не критичны.
- ovk: MEDIUM RISK. Рестарты болезненны для production SLA, но restore-state probe гарантирует восстановление сессий из S3.

**Риски и митигации**
- OOM в labs → pre-flight RAM check, блокировка при delta > 50MB
- Потеря S3-sync → suspend canary во время rollout, resume с задержкой, алерт если canary не восстанавливается
- Потеря сессий в ovk → restore-state readiness probe, автооткат при failure
- Регрессия в extensions → smoke test в labs (WhatsApp + Telegram + Discord сессии) перед продвижением в admins/ovk
- Upstream breaking change в CHANGELOG → review CHANGELOG до начала rollout
