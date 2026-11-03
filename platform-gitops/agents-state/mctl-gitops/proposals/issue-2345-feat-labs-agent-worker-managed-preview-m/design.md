# Design: issue-2345-feat-labs-agent-worker-managed-preview-m

## Current state

- `platform-gitops/services/labs/agent-worker-preview/values.yaml` is the
  own-runtime worker. It runs at `replicaCount: 0` since 2026-10-29 because the
  worker moved off-cluster. Image is `ghcr.io/mctlhq/agent-worker-preview`, tag
  `main-a787e97`, bumped by mctl-telegram `preview-deploy.yml`. It has
  `ingress.enabled: false`, probes on `port: http` (`/healthz`, `/readyz`),
  `readOnlyRootFilesystem: true`, `automountServiceAccountToken: false`, and
  emptyDirs for `/home/node` (Claude CLI HOME) and `/tmp`. Env:
  `AGENT_API_BASE_URL=http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1`
  (it must be the full `/api/agent/v1` root), `AGENT_MAX_BUDGET_USD`,
  `AGENT_WORKER_CONCURRENCY` and `AGENT_CREDENTIAL_DOMAIN_ID` (read through
  `requireEnv`, so it is fail-fast if unset), plus a long `AGENT_SYSTEM_PROMPT`.
  One ExternalSecret `labs-agent-worker-preview-api` reads
  `secret/data/platform/labs/agent-worker-preview/api` through
  `vault-backend`/`ClusterSecretStore`. There is no `AGENT_RUNNER` (it defaults
  to `claude`) and no `AGENT_POOL_MODE`. The `catalog-info.yaml` is a Backstage
  `Component` of type `worker`, with `github.com/source-repo: mctlhq/mctl-telegram`
  and `mctl.me/auto-deploy: "false"`.
- `platform-gitops/services/labs/mctl-telegram-preview/values.yaml` sets
  `AGENT_ENABLED: "true"`, `AGENT_KILL_SWITCH: "false"`,
  `AGENT_TURN_QUIET`/`AGENT_TURN_MAX_WAIT`, `AGENT_UNCLAIMED_ROUTE_AFTER: "5m"`
  and `EVENTS_OPERATOR_ROUTING: "true"`. It has no `MANAGED_*` key.
- `infrastructure/cloudflare/account/ai-gateway.tf` declares one gateway,
  `cloudflare_ai_gateway.mctl_support` (id `mctl-support`). Its settings are
  `collect_logs=false`, `authentication=true`, `byok_only=true`, `cache_ttl=0`,
  rate limiting off, and pinned server-side defaults (`log_classification`,
  `log_management`, `log_management_strategy`, `logpush`, `zdr`) that work
  around provider bug 7336. It also has the output
  `mctl_support_ai_gateway_url`. `ai-gateway-custom-providers.json` declares the
  `nebius` and `hetzner` custom providers for the whole account. The README
  documents the route `<gateway url>/custom-hetzner/v1`.
- `infrastructure/cloudflare/tokens/manifest.tf` already has
  `local.pg.ai_gateway_run` and one run token, `mctl-support-ai-gateway-run
  (Vault platform/mctl-support/ai-gateway)`, under "Other". Its resources are
  the whole account (`(local.account) = "*"`).
- `platform-gitops/services/admins/mctl-support/values.yaml` is the reference
  for consuming the gateway. It sets
  `NEBIUS_BASE_URL=https://gateway.ai.cloudflare.com/v1/6a09f637d20e1f66a8e9d45ebe778058/mctl-support/custom-nebius/v1`
  and Nebius prices `MODEL_INPUT_USD_PER_MTOK: "1.40"` /
  `MODEL_OUTPUT_USD_PER_MTOK: "4.40"` (GLM-5.1), and has the bearer
  `MODEL_GATEWAY_TOKEN` from `secret/data/platform/mctl-support/ai-gateway`
  property `token`.
- `platform-gitops/bootstrap/templates/mctl-platform/mctl-telegram-agent-preview-monitor.yaml`
  is a `VMServiceScrape` selecting `app.kubernetes.io/instance In
  [labs-mctl-telegram-preview, labs-agent-worker-preview]` in `labs`. It scrapes
  `port: http` and `/metrics`, and its `metricRelabelConfigs` keep only
  `mctl_agent_.*`, so preview series do not trip production SLO alerts.
