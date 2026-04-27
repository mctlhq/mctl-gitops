# Design: clawhub-skills-allowlist

## Текущее состояние
Согласно `context/architecture.md`, платформа использует 3-layer skills архитектуру:
- Layer 1: Built-in skills (compiled в core)
- Layer 2: YAML skills (hot-reload из `skills/custom/`)
- Layer 3: Remote skills (HTTP-delegated, регистрация через REST API)

Layer 3 skills регистрируются через REST API openclaw — любой клиент с доступом к API может зарегистрировать skill с произвольным remote endpoint. В текущих gitops-манифестах нет поля, ограничивающего список допустимых источников. CI-пайплайн не проверяет появление новых skill-источников. Деплой: Docker → mctl-gitops → ArgoCD, конфигурация тенантов в Helm values.

## Предлагаемое решение

**Часть 1: allowlist в Helm values (gitops)**

Добавить в Helm values каждого тенанта поле `skills.remoteAllowlist` — список допустимых URL-префиксов (или origins) для Layer 3 skills:

```yaml
# mctl-gitops/tenants/<tenant>/values.yaml
skills:
  remoteAllowlist:
    - "https://skills.mctlhq.internal/"
    # пустой список = deny-all (fail-closed)
```

Если поле отсутствует или пусто — применяется deny-all по умолчанию. Это fail-closed семантика: нет явного разрешения → нет доступа.

**Часть 2: enforcement в openclaw config**

openclaw поддерживает конфигурацию через YAML config file (Layer 2 hot-reload механизм). Добавить в `skills/custom/` (tenant-specific overlay через gitops) конфигурационный skill или использовать существующий config-механизм openclaw для задания `allowRemoteSkillSources`. При регистрации Layer 3 skill через REST API openclaw проверяет origin против allowlist и возвращает 403 при несовпадении.

Если openclaw не поддерживает нативный allowlist — реализовать через nginx/ingress middleware (admission webhook или Lua-скрипт) перед API endpoint, который фильтрует запросы на регистрацию skills по origin header. Это более инвазивный подход, но не требует upstream патча.

**Часть 3: CI-проверка**

Добавить шаг в CI-пайплайн mctl-gitops:
- Скрипт сканирует diff PR на изменения в `skills/` директориях и манифестах, связанных с Layer 3 skills
- Если обнаружен новый URL/origin, не входящий в allowlist текущего тенанта — CI падает с сообщением: "New remote skill source detected: <url>. Update allowlist in values.yaml and get security review."
- Шаг реализуется как простой bash/Python скрипт без дополнительных зависимостей

**Почему именно так:**
Конфигурационный подход (Helm values + CI) — минимальный effort, нулевой RAM impact, не требует изменений в upstream. Fail-closed семантика по умолчанию защищает тенантов, которые забыли явно задать allowlist. CI-проверка предотвращает случайное добавление неодобренных источников через gitops.

## Альтернативы

**Альтернатива 1: NetworkPolicy — блокировка ClawHub на сетевом уровне**
Kubernetes NetworkPolicy можно настроить так, чтобы поды openclaw не могли обращаться к IP-диапазонам ClawHub. Отброшено: требует поддержания актуального списка IP ClawHub (меняются), не защищает от skills, хостящихся на других доменах, и не решает проблему для skills, уже зарегистрированных в системе. Более широкая мера, не заменяет allowlist.

**Альтернатива 2: Upstream feature request — allowlist в openclaw core**
Запросить в upstream openclaw добавление нативного allowlist для remote skills. Отброшено: слишком долго (кампания активна сейчас); не гарантирует включение в ближайший релиз; решение нужно немедленно. Можно сделать параллельно как долгосрочную меру.

**Альтернатива 3: Полное отключение Layer 3 skills на всех тенантах**
Самый быстрый способ закрыть вектор — выключить remote skills регистрацию. Отброшено: возможно, легитимные Layer 3 skills уже используются в ovk или admins; отключение без инвентаризации может сломать продуктивный функционал. Allowlist с явно разрешёнными источниками — более точный и управляемый подход.

## Влияние на платформу

**Migration/миграции**
Перед включением deny-all политики необходимо провести инвентаризацию текущих зарегистрированных Layer 3 skills на каждом тенанте и добавить их источники в allowlist. Иначе легитимные skills перестанут работать.

**Backward compatibility**
Изменение затрагивает поведение REST API openclaw для Layer 3 skills. Существующие skills, зарегистрированные до введения allowlist, не затрагиваются (они уже в системе), но попытки повторной регистрации или обновления будут проверяться по allowlist. Необходимо документировать процесс обновления allowlist для операторов.

**Resource impact**
- labs: NO IMPACT. Изменение только конфигурационное (Helm values + CI), без прироста RAM.
- admins: NO IMPACT.
- ovk: NO IMPACT.

**Риски и митигации**
- Легитимные Layer 3 skills заблокированы при неполном allowlist → провести инвентаризацию skills перед включением политики; начать с admins (минимальный blast radius), затем labs, затем ovk
- Оператор обходит CI-проверку через прямой коммит в main → защитить ветку main branch protection rule с обязательным CI
- allowlist задан слишком широко (например, `https://clawhub.io/`) → документировать политику: только явные проверенные origins, не wildcard домены ClawHub
- hot-reload конфига не применяется без рестарта → проверить поведение openclaw при изменении config через YAML; при необходимости предусмотреть graceful reload или rolling restart
