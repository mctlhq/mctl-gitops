# План развития MCTL

> **Статус на 2026-10-23.** Один кластер `mctl-preprod` (Hetzner, k3s v1.34.12,
> 1 control-plane + 3 workers), который де-факто уже прод: на нём первый тенант
> с внешними людьми (`erpact`, 4 участника), 27 сервисов, 6 тенантов. Путь
> самообслуживания (заявка → ZITADEL → workspace → MCP) построен и прошёл
> приёмку в проде 2026-10-17, но публичная регистрация закрыта
> (`AUTH_FLOW_PUBLIC=false`): работает waitlist с ручным одобрением, а
> ёмкость под новые workspace — **1 слот** (память переподписана: 49.9 GiB
> committed при 43.98 GiB allocatable). Платящих клиентов и биллинга нет.
> Исполнитель — один человек + Claude-агенты. Обновлять по мере выполнения.
>
> Визуальная версия этого плана — артефакт
> <https://claude.ai/artifact/9xF29UW7dcxVPp91rZBpL7>. **При любом изменении
> этого файла обновлять и артефакт** (тот же URL, через Artifact tool с `url`),
> чтобы страница и источник не расходились.

## 0. Что изменилось с августа

Предыдущая версия плана (июль–август) исходила из «клиентов нет → главный риск,
что продукт никому не продан». За два месяца ситуация перевернулась: продукт
доведён до рабочего onboarding, на кластере появились чужие люди, и теперь
ограничивает не продукт, а инфраструктура и операционная зрелость.