- `platform-gitops/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`
  group `mctl-telegram-agent` holds `MctlAgentDeadLetter`,
  `MctlAgentJobCostHigh` and the other agent rules. The file header requires
  every metric to be checked against live VictoriaMetrics series. Tests are in
  `vm-rules/tests/mctl-telegram-ops_test.yaml`, run by promtool and
  `scripts/check-vm-rules.sh` in `.github/workflows/validate-manifests.yml`.
- `.github/deploy-signal.yaml` requires every `services/**/values.yaml` with an
  image tag to be listed exactly once. `agent-worker-preview` is listed as
  `tracks_main: true`.
- The contracts this issue consumes, from the merged mctl-telegram proposals in
  `platform-gitops/agents-state/mctl-telegram/proposals/`:
  - #1090: a pool token with `aud=agent-pool`, minted by `POST /api/agent/pool-token`
    only while `AGENT_ENABLED` and `MANAGED_RUNTIME_ENABLED` are on. Worker
    `AGENT_POOL_MODE=true` uses per-job tokens and never falls back. Revoking
    the pool `jti` kills its job tokens.
  - #1092: `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY` (default 1.00),
    `MANAGED_BUDGET_USD_PER_ACCOUNT_MONTH` (15.00),
    `MANAGED_BUDGET_USD_GLOBAL_DAY` (20.00) and `MANAGED_MAX_JOB_COST_USD`
    (0.50). Metrics: `mctl_agent_usage_cost_usd_total{runner,model}`,
    `mctl_agent_managed_accounts`, `mctl_agent_budget_exhausted_total{scope}`
    and `mctl_agent_budget_deferred_total{scope}`. Its out-of-scope section hands
    the alert rules to this issue.
  - #1089: `MANAGED_RUNTIME_ENABLED` (default false) and
    `MANAGED_RUNTIME_MAX_ACCOUNTS` (default 1).

Deployed state checked:
- `diff` of `$MCTL_GITOPS_ROOT/services/labs/agent-worker-preview/values.yaml`
  and `.../mctl-telegram-preview/values.yaml` against the clone: identical.
- `ls $MCTL_GITOPS_ROOT/services/labs/`: no `agent-worker-managed-preview`
  exists yet.
- `grep MANAGED|AGENT_RUNNER|POOL` in `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram{,-preview}/values.yaml`:
  no matches, so managed runtime is not configured anywhere.
- `mctl_get_service_status(labs, agent-worker-preview)`: Synced/Healthy, image
  tag `main-a787e97`, componentType base-service.
- Not observed: Cloudflare account state (whether a `mctl-telegram` gateway or
  token exists), Vault paths, live VictoriaMetrics series for the new
  `mctl_agent_*` metrics, and whether `main-a787e97` contains the managed-runtime
  server code. All are recorded under Open questions in requirements.md.

## Proposed solution

One PR in mctl-gitops, with five parts. All of them are inert until an operator
acts: the worker is at 0 replicas, the Cloudflare roots need a reviewed apply,
and no account is managed.

### 1. New component `services/labs/agent-worker-managed-preview/`

`values.yaml` is cloned from `agent-worker-preview` and trimmed for the OpenAI
runner:

- `replicaCount: 0`, with a header comment describing the staged rollout and
  rollback.
- `image.repository: ghcr.io/mctlhq/agent-worker-preview`, with `image.tag` equal
  to the current `agent-worker-preview` tag. A comment says it is auto-bumped by
  mctl-telegram `preview-deploy.yml` once that workflow is extended, and must
  not be hand-pinned.
- `ingress.enabled: false`, `imagePullSecrets: ghcr-credentials`, and probes
  copied verbatim (the binary and health server are the same).
- `resources`: requests `cpu: 50m, memory: 64Mi`, limits `cpu: 500m,
  memory: 256Mi`. There is no `claude` CLI subprocess, so the 1000m/512Mi of the
  own worker is not needed. Also `ephemeral-storage` 64Mi/256Mi, matching the
  only writable volume.
- `podSecurityContext`/`containerSecurityContext` copied
  (`readOnlyRootFilesystem: true`, drop ALL, seccomp RuntimeDefault),
  `automountServiceAccountToken: false`.
