# Spike 2659: PostgreSQL connection pooling and memory on shared-pg

STATUS: SOURCE_ONLY_STAGE_1 (no experiment run; every result below is NOT_RUN)

Source-only first stage of mctlhq/mctl-gitops#2659, written 2026-11-16 against
`origin/main` at `9721e42a0`. Nothing here changes runtime, configuration or any
database. No cluster, database, billing or tenant system was read. No package was
installed and nothing was fetched from the network.

Vocabulary: "declared" means written in this repository. "Live" means what the
cluster runs now. Git can drift from live (ArgoCD `ignoreDifferences`, manual
changes), and this stage did not read live state, so every live fact is
NOT_OBSERVED. "Claimed in a comment" means a source comment asserts a measured
number; this stage could not verify it.

## 0. Inputs and scope

- The article behind the issue was not supplied. Its findings are NOT_OBSERVED,
  and none are assumed or paraphrased here.
- Preflight (from the orchestrator, not re-run here): issue open, unassigned,
  label `spike:scout` only, no comments; 39 open PRs checked, none mention
  #2659, pooler or pgbouncer. DevLoop "not found" is negative evidence only.
- Re-checked locally: no remote or local branch naming 2659, and no 2659 report
  in `docs/spikes/` (the existing reports are 2262, 2286 and 2506). This is
  bounded negative evidence from local refs and files only. It is not proof that
  #2659 is not already owned elsewhere (other clones, unpushed work, other
  trackers were not checked).

## 1. Declared inventory

