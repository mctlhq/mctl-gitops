# Обновление openclaw до 2026.4.25 (закрытие 5 незакрытых CVE)

## Контекст
Текущая версия openclaw 2026.3.14 содержит 5 незакрытых уязвимостей, зафиксированных в inbox/2026-04-27.md. Наиболее критична CVE-2026-41349 (CVSS 8.8): LLM-агент может тихо отключить execution approval через `config.patch`, что в agentic-среде openclaw означает неконтролируемое выполнение действий без согласования с пользователем. Помимо неё открыты CVE-2026-41361 (SSRF через IPv6 special-use диапазоны), CVE-2026-41359 (privilege escalation через Telegram send endpoint), CVE-2026-41353 (allowProfiles bypass через persistent profile mutation) и CVE-2026-41348 (Discord slash command / autocomplete auth bypass, CVSS 5.4).

Upstream-релиз 2026.4.25 закрывает все пять уязвимостей и содержит 200+ изменений, включая TTS upgrade, plugin registry на cold persisted storage, расширение OpenTelemetry и browser automation hardening. Обновление идёт по накатанному маршруту labs → admins → ovk согласно ADR 0001; перед накатом на labs необходимо проверить delta RAM, так как тенант labs близок к лимиту памяти.

## User stories
- AS a platform operator I WANT openclaw обновлён до 2026.4.25 SO THAT пять открытых CVE закрыты до их потенциальной эксплуатации
- AS a security engineer I WANT подтверждение что все три тенанта работают на patched-версии SO THAT могу закрыть security findings в трекере
- AS a labs tenant operator I WANT предварительную проверку RAM-footprint нового релиза SO THAT обновление не приведёт к OOM в labs
- AS an ovk production operator I WANT rollout с проверкой restore-state probe и s3-sync canary SO THAT WhatsApp/Telegram сессии не потеряются при обновлении

## Acceptance criteria (EARS)
- WHEN докер-образ openclaw 2026.4.25 задеплоен в тенант labs THEN THE SYSTEM SHALL пройти readiness probe restore-state до перехода ArgoCD в статус Healthy
- WHEN rollout в labs завершён THE SYSTEM SHALL зафиксировать фактическое потребление RAM пода и сравнить с текущим лимитом labs; если delta > 50MB — заблокировать rollout в admins до решения
- WHILE rollout выполняется в любом тенанте THE SYSTEM SHALL держать s3-sync canary остановленным и перезапустить его с задержкой после успешного завершения rollout
- WHEN rollout в labs и admins прошёл без регрессий THE SYSTEM SHALL разрешить продвижение в ovk согласно rollout-маршруту labs → admins → ovk
- IF restore-state probe не проходит за отведённый timeout в любом тенанте THEN THE SYSTEM SHALL автоматически откатить деплой к предыдущей версии (2026.3.14)
- IF фактическое потребление RAM в labs после обновления превышает текущий лимит THEN THE SYSTEM SHALL не продвигать образ в admins и ovk без явного решения о поднятии лимита
- WHEN openclaw 2026.4.25 запущен на всех трёх тенантах THE SYSTEM SHALL не иметь активных CVE-2026-41349, CVE-2026-41361, CVE-2026-41359, CVE-2026-41353, CVE-2026-41348

## Out of scope
- Обновление Node.js runtime (нет срочного security-триггера)
- Обновление TypeScript до 6.x (нет security CVE)
- Миграция plugin registry на cold persisted storage (фича нового релиза, отдельное предложение при необходимости)
- Обновление зависимостей Baileys, discord.js, node-slack-sdk (покрыто отдельными proposals)
- Изменения в конфигурации каналов или skills