| Было в плане | Стало | Где |
|---|---|---|
| Горизонт 0 целиком (бэкапы, drills, retention, etcd→R2, doc drift) | **Выполнен.** Drills CNPG/Vault 08-14, etcd→R2 08-15, CNPG→R2 и Barman Cloud Plugin, drill R2-линии 10-19 и 10-23 | `docs/runbooks/restore.md` |
| Preview делит секреты с prod (блокер №1) | **Закрыто**: `{team}-preview`, отдельные Vault-пути, NetworkPolicy; hourly reaper по TTL | `wft-preview-deploy.yaml`, `tenant/templates/preview*.yaml` |
| `VAULT_TOKEN` в GHA | **Закрыто**: GitHub OIDC JWT → Vault | `build-image.yaml` |
| PSS `restricted` | 4 из 6 тенантов (`admins`, `labs`, `karabu`, `mctl`); `erpact`, `commerce-proof` — `baseline` | `tenants/*/values.yaml` |
| «Tracing — не делаем впрок» (Горизонт 3) | **Пересмотрено и сделано**: OTel collector (#902) + Tempo принят 2026-10-22 (#1280). Ограничение: partial reads (5 092 из 6 930 спанов) — не для SLO | `docs/runbooks/tempo.md`, `docs/adr/0001-*` |
| «Admission policy (Kyverno) — потом» | Сделано нативно: ValidatingAdmissionPolicy как backstop для NetworkPolicy (#800) | `bootstrap/templates/system/admission-policies.yaml` |
| «SOC 2 — когда попросит enterprise-лид» | Type I **binder** собран (control-matrix, risk-register, assertion 08-19, CUECs, evidence). Не аттестация | `docs/soc2/` |
| Единый IdP | **ZITADEL** (v4, auth.mctl.ai) для Forgejo, Grafana, Vault human-auth, API, portal, kubectl, customers-org | `docs/runbooks/zitadel.md` |
| — | Новые компоненты: **Forgejo** (git.mctl.ai, ежедневный авто-drill restore), **Valkey** (events bus), **Temporal** (оркестрация агентов вместо Argo), Grafana и Cloudflare как IaC (**OpenTofu**, state backup daily в R2) | `docs/runbooks/` |
| Прод-кластер по триггеру «первый клиент» | **Не начат** — `k3s-prod/` и `applicationset-prod.yaml` остались заглушками, хотя триггер фактически сработал | `infrastructure/k3s-prod/README.md` |

Масштаб: 27 сервисов, 34 ClusterWorkflowTemplate, 19 runbook'ов, 26 файлов
алертов (с unit-тестами), ~100 MCP tools (в docs — 92 строки, число в прозе
убрано в пользу `tools/list`), mctl-api 4.118, mctl-agent 2.5, mctl-agents 1.96.

## 1. Принцип приоритизации (пересмотрен)

Чужие люди уже на кластере, а публичный вход упирается в ёмкость → главный
риск сместился с «не продано» на «не выдержим первых пользователей». Поэтому:

1. **Сначала** — то, что физически открывает регистрацию (ёмкость, launch-гейты)
   и защищает уже живущих на кластере внешних пользователей (HA control-plane,
   автоматические drills, SLO платформы).
2. **Параллельно** — закрыть хвосты, которые уже один раз стреляли
   (`GHCR_PAT` истёк 10-12 и сломал release-deploy; docs отстают от реального
   funnel).
3. **Не делаем** впрок: биллинг до первого платящего, второй кластер до того,
   как HA внутри текущего не исчерпан, multi-region, service mesh.

## 2. Горизонт 0 — ближайшие 2–4 недели: открыть вход

### 2.1 Ёмкость кластера (блокер регистрации)
- [ ] Поднять allocatable: +1 worker `cx43` (или апгрейд типов) через `kube.tf`;
  цель — автоматический admission-budget ≥ 5 starter-workspace вместо 1.
- [ ] Пройтись по requests платформенных компонентов — overcommit 49.9/44 GiB
  создают в основном они, а не тенанты; снять завышенные requests там, где
  фактическое потребление в разы ниже (данные уже в VictoriaMetrics).
- [ ] После этого — пересчитать `mctl_signup_capacity` и одобрить ждущую заявку.

### 2.2 Launch-гейты самообслуживания (из `site-onboarding-review.md`)
- [ ] Свежий e2e-прогон под **не-admin** учёткой.
- [ ] Контролируемый тест «provisioning упал → восстановление» (workspace не
  должен остаться в полусозданном состоянии; проверить release слота).
- [ ] Docs: `getting-started/` и `first-user-checklist.md` до сих пор описывают
  «request access, then confirm with your operator» — переписать под реальный
  flow: заявка → письмо-решение → вход через ZITADEL/GitHub → starter workspace
  → подключение MCP. Слово «invitation» в docs не встречается ни разу.
- [ ] Stage C1c: убрать legacy GitHub OAuth на сайте (после 31.10 по плану).

### 2.3 Хвосты, которые уже стреляли
- [ ] **Добить `GHCR_PAT`/`GH_PACKAGES_TOKEN`**: допереключить mctl-web, mctl-docs,
  mctl-academy (`build-image.yaml:553`, `release-deploy.yaml:145-161`) на
  `GITHUB_TOKEN`, затем удалить оба секрета. PAT истёк 2026-10-12 молча.
- [ ] Vault ACL-инцидент Valkey 09-17 (`#` в ACL-файле валит старт) — добавить
  lint ACL в `validate-manifests.yml`.
- [x] mctl-agent `CLAUDE.md` снова отстал (9 skills / SQLite / Go 1.24 при 12 /
  Postgres / Go 1.26) — обновлён, и добавлен `TestClaudeMDSkillCount`, который
  сверяет число skills в CLAUDE.md с `register.go`, как `server_test.go` делает
  для tools ([mctl-agent#180](https://github.com/mctlhq/mctl-agent/pull/180)).

## 3. Горизонт 1 — квартал: выдержать первых пользователей

### 3.1 HA control-plane вместо отдельного прод-кластера
Решение, которое нужно принять явно. Два варианта:
- **A (рекомендуется):** сделать `mctl-preprod` трёхузловым по control-plane
  (`count: 3` для `control-plane-fsn1` в `kube.tf`; etcd-кворум, включается
  обратно `automatically_upgrade_os`). Один оператор не вытянет два кластера;
  текущий уже прод по факту. Переименование — косметика на потом.
- **B:** реальный `k3s-prod/` + промоушен preprod→prod. Честнее по
  архитектуре, но удваивает операционную нагрузку и стоимость.
- [ ] Принять решение, записать ADR 0002, выполнить. Закрывает SOC2 risk R2/F11.
- [ ] Vault с TLS-listener'ом — при варианте A это отдельная миграция raft на
  https (сейчас accepted residual, см. `control-plane.md`); при B — с первого дня.

### 3.2 Автоматические restore drills (по образцу Forgejo)
- [ ] CronWorkflow еженедельного CNPG-drill: восстановить в `pg-restore-drill`,
  сверить число БД/таблиц с prod, удалить, выставить метрику → алерт на
  staleness (как `ForgejoRestoreDrillStale`).
- [ ] То же для Vault (raft restore в throwaway Vault, `kv list`).
- [ ] **etcd restore drill так и не проводился** — только проверка наличия
  снапшотов. Провести хотя бы раз вручную (на отдельной VM по
  `restore.md §3`), прежде чем менять топологию control-plane в 3.1.

### 3.3 SLO платформы
Паттерн готов (`vm-rules/mctl-telegram-slo.yaml`, burn-rate multi-window,
тесты). Распространить на платформу:
- [ ] mctl-api availability и latency.
- [ ] Успешность deploy-workflow и `create-tenant`.
- [ ] Argo CD sync lag.
- [ ] Успешность бэкапов (staleness-алерты уже есть в `backup-alerts.yaml`,
  оформить как SLO с бюджетом).
- [ ] Error-budget merge-freeze из `backup-alerts.yaml:118` — задокументировать
  как политику.

### 3.4 Стоимость per-tenant
Starter — бесплатный; без цены workspace нельзя планировать ёмкость и pricing.
- [ ] Дашборд cost по tenant/namespace (CPU/mem requests × цена узла, storage —
  уже есть в FinOps-дашборде).
- [ ] Выполнить `docs/plans/argo-local-workdir.md` (13 133 десятигигабайтных
  тома в июньском счёте).

### 3.5 Изоляция и governance
- [ ] PSS `restricted` для `erpact` и `commerce-proof` (по собранным audit-нарушениям).
- [ ] HPA для mctl-api как референс (replicaCount уже 2, шаблон есть).
- [ ] ADR 014 policy checkpoint: 6 surfaces из `staged` в live; закрыть обход
  через Bash/`MCTL_TOKEN` (mctl-agents#717, mctl-api#723); заполнить T5/T6.
- [ ] Stage E onboarding: явные grants и revocation для customers.
- [ ] Tempo: решить с partial reads (5 092/6 930) и WAL на emptyDir — либо
  починить, либо зафиксировать как accepted и не строить на нём SLO.

### 3.6 Dependabot
- [ ] mctl-docs — локально (`@mctlhq/css` требует `read:packages`).
- [ ] mctl-portal — плановый Backstage upgrade (portal 4.27.1).

## 4. Горизонт 2 — первый платящий

Триггер: Professional-клиент готов платить, или starter-слоты заканчиваются.
- [ ] Биллинг: Stripe (или счета вручную для первых 3–5) поверх `internal/usage`;
  commerce-ledger остаётся симулированным, пока нет живого PaymentAuthorizer.
- [ ] `erpact` stopgap (`internal/erpactsites`, только tenant `erpact`) — либо
  обобщить в «managed app» абстракцию, либо явно оставить bespoke-контрактом.
- [ ] SOC 2: из Type I binder в readiness-оценку у аудитора — только по запросу
  enterprise-лида.
- [ ] Статус-страница (публичная) поверх blackbox-проб и SLO из 3.3.

## 5. Горизонт 3 — рост

- Второй регион / multi-zone — только если HA control-plane (3.1) окажется
  недостаточным по SLO.
- Cosign/provenance для образов — когда спросит клиент.
- Portable runtime (Rust-спайки в mctl-agents) — исследование, не обязательство.

## 6. Чего в плане сознательно нет

Service mesh, Velero (CNPG + Vault + etcd + Forgejo снапшоты закрывают всё
критичное), VPA, выделенные node pools, WORM-архив аудита, отдельный
прод-кластер до исчерпания HA внутри текущего. Причина прежняя: расход времени
одного оператора, который не открывает регистрацию и не защищает от
невосстановимых потерь.

## 7. Что осталось от старого плана невыполненным

Для честности — пункты, которые перекочевали без прогресса:
- Прод-кластер / промоушен-путь (переформулирован в 3.1).
- HPA для mctl-api (3.5).
- `GHCR_PAT`/`GH_PACKAGES_TOKEN` (2.3) — частично.
- Dependabot docs/portal (3.6).
- Платформенные SLO (3.3).
- Продуктовые пункты 2.4 старого плана (ICP, демо): ICP определился на практике
  — агентные/внутренние команды и bespoke ERP-проекты; записанного демо
  self-healing по-прежнему нет.