| Item | Declared value | Source |
|---|---|---|
| Cluster | CNPG `Cluster` `shared-pg`, ns `platform-db`, 2 instances (primary + hot standby), `maxSyncReplicas: 0` | `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml` |
| PostgreSQL | image `ghcr.io/cloudnative-pg/postgresql:17.11@sha256:70664ebc...` (Debian bullseye "system" image, pinned for glibc/collation stability) | `cluster.yaml` `imageName` |
| CNPG operator | Helm chart `cloudnative-pg` `0.29.1` (the file's comment says this is operator 1.30.1), ns `cnpg-system` | `platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml` |
| Pooler | **none declared in this repository.** There is no `kind: Pooler` and no PgBouncer/pgpool reference outside history and agent proposal text. This states declared configuration only. Whether a pooler or pool exists in the live cluster is NOT_OBSERVED | repo-wide search; see section 2 |
| PgBouncer version | no declared version. The deployed version, and any live presence or absence of PgBouncer, is NOT_OBSERVED. A future Pooler would use whatever image the operator defaults to, also NOT_OBSERVED | n/a |
| `max_connections` | `"200"` | `cluster.yaml` `postgresql.parameters` |
| `shared_buffers` | `"256MB"` | same |
| `work_mem` | `"4MB"` (per sort/hash operation, per backend) | same |
| `temp_file_limit` | `"256MB"` | same |
| Timeouts | `statement_timeout 60s`, `lock_timeout 10s`, `idle_in_transaction_session_timeout 300s` | same |
| Pod memory | request = limit = `2Gi`; CPU request `500m`, limit `2` | `cluster.yaml` `resources` |
| Per-role caps | `managed.roles[].connectionLimit`: backstage 100, temporal 140, mctl-api 64, forgejo 30, zitadel 25, argoworkflows 20, mctl-agent 20, glovo_runtime 36, mctl_api_workitems 36, glovo_migrator 2, most tenant roles 10, academy_readonly 5. The zitadel comment states these already sum past `max_connections` | `cluster.yaml` `managed.roles` |
| Connection path | clients use `shared-pg-rw.platform-db.svc.cluster.local:5432` directly | `wft-provision-database.yaml` (Vault `host`/`port`), `temporal.yaml`, `monitoring.yaml`, `base-service/templates/job-db-init.yaml` |
| Client-side pools (declared) | temporal `maxConns` 20 / `maxIdleConns` 5 (default DB), 10 / 5 (visibility), `maxConnLifetime 1h`; Grafana `max_open_conn 4`, `max_idle_conn 2`; ZITADEL `MaxOpenConns 15`; Grafana academy datasource `maxOpenConns 3`; mctl-api `DB_POOL_MAX_CONNS` default 8 per database URL per pod (value lives in the mctl-api repo, referenced from comments here); Backstage knex pool max 3 per plugin schema (comment) | `temporal.yaml`, `monitoring.yaml`, `zitadel.yaml`, `academy-postgres-datasource.yaml`, `cluster.yaml` comments. Values for other repositories (mctl-api pool default, Backstage knex) are comment evidence only; the implementation was not read and is not verified |

The pooler-related history is the most relevant finding of this stage:

- A `Pooler` `shared-pg-pooler-rw` (2 instances, PgBouncer `poolMode: transaction`,
  `max_client_conn 400`, `default_pool_size 20`, `max_db_connections 30`) existed
  and was **removed** by commit `c26d9ac0f` (2026-10-20,
  "trim idle connection budget, drop unused pooler"). That commit message states
  that no Secret, Deployment, StatefulSet, CronJob or ConfigMap pointed at it and
  that no backend connection came from its pods. These are claims in a commit
  message; this stage did not re-verify them.
- The same commit message claims 8 days of VictoriaMetrics data (2026-10-12..20)
  showed a peak of 130 connections against `max_connections 200` and never more
  than 15 active backends, and chose to trim client pools (temporal idle 20/10 -> 5/5)
  rather than pool at the server. NOT_OBSERVED here. It is a claim from a
  prior investigation, not a measurement from this stage.
- `platform-gitops/agents-state/mctl-gitops/proposals/issue-1774-*` still
  describes the pooler as present (and cites chart 0.23.0). That is agent
  proposal state frozen in time, not current config. Do not read it as live.

## 2. Tenant provisioning paths (how clients reach the database)

1. `ClusterWorkflowTemplate` `provision-database`
   (`platform-gitops/argo-workflows/cluster-templates/wft-provision-database.yaml`)
   writes `host = shared-pg-rw.platform-db.svc.cluster.local`, `port = 5432` to
   Vault, then patches `cluster.yaml` (pg_hba entry, a managed role with a
   hard-coded `connectionLimit: 10`), `databases.yaml` and `secrets.yaml`, and
   pushes to `main`. A pooler would need a new host/port here, or a second Vault
   key, and the awk anchors (`# Team app roles`,
   `host all all 0.0.0.0/0 reject`) would need to keep working.
2. The `ExternalSecret` template emits `DATABASE_URL`, `DB_HOST`, `DB_PORT` and
   related keys. Every tenant gets the direct-primary endpoint by default.
3. `base-service/templates/job-db-init.yaml` hard-codes the direct endpoint for
   its own init Job (`postgres:17-alpine` psql client).
4. Platform clients (temporal, Grafana, ZITADEL, Backstage, mctl-api, Forgejo)
   configure their own host in their own Applications or services. There is no
   single switch point. A rollout would be per-client.
5. pg_hba is per database/role, with `host all all 0.0.0.0/0 reject` last. The
   named database/role entries in `cluster.yaml` already use address `all`, so a
   pooler does not by itself imply widening or changing them. Whether any
   pg_hba, authentication or user-mapping change is needed depends on the
   chosen design (for example how the pooler authenticates to the server and
   maps client users to roles) and must be reassessed against that design, with
   tenant isolation retained. The deleted `networkpolicy.yaml` change in
   `c26d9ac0f` shows the policy once referenced the pooler, so NetworkPolicy
   is a place to reassess too, not a presumed change. No settings change is
   authorized by this report.

## 3. Canonical config owner and observability (source only, not queried)

- Config owner: `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`,
  synced by `platform-gitops/bootstrap/templates/data/shared-pg.yaml`
  (automated, prune, selfHeal). `.github/CODEOWNERS` default owner is
  `@MashkovD`. No more specific data-path owner appears in CODEOWNERS.
  Owner confirmation is an owner choice (section 8).
- Runbook: `docs/runbooks/shared-pg.md` (SharedPgConnectionsHigh and
  SharedPgRoleConnectionsHigh describe the connection budget and say to restart
  the offending client, not the database).
- Alerts: `platform-gitops/infra-components/observability/vm-rules/shared-pg-alerts.yaml`
  (`SharedPgConnectionsHigh` at 80% of `max_connections`, hard-coded "200" in the
  description; `SharedPgRoleConnectionsHigh` mirrors `connectionLimit` for
  mctl-api, temporal, backstage, labs-mctl-alice, labs-mctl-telegram only, so
  other roles have no per-role alert). Tests in `vm-rules/tests/shared-pg-alerts_test.yaml`.
- Dashboard: `platform-gitops/infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`
  has pod `container_memory_working_set_bytes` against requests, and
  `cnpg_backends_total` against `max_connections`. It has no per-backend
  memory (RSS/PSS) panel.
- Scrape: `infra-components/data/cnpg/shared/vmpodscrape.yaml`.
- Not exported or not available in source: `rolconnlimit` (the alert file says
  so), `pg_stat_activity` state split (active vs idle vs idle-in-transaction) as
  an alert input, per-backend memory, `work_mem` spill counts.
  Whether the default CNPG exporter queries cover these is NOT_OBSERVED.

## 4. What the source does and does not establish

Distinct quantities that must not be conflated:

| Quantity | What source says | Unknown |
|---|---|---|
| `max_connections` | 200 declared. An upper bound on backend slots, not a memory figure | live value (could differ if edited out of band) |
| Per-backend fixed memory | not declared anywhere (it is a PostgreSQL/OS property: catalog caches, relcache, plan caches, per-process overhead, which grow with the workload and schema) | any measured distribution on this cluster, for idle or active backends |
| `work_mem` | 4MB, allocated per sort/hash node per backend and per query, not per connection. One query can use several | actual spill/usage; plan shapes |
| Active concurrency | commit message claims a peak of 15 active backends over 2026-10-12..20 (NOT_OBSERVED here) | current peak, burst shape, tail beyond the 8-day window, what changes under mctl-api rolling updates |
| Total connections | same claim: peak 130 of 200 | same |
| Pool mode | no pool is declared in git. Live presence is NOT_OBSERVED. A deleted Pooler used `transaction` | live pools; which clients tolerate transaction pooling |
| Pod memory | `2Gi` limit. A comment says shared-pg-1 was OOMKilled 11 times at the former `1Gi` limit on 2026-06-30 and attributes it to `shared_buffers` + `max_connections` x `work_mem` + WAL/checkpoint buffers "under load" | the real composition of the pre-raise working set; whether OOM kills have recurred at `2Gi` |

I do **not** multiply `max_connections` by any per-backend figure, or by
`work_mem`, to state a memory usage. Such a product is an upper-bound
construction, and for `work_mem` it is not even a realistic bound (a backend
may use none, one, or several allocations). No measured memory claim is made.

The source does establish: a 2Gi cap that was previously OOMKilled at 1Gi (a
comment claim), a 200-slot ceiling, per-role limits that oversubscribe it by
design, idle-pool pressure addressed once at the client (temporal), and a pooler
that was deliberately removed because nothing used it.

The source does **not** establish: that backend memory is currently a problem,
that any OOM has occurred since the 2Gi raise, that idle connections are the
dominant memory consumer, or that a pooler would help. The only evidence of
memory pressure is a pre-raise OOM comment and a mitigation already applied.

**Is there a real gap in source? Not shown.** What is shown is an unquantified
risk: no declared per-backend memory view, no current-peak concurrency data in
git, and no alert that distinguishes idle from active backends. Whether this
matters is a live-state question this stage cannot answer.

## 5. Transaction/session compatibility (source-visible signals)

Transaction-mode pooling reuses a server connection across clients between
transactions, so any feature that relies on session state is a compatibility
question. Statements about generic PgBouncer behaviour below come from general
knowledge, not from a source read here. They must be checked against the
PgBouncer version actually pinned for any future test (NOT_OBSERVED).

Signals in this repo:

- Session-level or transaction-held advisory locks: mctl-support migrates "advisory-locked"
  on start (`services/admins/mctl-support/values.yaml`); the Glovo schema
  migrations take advisory locks inside one transaction each
  (`docs/runbooks/glovo-basket-canary.md`). Transaction-scoped locks are
  compatible in principle, session-scoped locks are not. Which kind each uses is
  NOT_OBSERVED (the code is in other repositories).
- Prepared statements and driver behaviour per client. Any client-pool default
  or driver behaviour for other repositories that appears in a source comment
  here is comment evidence, not verified implementation, and supports no
  blanket compatibility claim. A future test must pin and test the exact
  candidate PgBouncer, driver and client versions. No external fetch is needed
  for that statement. (Go `database/sql` with
  pgx or lib/pq, knex/pg for Backstage, Python asyncpg for kuptsi-app; the
  drivers used by Forgejo, ZITADEL and Temporal are not read here): NOT_OBSERVED. asyncpg in particular
  uses server-side prepared statements by default, so it is the first client
  to test, because `kuptsi-app` declares a `postgresql+asyncpg://` URL (comment in
  `wft-provision-database.yaml`).
- `LISTEN/NOTIFY`, `SET` (non-local), temp tables, cursors `WITH HOLD`: not
  searchable from this repo for third-party clients; NOT_OBSERVED.
- `ssl_mode require` is used by Grafana; pooler TLS to client and to server
  would be a separate setting. NOT_OBSERVED.
- Role/pg_hba: connection limits are per role on the server. Existing per-role
  `connectionLimit` values would still constrain backend connections behind a
  pooler. Whether the per-role alerts and limits need evaluation depends on the
  chosen design (for example per-role pools versus shared pools); that is an
  evaluation item, not automatic rework. Authentication, user mapping and
  tenant isolation must be reassessed against the actual design.

## 6. Options

### Option A: reuse existing configuration (no pooler)

Keep direct connections. Use the existing levers already established in git:
client pool sizing (as in temporal, Grafana, mctl-api), per-role
`connectionLimit`, `idle_in_transaction_session_timeout`. If the source gap above
is to be closed, add observability only (per-state backend counts, per-role
alerts for the remaining roles, a memory-versus-backends view) through the
existing alert and dashboard files.

- For: no new component, no tenant impact, matches the 2026-10-20 decision.
- Against: leaves idle-backend memory as an unmeasured risk and leaves
  clients to size their own pools, which has failed before
  (`too many connections for role` for mctl-api 2026-09-24 and Grafana
  2026-10-04, per comments).

### Option B: bounded future offline synthetic experiment (stage 2, not run)

A throwaway PostgreSQL and optional PgBouncer on an isolated workstation or CI
runner, with a synthetic workload only. Purpose: obtain **ratios and
compatibility answers** (per-backend memory slope, effect of transaction
pooling on a fixed synthetic client set), not predictions of production
memory. It needs separate operator authorization because it installs packages or images and
pulls from the network, which this stage was forbidden to do. See section 7.

- For: answers compatibility and slope questions with no production access.
- Against: synthetic data does not reproduce real schemas, plan cache or
  relcache sizes, so absolute numbers do not transfer. Cost is real engineering time.

### Option C: DEFER

Record that the source shows no established gap and close #2659 as a
research note. Reopen if live evidence (an OOM, a SharedPgConnectionsHigh page,
or a measured idle/active split) shows a gap.

- For: honest to the evidence; avoids rebuilding what was removed because it was unused.
- Against: the missing live peak data stays missing.

### Recommendation (owner decides)

Option C now, with a small Option A observability follow-up proposed only if
the owner wants the unknown closed cheaply. Option B only if live data (read by
an authorized operator in a later stage) shows memory pressure attributable to
backends. Nothing in source justifies re-adding a pooler.

## 7. Proposed offline synthetic experiment design (every result NOT_RUN)

Proposed, not executed. Requires explicit authorization for package/image
installs and any egress before anyone runs it.

**Conditions held fixed:**

- PostgreSQL 17.11 with the same parameters as `cluster.yaml`:
  `max_connections 200`, `shared_buffers 256MB`, `work_mem 4MB`,
  `temp_file_limit 256MB`, same three timeouts. Record the exact image digest
  and kernel/OS. The Debian bullseye vs other base differs in libc and
  allocator, so state it.
- Container memory limit 2Gi equal to production, cgroup v2, no swap.
- If PgBouncer is included: pin the version, the same `poolMode` under test, and
  the same `default_pool_size`, `max_client_conn`, `max_db_connections`
  as the removed config, recorded verbatim. Treat those as a starting
  point only, not recommended values.
- Schema: synthetic, with table/index/partition counts chosen in advance and stated.
  Include one variant sized like the largest tenant schema only if its size is
  known from an authorized source (otherwise NOT_OBSERVED).

**Workload mixes (fixed seeds, fixed duration, warm-up discarded):**

| Run | Clients | Mix | Pool | Result |
|---|---|---|---|---|
| R1 baseline idle | N requested client connections, N stepped (say 10/50/130/200, chosen in advance). Record how many were admitted and how many refused, with error text | connect, one trivial query, hold idle | direct | NOT_RUN |
| R1p paired idle via pooler | same requested client count and mix as R1; record observed backend count separately from client count | same | transaction | NOT_RUN |
| R2 active/idle mix | same N, with a fixed active fraction (say 15 of 130, mirroring the claimed profile, labelled as a claim) | short OLTP transactions | direct | NOT_RUN |
| R3 same load via pooler | same as R2 | same | transaction | NOT_RUN |
| R4 session-state probes | small client set | session `SET`, session advisory lock, named prepared statements, `LISTEN`, temp table, `WITH HOLD` cursor | direct vs transaction | NOT_RUN |
| R5 `work_mem` pressure | few clients | sort/hash-heavy query, with and without spill | direct | NOT_RUN |
| R6 failure/latency | R3 plus: kill a backend, restart the pooler, restart postgres, inject added network latency | | transaction | NOT_RUN |

**Admission caveat:** `max_connections 200` does not guarantee 200 ordinary
connections are available. Reserved slots (superuser/reserved connections),
background and replication roles and version-specific configuration consume
slots. Treat N as requested client connections, record admissions and
refusals, and do not assume N were served.

**Idle-memory comparison rule:** if idle memory benefits are discussed, use the
paired R1/R1p runs with the same logical client count and mix, and report
observed backend counts for each separately. Measure total memory (PostgreSQL
plus pooler, all processes) in both arms. Memory saved on the server side is
not a total gain until pooler memory is included. No benchmark was executed,
and none of this is a production sizing recommendation.

**Measurements:**

- Memory: per-backend RSS **and PSS** (shared pages counted once; RSS alone
  double counts `shared_buffers`), plus container cgroup `memory.current`. State
  which was used. Sample at fixed intervals and report the distribution
  (p50/p95/max), not a mean.
- Latency: client-observed p50/p95/p99 per transaction, with connect time reported separately.
- Server: `pg_stat_activity` state counts, `pg_stat_database`, temp-file counts.
- Pooler: its own memory, client/server connection counts, wait times.
- Failure controls: error rate, recovery time, whether clients reconnect.
- Compatibility: per probe in R4, a pass/fail with the exact error text.

**Method rules:** repeat each run at least 3 times and report spread; change one
variable per run; archive the raw samples; do not extrapolate a measured slope
to production memory. A result is valid only for the stated synthetic schema,
versions and limits.

**Proposed tuning checklist (not recommended production values, nothing applied):**

1. Capture the live idle/active/idle-in-transaction split and the peak over a
   long window (operator-authorized read, later stage).
2. Capture per-backend memory distribution from the live primary (same).
3. Decide whether per-role `connectionLimit` or client pools, not a pooler, already
   bound the risk.
4. If a pooler is ever reconsidered: choose the pool mode per client from R4
   outcomes, pin the PgBouncer version, size the pool from measured **active**
   concurrency, not from `max_connections`, and plan the Vault `host`/`port`
   changes, then reassess pg_hba/authentication, user mapping, NetworkPolicy,
   tenant isolation and the existing per-role limits and alerts against the
   chosen design (section 2). None of these is presumed to need a change.

## 8. Unknowns (all NOT_OBSERVED in this stage)

- Live PostgreSQL parameters, version and pod memory/OOM history on shared-pg.
- Current and historical peak total connections, active backends, idle backends
  and idle-in-transaction counts; per-backend memory distribution.
- Whether the 2026-10-20 commit's numbers (130 peak, 15 active) are accurate
  or have changed.
- Which clients use server-side prepared statements, session advisory locks,
  `LISTEN/NOTIFY`, session `SET`, temp tables.
- The article's content and claims.
- The PgBouncer version a current CNPG operator would default to.
- Whether the live Cluster matches git (the Application ignores Cluster
  annotations, labels and status only; `restartedAt` is reconciled).
- Cloudflare/billing/tenant cost data (out of scope).

## 9. Owner choices

1. Choose A, B or C (section 6). This report recommends C, with optional
   observability-only A.
2. Confirm the config owner for `cluster.yaml` (CODEOWNERS default `@MashkovD`).
3. If B: authorize the offline environment, package or image installs and egress
   as a separate, explicitly scoped stage.
4. If live evidence is wanted: authorize an operator read-only stage that
   names the queries and the retention window, run by a person with cluster access.
5. Decide whether `agents-state` proposal 1774, which still describes a pooler
   that no longer exists, should be annotated as stale (not touched here).

## 10. Sources read (all in this repository at `9721e42a0`)

- `AGENTS.md`, `CLAUDE.md`
- `platform-gitops/infra-components/data/cnpg/shared/cluster.yaml`
- `platform-gitops/bootstrap/templates/data/shared-pg.yaml`
- `platform-gitops/bootstrap/templates/data/cloudnative-pg.yaml`
- `platform-gitops/bootstrap/templates/data/temporal.yaml`
- `platform-gitops/bootstrap/templates/observability/monitoring.yaml`
- `platform-gitops/argo-workflows/cluster-templates/wft-provision-database.yaml`
- `platform-gitops/helm-charts/base-service/templates/job-db-init.yaml`
- `platform-gitops/infra-components/observability/vm-rules/shared-pg-alerts.yaml`
- `platform-gitops/infra-components/observability/grafana-dashboards/cnpg-dashboard-configmap.yaml`
- `docs/runbooks/shared-pg.md`, `docs/runbooks/glovo-basket-canary.md`
- `platform-gitops/services/admins/mctl-support/values.yaml`
- `platform-gitops/agents-state/mctl-gitops/proposals/issue-1774-*/` (historical)
- Git history: commit `c26d9ac0f` (pooler removal), `git log -S` on `shared-pg-pooler`
- `.github/CODEOWNERS`
