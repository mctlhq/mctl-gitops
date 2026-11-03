# Managed-runtime preview: agent-worker-managed-preview, MANAGED_RUNTIME flags and the mctl-telegram AI Gateway

## Context

mctlhq/mctl-telegram#1088 (managed runtime epic, ADR 0008 section 6) adds a
`managed` runtime. In it, a platform-operated pool worker runs an account's
communication-agent jobs on an OpenAI-compatible model reached through a
Cloudflare AI Gateway. The account no longer needs its own worker and Claude
credential. The server side has merged in mctl-telegram: the runtime field
(#1089, PR #1098), the claim-only pool credential and `POST /api/agent/pool-token`
(#1090, PR #1105), and the managed usage ledger and budget caps (#1092,
PR #1113). This issue is the mctl-gitops half: deploy the pool worker on preview,
turn on the flags and caps in `mctl-telegram-preview`, create a dedicated
`mctl-telegram` AI Gateway and its run token, and add scraping and alerting for
the new component.

The rollout is staged. Values land with `replicaCount: 0`. The gateway and token
are applied next, then secrets are written to Vault. After that the worker is
scaled to 1, the owner switches one preview account to `managed`, and a soak of
at least 30 jobs runs. Production is out of scope until mctl-telegram#889 and
#334 land. Each step must be reversible without touching the own-runtime worker
(`agent-worker-preview`) or production `mctl-telegram`.

## User stories

- AS the platform operator I WANT a separate managed pool worker on preview,
  deployed at 0 replicas first, SO THAT I can provision its secrets and gateway
  before anything runs.
- AS the platform operator I WANT the preview server to have managed runtime
  enabled with tight caps (1 account, $1.00 per account per day, $5.00 global
  per day) SO THAT the soak cannot overspend.
- AS a security reviewer I WANT the managed worker's model traffic to go through
  its own AI Gateway, with logs off, auth on and BYOK only, SO THAT no prompts
  are stored at Cloudflare, a leaked URL spends nothing, and its spend is
  separate from mctl-support's.
- AS the on-call operator I WANT alerts for a global budget cap hit, high hourly
  spend, and a pool worker that is down while managed accounts exist SO THAT a
  stuck or runaway managed runtime is visible.

## Acceptance criteria (EARS)

Worker component
- WHEN the change is merged THE SYSTEM SHALL contain
  `platform-gitops/services/labs/agent-worker-managed-preview/values.yaml` and
  `catalog-info.yaml`, which ArgoCD reconciles as Application
  `labs-agent-worker-managed-preview` in namespace `labs` with `replicaCount: 0`.
- THE SYSTEM SHALL run the worker from image
  `ghcr.io/mctlhq/agent-worker-preview`, with the same tag as
  `agent-worker-preview`, and SHALL list the new values file in
  `.github/deploy-signal.yaml` as `tracks_main: true`.
- THE SYSTEM SHALL set this worker env: `AGENT_RUNNER=openai`,
  `AGENT_POOL_MODE=true`, `AGENT_MODEL=<C1 gate model>`,
  `AGENT_OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/<account>/mctl-telegram/custom-hetzner/v1`,
  `AGENT_MAX_BUDGET_USD=0.25`, `AGENT_MAX_TURNS=12`,
  `AGENT_OPENAI_MIN_INTERVAL=6s`, `AGENT_WORKER_CONCURRENCY=1`,
  `MODEL_INPUT_USD_PER_MTOK` and `MODEL_OUTPUT_USD_PER_MTOK` at the Nebius
  (shadow) rates, and
  `AGENT_CREDENTIAL_DOMAIN_ID=platform/labs/agent-worker-managed-preview/openai`.
  It SHALL NOT set `AGENT_SYSTEM_PROMPT`.
- THE SYSTEM SHALL source the worker's secrets from three ExternalSecrets
  (`store: vault-backend`, `storeKind: ClusterSecretStore`). They read
  `secret/data/platform/labs/agent-worker-managed-preview/api` (the pool token
  as `AGENT_API_TOKEN`), `.../openai` (the provider key) and `.../gateway` (the
  `cf-aig-authorization` bearer), one property each, and are wired through
  `envFrom`.
- THE SYSTEM SHALL request `cpu: 50m, memory: 64Mi` and limit
  `cpu: 500m, memory: 256Mi`. It SHALL run with `readOnlyRootFilesystem: true`,
  non-root, all capabilities dropped and `automountServiceAccountToken: false`,
  with `/tmp` as the only writable mount, an `emptyDir`.
- WHILE `replicaCount` is 0 THE SYSTEM SHALL create no worker pod, so missing
  Vault paths or a pool token not yet minted cause no crash loop.

Preview server flags
- WHEN the change is merged THE SYSTEM SHALL set these in
  `platform-gitops/services/labs/mctl-telegram-preview/values.yaml`:
  `MANAGED_RUNTIME_ENABLED: "true"`, `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`,
  `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"` and
  `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"`.
- THE SYSTEM SHALL NOT add any `MANAGED_*` key to
  `platform-gitops/services/labs/mctl-telegram/values.yaml` (production).

AI Gateway and token
- WHEN `infrastructure/cloudflare/account` is applied THE SYSTEM SHALL create a
  `cloudflare_ai_gateway` with id `mctl-telegram`. It SHALL have
  `collect_logs = false`, `authentication = true`, `byok_only = true`,
  `cache_ttl = 0`, rate limiting off (interval 0, limit 0), and the same pinned
  server-side defaults as `cloudflare_ai_gateway.mctl_support`.
- WHEN `infrastructure/cloudflare/tokens` is applied THE SYSTEM SHALL create a
  run-only token (`local.pg.ai_gateway_run`) named
  `mctl-telegram-ai-gateway-run (Vault platform/mctl-telegram/ai-gateway)`.
- THE SYSTEM SHALL NOT change `ai-gateway-custom-providers.json`. The
  `custom-hetzner` and `custom-nebius` providers are already declared
  account-wide.

Observability
- THE SYSTEM SHALL scrape `labs-agent-worker-managed-preview` on `port: http`,
  path `/metrics`, keeping only `mctl_agent_.*` series, by the same rules as
  `mctl-telegram-agent-preview-monitor.yaml`.
- IF `mctl_agent_budget_exhausted_total` increases for the global scope THEN THE
  SYSTEM SHALL fire a warning alert (managed global cap hit).
- IF the managed spend over the last hour (`mctl_agent_usage_cost_usd_total` for
  runner `openai`) exceeds the hourly threshold THEN THE SYSTEM SHALL fire a
  warning alert.
- IF `mctl_agent_managed_accounts > 0` WHILE no
  `labs-agent-worker-managed-preview` scrape target is up for 10 minutes THEN
  THE SYSTEM SHALL fire a warning alert (pool worker down). This includes the
  case of 0 replicas.
- THE SYSTEM SHALL cover each new alert with promtool unit tests in
  `vm-rules/tests/mctl-telegram-ops_test.yaml`, and
  `scripts/check-vm-rules.sh` SHALL pass.

## Out of scope

- The data-plane steps of the rollout order. These are operator actions
  recorded in tasks.md, not in git: `tofu apply`, writing Vault secrets, minting
  the pool token on tg-preview, scaling to 1, switching the account to managed,
  and the soak.
- Production (`services/labs/mctl-telegram`, a production pool worker,
  `custom-nebius` and the release image). These wait for mctl-telegram#889 and
  #334.
- The mctl-telegram `preview-deploy.yml` change that also bumps the new
  values file's `image.tag`. That lives in mctlhq/mctl-telegram and is a
  prerequisite for keeping the tag current.
- Any change to the own-runtime `agent-worker-preview` deployment.
- New custom providers or changes to the `mctl-support` gateway.

## Open questions

- `AGENT_MODEL`: the issue says "from the C1 gate". The gating spike
  (mctlhq/.github#293, proposal still `proposed` in this clone) has no recorded
  result. Candidates in that spike are Hetzner Qwen3.8-27B and Qwen3.6-35B-A3B
  via `custom-hetzner`. The exact model id and the matching Nebius
  input/output USD-per-MTok prices must come from the gate report. The
  implementer uses the gate's id. If there is no report, it must not invent one;
  it leaves a TODO and keeps `replicaCount: 0`.
- The env-var names under which the OpenAI runner reads the provider key and
  the gateway bearer are not visible in this repo (mctl-telegram
  `cmd/agent-worker/main.go`). The ExternalSecret `secretKey`s must match them.
- The issue puts the run token in Vault `secret/platform/mctl-telegram/ai-gateway`
  (manifest) but has the worker read
  `secret/platform/labs/agent-worker-managed-preview/gateway`. This proposal
  keeps both as written: the manifest names the canonical home and the operator
  copies the value to the worker path. The alternative is to point the worker's
  gateway ExternalSecret straight at `platform/mctl-telegram/ai-gateway` and
  keep a single copy.
- The `scope` label value of `mctl_agent_budget_exhausted_total` for the global
  window (for example `global` or `global_day`) is not confirmed. The rule uses
  `scope=~"global.*"` until the live series is checked.
- The hourly spend threshold is not given in the issue. This proposal uses
  $1.00/h (20 % of the $5.00 global daily cap).
- `MANAGED_MAX_JOB_COST_USD` (per-job reservation, default 0.50 per #1092) is
  higher than the worker's `AGENT_MAX_BUDGET_USD=0.25`. This is left at the
  default, which reserves conservatively. Whether to align it to 0.25 is the
  owner's call.
- Whether preview image `main-a787e97` already contains #1098, #1105 and #1113 is
  not verified. Older images ignore the `MANAGED_*` keys, so this is harmless,
  but the pool token cannot be minted until it does.
