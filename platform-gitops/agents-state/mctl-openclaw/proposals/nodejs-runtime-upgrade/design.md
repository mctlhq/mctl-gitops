# Design: nodejs-runtime-upgrade

## Текущее состояние

Согласно `context/architecture.md`, openclaw использует Node.js + TypeScript, Docker образы
собираются и деплоятся через mctl-gitops → ArgoCD в три namespace: `ovk`, `labs`, `admins`.
Текущая версия openclaw: 2026.3.14 (см. `context/current-version.md`).

Конкретная версия Node.js в базовом Docker образе не зафиксирована в context (нет явного
указания в `architecture.md`), однако Node.js January 2026 Security Release опубликован
13 января 2026: если base image не обновлялся с момента сборки 2026.3.14, вероятно
используется версия ниже безопасных порогов (v20.20.0 / v22.22.0 / v24.13.0). Это делает
три High CVE (CVE-2025-55131, CVE-2025-55130, CVE-2025-59465) потенциально активными.

Текущий CI pipeline статус `npm audit` и проверка на malicious пакеты не зафиксированы
в context — предполагается что они отсутствуют или не блокируют сборку.

## Предлагаемое решение

### 1. Base image bump в Dockerfile

Изменить строку `FROM node:XX` в Dockerfile openclaw (или в fork-специфичном Dockerfile
mctl-gitops) на Node.js v22.22.0-alpine (или эквивалентный slim образ).

Выбор v22 (LTS "Jod") обоснован:
- Это текущая Active LTS линейка на момент выхода security release (апрель 2026).
- v24.13.0 ("Krypton") выпущен 15 апреля 2026 — ещё не завершил stabilization period, хотя
  помечен LTS; для production предпочтительна проверенная линейка.
- v20.20.2 ("Iron") — Security Maintenance (только security fixes, feature-freeze).

Если текущий Dockerfile уже использует v22.x < 22.22.0 — достаточно patch тега.
Если v20.x — bump до v22.22.0 с валидацией совместимости в labs (см. задачи).

Alpine/slim вариант не влияет на RAM относительно текущего базового образа — замена
происходит в рамках той же size-категории.

### 2. CI шаг: npm audit

Добавить в CI pipeline (GitHub Actions / Argo Workflows / аналог) шаг после `npm ci`:

```
npm audit --audit-level=high --production
```

- `--audit-level=high`: блокирует только High и Critical уязвимости (medium/low — предупреждение).
- `--production`: игнорирует devDependencies в runtime audit (devDeps не попадают в Docker образ).
- Шаг выполняется до `docker build` — fast-fail до дорогостоящей сборки образа.

### 3. CI шаг: grep на malicious пакеты

Добавить shellscript-шаг в CI:

```bash
#!/bin/sh
set -e
BLOCKED="lotusbail discord.js-user"
for pkg in $BLOCKED; do
  if grep -q "\"$pkg\"" package-lock.json; then
    echo "SECURITY: malicious package '$pkg' found in lockfile" >&2
    exit 1
  fi
done
echo "Malicious package check passed."
```

Шаг выполняется перед `npm ci` — до установки зависимостей.

Список `BLOCKED` расширяется по мере появления новых raскрытий (поддерживается как
конфигурационный файл `.malicious-packages` в корне репозитория — одно имя пакета на строку).

### Rollout

Изменения в Dockerfile и CI не требуют отдельного rollout по тенантам — они применяются
на уровне сборки образа. Однако новый образ деплоится согласно ADR 0001: labs → admins → ovk.

Для `labs`: перед деплоем нового образа зафиксировать baseline RAM (kubectl top pod),
после деплоя — сравнить. Minor Node.js bump не должен давать значимого роста RAM;
если delta > 20MB — расследовать до продвижения в admins.

Restore-state probe (ADR 0002) и s3-sync canary применяются штатно при деплое нового образа.

## Альтернативы

### 1. Обновление до Node.js v24 LTS ("Krypton")

v24.15.0 выпущен 15 апреля 2026 и уже помечен LTS. Закрывает те же CVE + содержит новые
API (SQLite RC, улучшенный crypto).
- Риск: major bump (v22 → v24) может вскрыть breaking changes в зависимостях openclaw
  (в особенности native addons, если есть).
- Требует более тщательной валидации в labs.
- Отброшено для первой итерации: достаточно v22.22.0 для закрытия CVE; v24 — отдельный
  proposal при необходимости.

### 2. Dependabot / Renovate для автоматического обновления base image

Автоматический PR при выходе нового Node.js образа — устраняет ручной труд.
- Требует настройки Renovate/Dependabot в gitops репозитории.
- Выходит за рамки данного proposal (отдельная операционная задача).
- Не закрывает уже активные CVE здесь и сейчас.
Отброшено как out-of-scope; может быть добавлен как follow-up.

### 3. Использовать только `npm audit` без grep на конкретные пакеты

`npm audit` покрывает известные уязвимости в реестре npm advisories. Проблема: `lotusbail`
и `discord.js-user` — malicious пакеты, их advisory может отсутствовать в npm registry
(Koi Security раскрыла в декабре 2025, статус регистрации в npm advisory database неизвестен).
Явный grep по имени пакета является надёжным и не зависит от обновлённости advisory базы.
Отброшено: используем оба подхода параллельно.

## Влияние на платформу

### Migration / миграции

Нет миграции данных или state. Изменение ограничено:
- Dockerfile (одна строка `FROM`)
- CI pipeline конфигурация (два дополнительных шага)

### Backward compatibility

Node.js v22.22.0 совместима с большинством npm пакетов, поддерживающих Node.js >= 18.
Если текущий базовый образ использует v20.x — minor breaking changes маловероятны, но
требуют валидации в labs (TypeScript compilation, native addons, test suite).

`npm audit --production` не влияет на runtime поведение — только блокирует CI при обнаружении.

### Resource impact

- **RAM**: минимальное изменение (patch/minor bump Node.js, не major). Delta < 5MB ожидается.
  Для `labs` — **не risky**.
- **CPU**: без изменений.
- **Время сборки CI**: +30–60 секунд на `npm audit` шаг (сетевой запрос к registry).

### Риски и митигации

| Риск | Вероятность | Митигация |
|------|-------------|-----------|
| Node.js bump ломает native addon | Низкая | Валидация в labs: полный тест-прогон перед admins/ovk |
| `npm audit` выдаёт ложные срабатывания (false positives в devDeps) | Средняя | Флаг `--production` исключает devDeps; спорные findings — через `npm audit --json` разбор |
| grep не покрывает scoped-версии malicious пакетов | Низкая | Расширить regex: `lotusbail` + `@*/lotusbail` при необходимости |
| Новый образ не восстанавливает S3 state (breaking change в Node.js crypto) | Очень низкая | restore-state probe (ADR 0002) поймает до трафика в prod; откат к предыдущему образу |
