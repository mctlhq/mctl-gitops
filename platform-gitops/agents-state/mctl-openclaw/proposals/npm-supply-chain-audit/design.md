# Design: npm-supply-chain-audit

## Текущее состояние
Согласно `context/architecture.md`, openclaw использует Node.js + TypeScript workspace. WhatsApp-канал реализован через `@whiskeysockets/baileys`, Discord — через `discordjs/discord.js`. Зависимости управляются через `package.json` / `package-lock.json`. Деплой: Docker → mctl-gitops → ArgoCD. Текущий CI-пайплайн не содержит явной проверки resolved URLs пакетов или запрещённых имён. Факт использования корректных пакетов сейчас не верифицирован автоматически.

Зафиксированные угрозы (inbox/2026-04-27.md):
- Poisoned Baileys-форк (2025-12): перехват WhatsApp auth, сообщений, контактов, медиа через WebSocket wrapper
- `discord.js-user` (GHSA-69r6-7h4f-9p7q, CVSS 9.8): слив Discord-токенов

## Предлагаемое решение

**Часть 1: Одноразовый аудит (немедленно)**

Выполнить `grep`-аудит `package-lock.json` и `package.json` на предмет:
1. Запрещённых имён: `baileys` (без namespace), `discord.js-user`, и любых других известных poisoned форков
2. resolved URLs для `@whiskeysockets/baileys` и `discord.js` — должны указывать на `https://registry.npmjs.org/`
3. Запустить `npm audit --audit-level=high` и зафиксировать результат

Результат аудита документируется: либо "всё чисто + подтверждено", либо список проблем для немедленного исправления.

**Часть 2: CI-шаг (постоянный)**

Добавить в CI-пайплайн скрипт `scripts/check-npm-supply-chain.sh` (или аналогичный в Python/Node):

```bash
# Проверка запрещённых имён пакетов
FORBIDDEN="baileys discord.js-user"
for pkg in $FORBIDDEN; do
  if grep -q "\"$pkg\"" package-lock.json; then
    echo "BLOCKED: forbidden package '$pkg' found in package-lock.json"
    exit 1
  fi
done

# Проверка resolved URL для monitored пакетов
MONITORED="@whiskeysockets/baileys discord.js"
for pkg in $MONITORED; do
  urls=$(jq -r ".. | objects | select(.name? == \"$pkg\") | .resolved" package-lock.json 2>/dev/null)
  for url in $urls; do
    if [[ "$url" != "https://registry.npmjs.org/"* ]]; then
      echo "BLOCKED: package '$pkg' resolved from non-official registry: $url"
      exit 1
    fi
  done
done
```

Скрипт запускается при каждом изменении `package.json` или `package-lock.json` в PR. Дополнительно: `npm audit --audit-level=high` для пакетов из списка мониторинга.

**Почему именно так:**
Минимальный и точечный подход — проверяем только конкретные known-bad пакеты и их resolved URLs. Не требует внешних SCA-инструментов, работает с тем что есть в CI. Одноразовый аудит закрывает вопрос о текущем состоянии; постоянный CI-шаг предотвращает регрессию.

## Альтернативы

**Альтернатива 1: Полный SCA-инструмент (например, Snyk, Socket Security)**
Socket Security специализируется именно на supply chain атаках через npm и умеет детектировать poisoned форки на уровне поведенческого анализа. Отброшено для данного предложения: требует внешней интеграции, licensing, настройки — значительно больший effort при том что известные угрозы конкретны и покрываются простым скриптом. Можно добавить позже как дополнительный слой.

**Альтернатива 2: npm `overrides` / `resolutions` для пиннинга пакетов**
В `package.json` можно использовать `overrides` (npm 8+) чтобы форсировать конкретные версии и исключить форки:
```json
"overrides": { "baileys": "npm:@whiskeysockets/baileys@latest" }
```
Отброшено как основной механизм: это защищает от transitive dependency подмены, но не детектирует случай когда кто-то явно добавил запрещённый пакет в `dependencies`. CI-проверка более явна и аудируема. `overrides` можно добавить дополнительно.

**Альтернатива 3: Lockfile integrity check через `npm ci` в Docker build**
`npm ci` использует `package-lock.json` и отказывается если lock не соответствует `package.json`. Отброшено как достаточная мера: `npm ci` не проверяет имена пакетов на запрещённые — если `package-lock.json` уже содержит poisoned пакет, `npm ci` спокойно его установит. CI-скрипт нужен поверх.

## Влияние на платформу

**Migration/миграции**
Нет миграций. Одноразовый аудит + добавление CI-скрипта и конфига в репозиторий.

**Backward compatibility**
CI-шаг не затрагивает runtime. Если текущие пакеты корректны (ожидаемо) — CI будет просто проходить. Если обнаружена проблема — требует немедленного исправления `package.json`/`package-lock.json`.

**Resource impact**
- labs: NO IMPACT. Изменения только в CI, не в деплое.
- admins: NO IMPACT.
- ovk: NO IMPACT.

**Риски и митигации**
- Аудит обнаружит poisoned пакет в текущем `package-lock.json` → немедленно заменить пакет, пересобрать lock, провести emergency redeploy всех тенантов; WhatsApp/Discord credentials считать скомпрометированными (ротация токенов)
- Скрипт даёт false positive из-за зеркальных реестров (например, корпоративный Verdaccio) → добавить в allowlist корпоративные registry prefix'ы при необходимости
- Скрипт не покрывает новые poisoned пакеты, появившиеся после его написания → периодически (раз в квартал) пересматривать список `FORBIDDEN` и `MONITORED` пакетов
- Разработчик использует `--ignore-scripts` или другой обход → CI шаг обязателен (branch protection), не может быть пропущен без явного approval security engineer'а
