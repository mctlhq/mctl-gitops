# План развития MCTL

> Статус: один кластер `mctl-preprod` (Hetzner, k3s v1.33, 1 control-plane + 3 workers),
> клиентов пока нет. Прод-кластер сознательно отложен до появления первого клиента.
> План откалиброван под solo-разработку с Claude-агентами: минимум обязательного
> hardening + максимум готовности к первым клиентам. Обновлять по мере выполнения.

## 0. Что показала сверка внешнего аудита с кодом

Внешний обзор (по публичным докам) в ключевых местах разошёлся с реальностью:

| Утверждение аудита | Реальность | Где проверено |
|---|---|---|
| «Бэкапов нет» | **Неверно.** CNPG barman → R2 (daily, retention 14d), Vault raft snapshot → R2 (daily, 30 копий), vmbackup → R2 | `infra-components/data/cnpg/shared/`, `bootstrap/templates/core-infra/vault-backup.yaml`, `bootstrap/templates/observability/monitoring.yaml` |
| «Preview делит секреты с prod» | **Закрыто.** Preview ставится в `{team}-preview`; tenant Vault-пути переписываются на `teams/<team>/<service>/preview/*`; NetworkPolicy не пускает в prod-namespace | `argo-workflows/cluster-templates/wft-preview-deploy.yaml`, `helm-charts/tenant/templates/preview.yaml` |
| «Long-lived MCTL_GITHUB_TOKEN в auto-deploy» | **Закрыто для GHA Vault.** `build-image.yaml` ходит в Vault через GitHub OIDC JWT (роль `github-actions`); in-cluster токен GitHub App по-прежнему ротируется каждые 30 мин | `.github/workflows/build-image.yaml`, `vault-policy-github-actions-repo-pat.hcl`, `cwft-rotate-github-token.yaml` |
| «blue-green by default» vs «rolling by default» | Код: rolling через ArgoCD sync; blue-green в base-service есть, но opt-in. Доки противоречат друг другу | `helm-charts/base-service/`, mctl-docs `guides/services.md:82` vs `guides/rollbacks.md:24` |
| «Изоляция тенантов не подтверждена» | Есть: default-deny NetworkPolicy, ResourceQuota, LimitRange, PSS baseline; `allowInternetEgress: false` по умолчанию (см. 3.2) | `helm-charts/tenant/templates/`, `values.yaml` |

