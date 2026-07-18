# План развития MCTL

> Статус: один кластер `mctl-preprod` (Hetzner, k3s v1.33, 1 control-plane + 3 workers),
> клиентов пока нет. Прод-кластер сознательно отложен до появления первого клиента.
> План откалиброван под solo-разработку с Claude-агентами: минимум обязательного
> hardening + максимум готовности к первым клиентам. Обновлять по мере выполнения.

## 0. Что показала сверка внешнего аудита с кодом

Внешний обзор (по публичным докам) в ключевых местах разошёлся с реальностью:

| Утверждение аудита | Реальность | Где проверено |
|---|---|---|
| «Бэкапов нет» | **Неверно.** CNPG barman → MinIO (daily, retention 3d), Vault raft snapshot → R2 (daily, 30 копий), vmbackup → R2 | `infra-components/data/cnpg/shared/`, `bootstrap/templates/core-infra/vault-backup.yaml`, `bootstrap/templates/observability/monitoring.yaml` |
| «Preview делит секреты с prod» | **Верно.** Helm release preview ставится в namespace команды и монтирует те же Secret'ы | `argo-workflows/cluster-templates/wft-preview-deploy.yaml` (описание в самом шаблоне) |
| «Long-lived MCTL_GITHUB_TOKEN в auto-deploy» | **Неточно.** В коде такого токена нет — это ручная инструкция в доках. Реальный long-lived секрет — `VAULT_TOKEN` в GHA `build-image.yaml`; in-cluster токен GitHub App ротируется каждые 30 мин | `.github/workflows/build-image.yaml:88-96`, `cwft-rotate-github-token.yaml` |
| «blue-green by default» vs «rolling by default» | Код: rolling через ArgoCD sync; blue-green в base-service есть, но opt-in. Доки противоречат друг другу | `helm-charts/base-service/`, mctl-docs `guides/services.md:82` vs `guides/rollbacks.md:24` |
| «Изоляция тенантов не подтверждена» | Есть: default-deny NetworkPolicy, ResourceQuota, LimitRange, PSS baseline. Но `allowInternetEgress: true` по умолчанию | `helm-charts/tenant/templates/`, `values.yaml:58` |

Реальные пробелы, подтверждённые кодом: etcd-снапшоты не настроены на preprod (только TODO
в `infrastructure/k3s-prod/README.md`), restore ни разу не проверялся, состояние mctl-agent
в SQLite на поде без бэкапа, retention CNPG всего 3 дня, HPA opt-in и почти не используется,
PDB только у CNPG, prod-кластер — заглушки.

## 1. Принцип приоритизации

Клиентов нет → главный риск не «упадёт прод», а «продукт никому не продан».
Поэтому:

1. **Не делаем** энтерпрайз-hardening впрок (multi-region, service mesh, Velero,
   VPA, cosign/provenance, compliance mapping, distributed tracing, формальные SLO).
   Всё это имеет смысл при живой нагрузке и появится в Горизонте 2–3.
2. **Делаем сейчас** только то, что (а) защищает от невосстановимой потери
   (данные, состояние), (б) дёшево и повышает доверие первого клиента
   (консистентные доки), (в) убирает блокеры онбординга внешних людей.

## 2. Горизонт 0 — ближайшие 2–4 недели

### 2.1 Проверить, что бэкапы реально восстанавливаются (главный технический риск)
Бэкапы настроены, но ни один restore не проводился. Непроверенный бэкап = отсутствие бэкапа.
- [ ] Restore drill CNPG: поднять кластер из barmanObjectStore в отдельный namespace, сверить данные.
- [ ] Restore drill Vault: `vault operator raft snapshot restore` из R2 в тестовый Vault (можно kind/локально).
- [ ] Поднять retention CNPG с `3d` до `14d`–`30d` (`infra-components/data/cnpg/shared/cluster.yaml`).
- [ ] Настроить k3s etcd-снапшоты в S3/R2 на preprod (сейчас TODO только для будущего prod) — при одном control-plane это единственная защита состояния кластера.
- [ ] Записать результаты как runbook `docs/runbooks/restore.md` (в этом репо).

### 2.2 Убрать невосстановимое состояние mctl-agent
- [x] **Уже сделано** (обнаружено при проверке): деплой агента задаёт
  `DATABASE_URL` на shared-pg (`bootstrap/templates/mctl-platform/mctl-agent.yaml`),
  `persistence.data.enabled: false` — всё состояние в Postgres и покрыто CNPG-бэкапом.
  SQLite остался только как дефолт для локальной разработки. Осталось обновить
  CLAUDE.md агента, который всё ещё описывает SQLite как основное хранилище (→ 2.3).
- [x] **CNPG-бэкапы переведены с in-cluster MinIO на R2** (`s3://vault-backup/postgres-backups/shared-pg`,
  креды из Vault `platform/vault/r2-backup`; одноразовый Backup CR сеет первый
  базовый бэкап). Раньше бэкапы Postgres погибали вместе с кластером.
  Проверить после merge: Secret `cnpg-backup-r2` синкается, `shared-pg-r2-initial`
  завершился, в R2 появился `base/` каталог.