- `extraVolumes`/`extraVolumeMounts`: only `agent-tmp` emptyDir (`sizeLimit:
  64Mi`) at `/tmp`. No `/home/node`, because the OpenAI runner has no CLI HOME.
- `env`:
  ```yaml
  AGENT_API_BASE_URL: "http://labs-mctl-telegram-preview-base-service:8080/api/agent/v1"
  AGENT_RUNNER: "openai"
  AGENT_POOL_MODE: "true"
  AGENT_MODEL: "<C1 gate model id>"
  AGENT_OPENAI_BASE_URL: "https://gateway.ai.cloudflare.com/v1/6a09f637d20e1f66a8e9d45ebe778058/mctl-telegram/custom-hetzner/v1"
  AGENT_MAX_BUDGET_USD: "0.25"
  AGENT_MAX_TURNS: "12"
  AGENT_OPENAI_MIN_INTERVAL: "6s"     # Hetzner: 10 req/60s per key
  AGENT_WORKER_CONCURRENCY: "1"
  MODEL_INPUT_USD_PER_MTOK: "<Nebius rate>"   # shadow price, Hetzner bills differently
  MODEL_OUTPUT_USD_PER_MTOK: "<Nebius rate>"
  AGENT_CREDENTIAL_DOMAIN_ID: "platform/labs/agent-worker-managed-preview/openai"
  ```
  There is no `AGENT_SYSTEM_PROMPT`: in the managed runtime the prompt comes
  from the account's assistant install, not from the platform deployment. The
  account id in the URL is the non-secret value already committed in
  `ai-gateway-custom-providers.json` and `mctl-support/values.yaml`.
- `envFrom` with three secretRefs, and `extraExternalSecrets` with three entries
  (`store: vault-backend`, `storeKind: ClusterSecretStore`, `refreshInterval:
  1h`, one property each). Each carries the standard "Platform-scoped path"
  comment:
  - `labs-agent-worker-managed-preview-api`: `AGENT_API_TOKEN` from
    `secret/data/platform/labs/agent-worker-managed-preview/api`, the `aud=agent-pool`
    token from `POST /api/agent/pool-token` with pool_name
    `agent-worker-managed-preview`.
  - `labs-agent-worker-managed-preview-openai`: the provider (Hetzner) key from
    `.../openai`.
  - `labs-agent-worker-managed-preview-gateway`: the `cf-aig-authorization`
    bearer from `.../gateway`.
  The `secretKey`s for the last two must equal the names the worker reads. The
  implementer confirms them in mctl-telegram `cmd/agent-worker/main.go` (see
  Open questions).

`catalog-info.yaml` is a copy of the `agent-worker-preview` one with every
`agent-worker-preview` replaced by `agent-worker-managed-preview`.

`.github/deploy-signal.yaml` gains the new path with `tracks_main: true`, next to
`agent-worker-preview`. The checker fails without it.

### 2. Preview server flags

Four keys are added to `mctl-telegram-preview/values.yaml` `env`, after the
`AGENT_UNCLAIMED_ROUTE_AFTER` block, with a comment pointing to ADR 0008 §6 and
the rollback order:

```yaml
MANAGED_RUNTIME_ENABLED: "true"
MANAGED_RUNTIME_MAX_ACCOUNTS: "1"
MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"
MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"
```

