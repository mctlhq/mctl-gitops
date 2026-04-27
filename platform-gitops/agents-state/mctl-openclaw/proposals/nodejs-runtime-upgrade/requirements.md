# Обновление Node.js runtime до безопасной версии + аудит lockfile на malicious packages

## Контекст

Node.js January 2026 Security Release закрыл восемь CVE, из которых три имеют рейтинг High:
CVE-2025-55131 (buffer non-zerofilled — утечка heap-данных через uninitialised buffers),
CVE-2025-55130 (symlink bypass — обход symlink restrictions при file I/O операциях),
CVE-2025-59465 (HTTP/2 DoS — resource exhaustion через crafted HTTP/2 запросы). Безопасные
версии: v20.20.0+, v22.22.0+, v24.13.0+. Если базовый Docker образ openclaw использует
Node.js ниже этих версий — все три вектора активны в production.

Параллельно в конце 2025 года раскрыты два malicious npm пакета: `lotusbail` (Baileys-форк,
крадёт WhatsApp auth tokens, перехватывает сообщения, 56k+ downloads) и `discord.js-user`
(GHSA-69r6-7h4f-9p7q, CVSS 9.8, эксфильтрирует Discord token). Оба могут присутствовать
в транзитивных зависимостях через ошибочные package.json или typosquatting. Фокус данного
proposal отличается от `npm-supply-chain-audit` (тот про poisoned пакеты как класс): здесь
scope ограничен конкретными двумя известными пакетами + Node.js runtime bump в Dockerfile.

## User stories

- AS a platform security engineer I WANT Docker базовый образ openclaw обновлён до Node.js
  версии >= v22.22.0 SO THAT три High CVE из январского security release не активны
  в production runtime
- AS a platform operator I WANT CI-шаг `npm audit --audit-level=high` в pipeline образа
  openclaw SO THAT новые High/Critical уязвимости в зависимостях блокируют сборку до
  попадания в деплой
- AS a security engineer I WANT автоматическую проверку lockfile на присутствие пакетов
  `lotusbail` и `discord.js-user` SO THAT malicious supply-chain пакеты обнаруживаются
  до деплоя в любой тенант
- AS a labs tenant operator I WANT обновление Node.js runtime не увеличивало RAM потребление
  SO THAT labs тенант не приближается к OOM после base image bump

## Acceptance criteria (EARS)

- WHEN Docker образ openclaw собирается в CI THE SYSTEM SHALL использовать базовый образ
  Node.js не ниже v22.22.0 LTS (или v20.20.0 / v24.13.0 в зависимости от выбранной LTS линейки)
- WHEN CI собирает образ openclaw THE SYSTEM SHALL выполнять `npm audit --audit-level=high`
  и завершать сборку с ошибкой если обнаружены уязвимости уровня High или Critical
- WHEN CI собирает образ openclaw THE SYSTEM SHALL проверять `package-lock.json` на
  присутствие имён `lotusbail` и `discord.js-user` (прямые и транзитивные зависимости)
  и завершать сборку с ошибкой при обнаружении
- IF обновление Node.js runtime вызывает несовместимость с кодом openclaw или его плагинами
  THEN THE SYSTEM SHALL не продвигать образ в admins и ovk до устранения несовместимости
- WHILE новый образ деплоится в labs THE SYSTEM SHALL не увеличивать потребление RAM пода
  openclaw более чем на 20MB относительно baseline (Node.js minor bump, не major)
- WHEN образ с обновлённым Node.js runtime задеплоен в labs THE SYSTEM SHALL пройти
  restore-state probe в рамках штатного timeout (ADR 0002)
- WHEN `npm audit` или grep на malicious пакеты обнаруживают проблему в CI THE SYSTEM SHALL
  уведомлять команду через alert-канал и блокировать merge/deploy

## Out of scope

- Обновление Node.js до major версии (v22 → v24) — требует отдельной валидации совместимости;
  достаточно patch до безопасного minor в текущей LTS линейке
- Широкий аудит всего supply chain (все потенциально malicious пакеты) — покрыто отдельным
  proposal `npm-supply-chain-audit`
- Обновление TypeScript до 6.x (нет security CVE, нет срочности)
- Обновление Baileys, discord.js, node-slack-sdk (отдельные proposals по необходимости)
- Изменения в конфигурации openclaw или skills
- Изменение resource limits pods (если RAM-delta в норме)
