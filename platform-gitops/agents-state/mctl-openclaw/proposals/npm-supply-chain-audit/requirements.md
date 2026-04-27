# Аудит и пиннинг официальных npm-пакетов (Baileys, discord.js)

## Контекст
Зафиксированы активно распространяемые poisoned npm-форки двух ключевых зависимостей openclaw (inbox/2026-04-27.md). Поддельный Baileys-форк перехватывает WhatsApp auth-токены, сообщения, контакты и медиафайлы через WebSocket wrapper. Пакет `discord.js-user` (CVSS 9.8, GHSA-69r6-7h4f-9p7q) сливает Discord-токены на удалённый сервер. Официальные пакеты — `@whiskeysockets/baileys` и `discordjs/discord.js` — не затронуты напрямую.

Угроза реализуется через случайную подмену: если в `package.json` или `package-lock.json` закреплён неверный пакет (например, `baileys` вместо `@whiskeysockets/baileys`, или `discord.js-user` вместо `discord.js`), openclaw будет отправлять auth-токены всех WhatsApp/Discord-аккаунтов на серверы атакующих. Даже если сейчас зависимости корректны, без явной CI-проверки риск случайной подмены при будущих обновлениях остаётся открытым. Effort минимальный: одноразовый аудит плюс постоянный CI-шаг.

## User stories
- AS a security engineer I WANT однократный аудит `package-lock.json` для подтверждения что используются только официальные пакеты SO THAT текущее состояние верифицировано и задокументировано
- AS a platform operator I WANT CI-проверку resolved URLs в `package-lock.json` против allowlist официальных пакетов SO THAT случайная подмена на poisoned форк выявляется в PR до деплоя
- AS a developer I WANT понятный список запрещённых имён пакетов (например, `baileys`, `discord.js-user`) SO THAT я не добавлю их случайно при обновлении зависимостей

## Acceptance criteria (EARS)
- WHEN CI-пайплайн выполняется для PR, затрагивающего `package.json` или `package-lock.json` THEN THE SYSTEM SHALL проверить resolved URLs всех Baileys- и discord.js-связанных пакетов против allowlist официальных реестров
- IF `package-lock.json` содержит resolved URL, не соответствующий официальному реестру (`registry.npmjs.org`) для пакетов из списка мониторинга THEN THE SYSTEM SHALL провалить CI-шаг с указанием конкретного пакета и найденного URL
- IF `package.json` или `package-lock.json` содержит имя пакета из списка запрещённых (`baileys`, `discord.js-user` и аналоги) THEN THE SYSTEM SHALL провалить CI-шаг с объяснением правильного пакета
- WHEN `npm audit` выполняется в CI THEN THE SYSTEM SHALL завершиться с ненулевым кодом возврата при обнаружении advisory с severity >= high для пакетов из списка мониторинга
- WHILE CI-проверка активна THE SYSTEM SHALL выполнять её для каждого PR, затрагивающего зависимости, без возможности пропустить без явного override с обоснованием

## Out of scope
- Аудит всех npm-зависимостей проекта (scope ограничен Baileys, discord.js и явно известными poisoned пакетами)
- Обновление версий Baileys или discord.js (отдельное решение; Baileys 7.0.0 ещё в rc)
- Сканирование содержимого пакетов на вредоносный код (SAST/SCA выходит за рамки данного предложения)
- Изменения в runtime openclaw
- Аудит других каналов (Slack, Telegram, Signal и т.д.) — нет зафиксированных poisoned форков