`MANAGED_RUNTIME_ENABLED` must be true in this PR, because `POST
/api/agent/pool-token` returns 404 without it (#1090). With no account switched
to `managed`, it changes no job routing.

### 3. Cloudflare

`account/ai-gateway.tf` gets `resource "cloudflare_ai_gateway" "mctl_telegram"`
with `id = "mctl-telegram"`. Every argument matches `mctl_support`
(`collect_logs=false`, `authentication=true`, `byok_only=true`, `cache_ttl=0`,
`cache_invalidate_on_update=true`, rate limiting 0/0/"fixed", and the same
pinned defaults). It also gets an `output "mctl_telegram_ai_gateway_url"`. Its
comment explains why a separate gateway is used: a spend view and token
independent of mctl-support, and the ability to delete it without touching
mctl-support.

`tokens/manifest.tf` gets a second entry under "Other":
`mctl-telegram-ai-gateway-run (Vault platform/mctl-telegram/ai-gateway)`, with
`local.pg.ai_gateway_run` on the account. No permission change is needed for
apply or plan: `ai_gateway_write`/`ai_gateway_read` are already granted to the
apply and plan tokens.

`ai-gateway-custom-providers.json` is unchanged. Per the issue and the README,
the providers are account objects, so the route `/mctl-telegram/custom-hetzner/v1`
resolves once the gateway exists. The task list verifies this with one smoke
request after apply.

### 4. Scrape

Add `labs-agent-worker-managed-preview` to the `values` list of the existing
`VMServiceScrape` `mctl-telegram-agent-preview`, and add a header paragraph for
the third workload. It is the same namespace, port, path and `mctl_agent_.*`
keep filter. A third object would only duplicate the filter.

### 5. Alerts

A new group `mctl-telegram-managed` in `vm-rules/mctl-telegram-ops.yaml`, all
`severity: warning`, `service: mctl-telegram`, with runbook anchors in the
mctl-telegram runbook:

- `MctlAgentManagedGlobalCapHit`:
  `sum(increase(mctl_agent_budget_exhausted_total{scope=~"global.*"}[15m])) > 0`,
  `for: 0m`.
- `MctlAgentManagedSpendHigh`:
  `sum(increase(mctl_agent_usage_cost_usd_total{runner="openai"}[1h])) > 1.00`,
  `for: 0m`.
- `MctlAgentManagedPoolWorkerDown`:
  ```
  max(mctl_agent_managed_accounts) > 0
  unless on()
  (sum(up{namespace="labs", service="labs-agent-worker-managed-preview-base-service"}) > 0)
  ```
  `for: 10m`. With 0 replicas there is no `up` series, so `unless` lets the left
  side through. That is intended: an account switched to managed with no worker
  means jobs are routed to the operator via `AGENT_UNCLAIMED_ROUTE_AFTER`.

The file header's metric-provenance table gets the four new series. Each is
marked "not yet live" until it is checked in VictoriaMetrics after the image
with #1092 runs on tg-preview. Unit tests in `tests/mctl-telegram-ops_test.yaml`
cover firing and non-firing cases for each rule.

## Alternatives

1. **Reuse `agent-worker-preview` and switch it to `AGENT_RUNNER=openai`
   pool mode.** Dropped. That deployment is the own-runtime rollback target
   (its header says "Set back to 1 to roll back"), and its credential domain,
   secrets and resources are Claude-CLI specific. The ADR keeps own and managed
   workers separate, so a pool token never shares a pod with an account token.
2. **Route through the existing `mctl-support` gateway.** Dropped. It mixes two
   products' spend in one analytics view and one token. Revoking or deleting
   one would break the other, and the mctl-support gateway is a spike object
   whose no-go outcome is deletion.
3. **A separate VMServiceScrape file for the new worker.** This is a valid
   reading of "as mctl-telegram-agent-preview-monitor.yaml", but it duplicates
   the selector and the `mctl_agent_.*` filter, and the filter's reasoning would
   have to be kept in sync. Extending the existing scrape is smaller. If the
   reviewer prefers a dedicated object, the change is mechanical.

## Platform impact

- **Resources**: none at merge (0 replicas). At 1 replica, 50m/64Mi requested
  in `labs`, within quota.
- **Backward compatibility**: an image without #1089/#1092 ignores `MANAGED_*`.
  With the code, enabling the flag with no managed account changes no routing.
  Own-runtime jobs are separated in SQL (#1090).
- **Cost**: per job ≤ $0.25 (worker) / $0.50 reservation (server), per account
  ≤ $1.00/day, global ≤ $5.00/day, plus BYOK provider billing only. With
  `byok_only = true`, a missing key returns 400 instead of a Cloudflare Unified
  Billing charge.
- **Privacy**: `collect_logs = false`. The soak exit criterion "gateway logs =
  0" checks it.
- **Risks**:
  - The run token is scoped to the whole account, so it can also send through
    `mctl-support`. This matches the existing token's scope, and run is
    send-only. It is recorded, not fixed here.
  - Alerts reference metrics not yet seen live. Mitigation: promtool tests and
    the "not yet live" provenance note, with a task to confirm the series.
  - The image tag is not bumped until mctl-telegram `preview-deploy.yml` knows
    the new file. Mitigation: deploy-signal `tracks_main` surfaces drift.
  - Missing secrets at scale-up cause a crash loop. Mitigation: the order in
    tasks.md (Vault before replicas 1).