### 2.3 Закрыть документационный drift (дёшево, критично для доверия)
Первый потенциальный клиент читает docs.mctl.ai; противоречия хуже пробелов.
- [x] Единая deployment matrix: rolling — default, blue-green — opt-in (`guides/services.md`).
- [x] Единая модель секретов БД: Vault → ExternalSecret → K8s Secret, переменные `DB_*` + `DATABASE_URL` (`guides/databases.md`).
- [x] Число MCP tools: везде 62 (по `server_test.go`); в таблицу добавлен пропущенный `mctl_trigger_incident_responder`.
- [x] CLAUDE.md синхронизированы: mctl-agent (12 skills, Postgres-хранилище), mctl-portal (9 плагинов, `proposals-backend`), mctl-web (Nuxt 4).
- [ ] Разобрать Dependabot-долг на default-ветках (обнаружено при пуше):
  mctl-portal — 162 (19 critical), mctl-web — 56 (1 critical), mctl-docs — 23.
  Минимум: закрыть critical/high; для portal это в основном транзитивные
  зависимости Backstage — сначала попробовать плановый Backstage upgrade.

### 2.4 Продукт: путь первого клиента
- [ ] Пройти самому весь путь «нулевого пользователя» по `first-user-checklist` и `deploy-first-app`, зафиксировать все шероховатости как issues.
- [ ] Публичный демо-тенант / записанное демо (2–3 мин): создание тенанта → деплой сервиса → preview → self-healing PR от агента. Self-healing через PR — главный дифференциатор, его надо показывать.
- [ ] Определить ICP: кому продаём в первую очередь (малые команды без DevOps? агентства? AI-стартапы, которым нужен hosting для агентов?). От этого зависят следующие фичи.

## 3. Горизонт 1 — до онбординга первого внешнего клиента (блокеры)

Эти пункты не срочны, пока платформой пользуетесь только вы, но **обязательны до того,
как чужой код и чужие люди появятся на кластере**.

### 3.1 Изоляция preview от production-секретов (блокер №1)
Сейчас preview из любой ветки получает полные production-креды команды.
- [ ] Вариант-минимум: отдельный namespace `{team}-preview` (через tenant chart) + собственные ExternalSecret'ы на отдельные Vault-пути `secret/data/teams/<team>/<service>/preview/*`.
- [ ] Обновить `wft-preview-deploy.yaml` / `wft-preview-delete.yaml` и NetworkPolicy: preview не ходит в prod-namespace.

### 3.2 Ужесточить дефолты изоляции
- [x] `allowInternetEgress: false` по умолчанию — в чарте tenant, Backstage-шаблоне
  и wft-create-tenant. Существующие тенанты задают флаг явно, их поведение
  не изменилось; workflow-поды сохраняют egress через отдельную политику.
- [ ] PSS `restricted` для tenant-namespaces (сейчас `baseline`); проверить, что base-service проходит.

### 3.3 Сократить long-lived секреты в CI
- [ ] Заменить `VAULT_TOKEN` в `build-image.yaml` на Vault JWT/OIDC auth для GitHub Actions (паттерн ротации через GitHub App уже есть в `cwft-rotate-github-token.yaml` — переиспользовать подход).
- [ ] Убрать fallback-секреты `GHCR_PAT` / `GH_PACKAGES_TOKEN`, если основной путь стабилен.

### 3.4 Операционный минимум для чужих нагрузок
- [ ] PDB для платформенных компонентов (mctl-api, Traefik, ArgoCD) — не для tenant-приложений.
- [ ] Включить HPA (шаблон уже есть в base-service) для mctl-api как референс.
- [ ] Мини-runbook «что делать при падении single control-plane» — честно задокументировать ограничение preprod.

## 4. Горизонт 2 — есть первый платящий клиент

Триггер: подписан первый клиент / появилась реальная чужая нагрузка.

- [ ] **Прод-кластер**: `infrastructure/k3s-prod/` из стаба в реальный Terraform — 3 control-plane (HA etcd + S3 snapshots), отдельный LB, `applicationset-prod.yaml`. Preprod остаётся staging'ом платформы.
- [ ] Промоушен-путь preprod → prod для платформенных компонентов (сейчас всё катится сразу в единственный кластер).
- [ ] Базовые SLO: доступность mctl-api, успешность deploy-workflow, ArgoCD sync lag, успешность бэкапов; алерты на error budget вместо интуиции.
- [ ] Cost-дашборд по tenant/namespace (данные уже есть в VictoriaMetrics) + TTL-очистка preview (ttl_hours уже есть — проверить фактическую отработку).
- [ ] Периодический автоматический restore-drill (CronWorkflow) вместо ручного.

## 5. Горизонт 3 — рост (несколько клиентов)

Только по фактической потребности, не впрок:
- OpenTelemetry/tracing — когда появятся multi-hop инциденты, которые нечем разбирать.
- Cosign/provenance + admission policy (Kyverno) — когда клиенты начнут спрашивать про supply chain.
- Упрощение self-hosting (сокращение hardcoded refs) — когда появится спрос на self-hosted.
- Compliance mapping (CIS/SOC2-lite) — когда попросит первый enterprise-лид.

## 6. Чего в плане сознательно нет

Multi-region/multi-zone, service mesh, Velero (CNPG+Vault+etcd снапшоты закрывают
критичное состояние), VPA, выделенные node pools, WORM-архив аудита. Причина одна:
на текущем масштабе это расход времени, который не приближает первого клиента и
не защищает от невосстановимых потерь.
