# PLAN-TEMPORAL-ADAPTATION.md

> **Статус:** памятка к Academy-плану.
> **Дата:** 2026-08-06.
> **Автор анализа:** Claude.

Academy-план (`mctlhq/mctl-academy/PLAN.md`) писался в допущении, что агентный
пайплайн (`issue-poller → investigator → implementer → shepherd`) полностью живёт
в **Argo CronWorkflows**. Это было так на момент написания, но с релизом
**mctl-agents 1.23.0** (август 2026) архитектура изменилась: оркестрация переехала
в **Temporal**. План нигде этого не отражает — ниже что именно поменялось и какие
разделы плана надо скорректировать.

---

## 1. Что поменялось (фактический срез на 1.23.0+)

| Компонент | Было (допущение плана) | Стало (реальность 1.23.0+) |
|---|---|---|
| **Issue intake** | Argo CronWorkflow `cronworkflow-mctl-agents-issue-poll` крутит поллинг | **Temporal Schedule** → `DevLoopWorkflow` на каждый issue. Poller делает `gh search` + Temporal RPC, не запускает SDK |
| **Investigate** | Argo CWFT `mctl-agents-investigate` по крону | Тот же CWFT, но submitится из **Temporal activity** (`submit_and_wait`), не из крона |
| **Implement** | Argo CWFT `mctl-agents-implement` по крону | Тот же CWFT, submitится из **Temporal activity** |
| **Shepherd** | Argo CronWorkflow с `decide()` | CWFT submitится из Temporal; review-loop — `check_review` activity с GitHub polling |
| **Reconcile** | Argo CronWorkflow `mctl-agents-reconcile` | Пока висит (Phase 5 не закрыта) — запланирована как Temporal Schedule для orphan `.status.yaml` |
| **Drift detection** | GitHub Actions `source-drift.yml` | Без изменений — по-прежнему GHA |
| **Service-agent / mentor rotation** | Argo CronWorkflow `mctl-agents-daily` | Без изменений (Temporal пока только для dev-loop) |

**Ключевое следствие:** задержка intake определяется не Argo-кроном, а
**Temporal Schedule**. Для Academy это значит: после открытия drift-issue с label
`agents:intake` → Temporal подхватит в ближайший tick (минуты, не часы).

---

## 2. Что в плане надо скорректировать

### 2.1. Раздел 5 — «Agents and PR flow»

**Сейчас в плане:**
> Drift issue → issue-poller → issue-investigator → implementer.

**Надо добавить:**
- Issue intake триггерится **Temporal Schedule**, не Argo CronWorkflow. Это влияет на
  наблюдаемость: статус пайплайна виден в **Temporal UI**, не в Argo Workflows UI.
- Между investigate и implement есть **сигнал утверждения** (`wait_condition` в
  `DevLoopWorkflow`). В плане это не отражено — подразумевается автоматический
  переход. На практике: либо человек сигнализирует approval, либо статус в
  `.status.yaml` переключается в `accepted`. Для Academy это значит, что контентный
  PR **не откроется автоматически** после investigate — нужен явный approval.

### 2.2. Раздел 5 — «SHEPHERD_SKIP_SERVICES»

**Сейчас в плане:**
> Add mctl-academy to SHEPHERD_SKIP_SERVICES in the shepherd workflow environment.

**Надо уточнить:**
- Shepherd теперь крутится **из Temporal review-loop**, не из отдельного крона.
  `SHEPHERD_SKIP_SERVICES` читается в `orchestrator/run_shepherd.py:146` — это всё ещё
  актуально, но контекст другой: shepherd вызывается как часть `DevLoopWorkflow`, а
  не как самостоятельный CronWorkflow.

### 2.3. Раздел 4 — «Drift»

**Сейчас в плане:**
> A weekly GitHub Actions workflow in mctl-academy re-fetches approved sources […]
> and opens one agents:intake issue per drifted source.

**Надо добавить:**
- После открытия issue → intake происходит через **Temporal**, не через Argo. Это
  влияет на SLA: план подразумевает «weekly cron → immediate pickup», а реальность
  «weekly cron → Temporal Schedule tick (минуты) → DevLoopWorkflow start».
- Дедуп drift-issue («updating the existing open issue rather than opening
  duplicates») — реализуется в `run_issue_poller.py` через Temporal workflow ID
  (`dev-loop-{owner}-{repo}-{issue}`), а не через ручной поиск по title/label.

### 2.4. Раздел 10 — «Phases and gates»

**Сейчас в плане:**
> Phase 0 — foundation […] 20 reviewed questions.

**Надо добавить:**
- Phase 0 должен включать проверку, что **worker image ≥ 1.23.0** и Temporal namespace
  `mctl-agents` зарегистрирован. Без этого весь пайплайс ниже не взлетит.
- Верификация Phase 0: один тестовый drift-issue → Temporal UI показывает
  `DevLoopWorkflow` → proposal в gitops → approval signal → PR.

---

## 3. Что в плане **не меняется** (можно оставить как есть)

- Content model, evidence chain, clean-room policy — не затронуты.
- Deployment через MCP (`mctl_deploy_service`, `mctl_provision_database`) — не
  затронут.
- Схема данных, OAuth, сессии — не затронуты.
- Раздел 8 (Deployment — MCP-only) — актуален, Temporal не меняет способ деплоя.
- Раздел 1 (Positioning and legal posture) — не зависит от оркестрации.

---

## 4. Критичное ограничение по версиям

**Весь описанный здесь Temporal-path работает только при `mctl-agents ≥ 1.23.0`.**

- В gitops `services/admins/mctl-agents-worker/values.yaml` → `image.tag` должен быть
  `1.23.0` или выше.
- В gitops `infra-components/data/temporal/tenant-namespace-job.yaml` → namespace
  `mctl-agents` должен быть зарегистрирован (PostSync hook, `register_ns "mctl-agents" 30`).
- До выполнения этих двух условий план полагаться на Temporal-path **не может** —
  всё ещё будет работать по старому Argo-CronWorkflow-пути (если кроны не удалены).

---

## 5. Опционально: что стоит доделать перед запуском Academy

| # | Что | Зачем |
|---|---|---|
| 1 | Бамп worker image до 1.23.0 в gitops | Без него Temporal dispatch не крутится |
| 2 | Финализировать Phase 5 (CronWorkflows → Temporal Schedules) | Кроны `issue-poll`, `incidents`, `reconcile`, `shepherd`, `implement` всё ещё в репозитории. Пока не заменены — работают параллельно с Temporal, что создаёт двойную оркестрацию |
| 3 | Удалить/приостановить кроны, которые дублируют Temporal | Избежать двойного intake |

Пункты 1 и 2 — пререквизиты для запуска Academy на Temporal-path. Пункт 3 —
желателен, но не блокер для MVP (старый путь просто не сработает, если worker на
1.23.0 и кроны не удалены — poller диспатчит в Temporal, а кроны не найдут labelled
issues).

---

## 6. Итого

Academy-план **не ошибочен**, но описывает платформу в состоянии «до Temporal».
С 1.23.0 оркестрация dev-loop'а переехала в Temporal, и это меняет:

1. **Триггер intake** — Temporal Schedule вместо Argo Cron.
2. **Наблюдаемость** — Temporal UI вместо Argo Workflows UI.
3. **Approval flow** — явный сигнал вместо автоматического перехода.
4. **Пререквизиты** — worker ≥ 1.23.0 + namespace `mctl-agents`.

Без учёта этих четырёх пунктов план рискует описать систему, которой в кластере
больше нет.