Реальные пробелы, подтверждённые кодом: etcd-снапшоты в S3/R2 на preprod подготовлены,
но не включены на живом CP (бакет `mctl-etcd-snapshots` создан 2026-08-15, terraform
описывает выгрузку; apply — [gitops#841](https://github.com/mctlhq/mctl-gitops/issues/841));
HPA opt-in и почти не используется; prod-кластер — заглушки.
Закрыто с момента написания: restore drills CNPG/Vault проведены 2026-08-14, состояние
mctl-agent переехало в Postgres (2.2), retention CNPG поднят до 14d, PDB у CNPG, Traefik,
mctl-api и Argo CD server/repo-server (3.4). SOC-реестр F1–F20 закрыт 2026-08-15
(agent inbound auth 1.15.3, preview isolation, portal 4.11.2, Vault JWT/OIDC).

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
Непроверенный бэкап = отсутствие бэкапа. Drills проведены 2026-08-14, журнал —
`docs/runbooks/restore.md`.
- [x] Restore drill CNPG: восстановлен в `pg-restore-drill` из barmanObjectStore, данные
  сверены (`catalog.final_entities=55` совпало с prod); drill 2026-08-14.
- [x] Restore drill Vault: `vault operator raft snapshot restore` снапшота из R2 в
  throwaway Vault, `secret/platform/` читается; drill 2026-08-14.
- [x] Retention CNPG поднят до `14d` (`infra-components/data/cnpg/shared/cluster.yaml`).
- [~] Настроить k3s etcd-снапшоты в S3/R2 на preprod — бакет `mctl-etcd-snapshots`
  создан 2026-08-15, `kube.tf` описывает `etcd_s3_backup` (6h, retention 56 = 14d).
  Живой CP всё ещё без `--etcd-s3` (локальные снапшоты ~12h). Операторский apply:
  [gitops#841](https://github.com/mctlhq/mctl-gitops/issues/841). При одном
  control-plane это единственная защита состояния кластера.
- [x] Записать результаты как runbook `docs/runbooks/restore.md` (в этом репо).

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
- [~] Разобрать Dependabot-долг на default-ветках:
  - [x] mctl-web: июль 29 → 0; августовская волна 34 → 0 в [mctl-web#55](https://github.com/mctlhq/mctl-web/pull/55)
    (npm audit fix + wrangler 4.87→4.123, CI green, Claude APPROVED; merge pending
    на branch protection).
  - [ ] mctl-docs: заблокировано из CI-среды — приватный пакет `@mctlhq/css`
    требует PAT с `read:packages`. Выполнить локально: `npm audit fix`, затем
    `npm run build`. Остаток esbuild/vite закрывается только апгрейдом VitePress.
  - [ ] mctl-portal: 162 (19 critical) — в основном транзитивные зависимости
    Backstage; закрывать плановым Backstage upgrade, не точечными резолюциями.

### 2.4 Продукт: путь первого клиента
- [ ] Пройти самому весь путь «нулевого пользователя» по `first-user-checklist` и `deploy-first-app`, зафиксировать все шероховатости как issues.
- [ ] Публичный демо-тенант / записанное демо (2–3 мин): создание тенанта → деплой сервиса → preview → self-healing PR от агента. Self-healing через PR — главный дифференциатор, его надо показывать.
- [ ] Определить ICP: кому продаём в первую очередь (малые команды без DevOps? агентства? AI-стартапы, которым нужен hosting для агентов?). От этого зависят следующие фичи.

## 3. Горизонт 1 — до онбординга первого внешнего клиента (блокеры)

Эти пункты не срочны, пока платформой пользуетесь только вы, но **обязательны до того,
как чужой код и чужие люди появятся на кластере**.

### 3.1 Изоляция preview от production-секретов (блокер №1)
Сейчас preview из любой ветки получает полные production-креды команды.
- [x] Вариант-минимум: отдельный namespace `{team}-preview` (через tenant chart) + собственные ExternalSecret'ы на отдельные Vault-пути `secret/data/teams/<team>/<service>/preview/*`.
- [x] Обновить `wft-preview-deploy.yaml` / `wft-preview-delete.yaml` и NetworkPolicy: preview не ходит в prod-namespace.

### 3.2 Ужесточить дефолты изоляции
- [x] `allowInternetEgress: false` по умолчанию — в чарте tenant, Backstage-шаблоне
  и wft-create-tenant. Существующие тенанты задают флаг явно, их поведение
  не изменилось; workflow-поды сохраняют egress через отдельную политику.
- [~] PSS `restricted` для tenant-namespaces — в два шага:
  - [x] Шаг 1: `audit`/`warn` labels подняты до `restricted` при `enforce: baseline`
    (`podSecurityObserveLevel` в tenant-чарте) — apiserver пишет каждое would-be
    нарушение в audit-log и warnings, ничего не ломая (#838).
  - [ ] Шаг 2: по собранным нарушениям флипнуть `podSecurityLevel: restricted`
    per-tenant там, где base-service проходит; workflow-поды с root-`chown`
    остаются на `baseline`. Напоминание 2026-08-29.

### 3.3 Сократить long-lived секреты в CI
- [x] Заменить `VAULT_TOKEN` в `build-image.yaml` на Vault JWT/OIDC auth для GitHub Actions (роль `github-actions`, policy `github-actions-repo-pat`; one-time `vault auth enable jwt` в `vault-config/README.md`).
- [ ] Убрать fallback-секреты `GHCR_PAT` / `GH_PACKAGES_TOKEN`, если основной путь стабилен.

### 3.4 Операционный минимум для чужих нагрузок
- [x] PDB для платформенных компонентов (mctl-api, Traefik, ArgoCD) — не для tenant-приложений.
  Traefik already 3 replicas + maxUnavailable 33%; mctl-api and Argo CD
  server/repo-server get minAvailable 1. Second CP node stays Horizon 2.
  See `docs/runbooks/control-plane.md`.
- [ ] Включить HPA (шаблон уже есть в base-service) для mctl-api как референс.
- [x] Мини-runbook «что делать при падении single control-plane» — честно задокументировать ограничение preprod (`docs/runbooks/control-plane.md`).

## 4. Горизонт 2 — есть первый платящий клиент

Триггер: подписан первый клиент / появилась реальная чужая нагрузка.

- [ ] **Прод-кластер**: `infrastructure/k3s-prod/` из стаба в реальный Terraform — 3 control-plane (HA etcd + S3 snapshots), отдельный LB, `applicationset-prod.yaml`. Preprod остаётся staging'ом платформы.
  Vault в прод-кластере поднимается с TLS-listener'ом с первого дня (серты от
  cert-manager до первого unseal) — закрывает SOC F15 без ретрофита. На preprod
  `tls_disable = 1` остаётся accepted residual (edge TLS на Traefik, NetworkPolicy;
  см. комментарий в `bootstrap/templates/core-infra/vault.yaml` и
  `docs/runbooks/control-plane.md`): миграция живого raft-кворума на https — это
  неконтейнящийся откат ради защиты от атакующего, который уже сидит в CNI.
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
