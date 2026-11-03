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
  `AGENT_POOL_MODE=true`, `AGENT_MODEL=Qwen/Qwen3.6-35B-A3B` (the dev/eval
  model the C1 gate named: mctl-telegram#1093 and mctlhq/.github#293 are
  closed with GO_HETZNER_DEV_NEBIUS_PROD, Qwen3.6-35B-A3B on Hetzner 31/32,
  0 leaks, 0 wrong auto-sends),
  `AGENT_OPENAI_BASE_URL=https://gateway.ai.cloudflare.com/v1/<account>/mctl-telegram/custom-hetzner/v1`,
  `AGENT_MAX_BUDGET_USD=0.25`, `AGENT_MAX_TURNS=12`,
  `AGENT_OPENAI_MIN_INTERVAL=6s`, `AGENT_WORKER_CONCURRENCY=1`,
  `MODEL_INPUT_USD_PER_MTOK=1.40` and `MODEL_OUTPUT_USD_PER_MTOK=4.40` (shadow
  prices: Nebius GLM-5.1, the production model, as in
  `admins/mctl-support/values.yaml`, so the preview ledger and caps behave as
  production would), and
  `AGENT_CREDENTIAL_DOMAIN_ID=platform/labs/agent-worker-managed-preview/openai`.
  It SHALL NOT set `AGENT_SYSTEM_PROMPT`.
- THE SYSTEM SHALL NOT create any ExternalSecret or `envFrom` entry for the
  worker in this change (owner amendment 2026-11-03). The Vault paths do not
  exist before activation, and an ExternalSecret that cannot sync makes the
  Application Degraded, which fires `ArgoCDApplicationDegraded` for the whole
  pre-activation window. Their exact specification is part of this proposal
  and is applied in activation step 4 (see "Activation"): three
  ExternalSecrets (`store: vault-backend`, `storeKind: ClusterSecretStore`,
  `refreshInterval: 1h`, one property each) wired through `envFrom`:
  - `labs-agent-worker-managed-preview-api`: `AGENT_API_TOKEN` from
    `secret/data/platform/labs/agent-worker-managed-preview/api` (the
    `aud=agent-pool` pool token);
  - `labs-agent-worker-managed-preview-openai`: `AGENT_OPENAI_API_KEY` from
    `.../openai` (the Hetzner key);
  - `labs-agent-worker-managed-preview-gateway`: `AGENT_GATEWAY_TOKEN` from
    `.../gateway` (the `cf-aig-authorization` bearer).
  These names are the ones `cmd/agent-worker/main.go` reads
  (`requireEnv("AGENT_API_TOKEN")`, `requireEnv("AGENT_OPENAI_API_KEY")`,
  `os.Getenv("AGENT_GATEWAY_TOKEN")`).
- THE SYSTEM SHALL request `cpu: 50m, memory: 64Mi` and limit
  `cpu: 500m, memory: 256Mi`. It SHALL run with `readOnlyRootFilesystem: true`,
  non-root, all capabilities dropped and `automountServiceAccountToken: false`,
  with `/tmp` as the only writable mount, an `emptyDir`.
- WHILE `replicaCount` is 0 THE SYSTEM SHALL create no worker pod, and the
  Application SHALL be Healthy (no ExternalSecret, nothing waiting on Vault).

Preview server flags
- WHEN the change is merged THE SYSTEM SHALL set these in
  `platform-gitops/services/labs/mctl-telegram-preview/values.yaml`:
  `MANAGED_RUNTIME_ENABLED: "false"`, `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`,
  `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"`,
  `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"` and `MANAGED_MAX_JOB_COST_USD: "0.25"`.
- WHILE `MANAGED_RUNTIME_ENABLED` is "false" THE SYSTEM SHALL keep managed
  runtime unreachable: no account can switch to `managed` and
  `POST /api/agent/pool-token` returns 404 (#1089, #1090). The flag is turned
  on only in activation step 1, after the owner's separate activation
  approval (owner amendment 2026-11-03).
- THE SYSTEM SHALL set `MANAGED_MAX_JOB_COST_USD` equal to the worker's
  `AGENT_MAX_BUDGET_USD` (0.25). With the 0.50 default, the per-job
  reservation is twice what the worker can spend, and at a 1.00 day cap one
  account is paused once its durable spend passes 0.50 (#1092: pause when
  cap - durable < per-job). At about USD 0.017 per job (C1 GLM-5.1 shadow cost)
  that is roughly 29 jobs a day; with 0.25 it is roughly 44. Both are
  estimates, not guarantees: the real count depends on the cost of the
  settled jobs and on held reservations.
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
- IF `mctl_agent_budget_exhausted_total{scope="global_day"}` increases THEN THE
  SYSTEM SHALL fire a warning alert (managed global cap hit). `global_day` is
  the exact label value (`db.BudgetScopeGlobalDay`, merged in #1113).
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

- Activation (see "Activation" below). None of its steps runs as part of this
  change, and none runs without the owner's separate activation approval:
  turning `MANAGED_RUNTIME_ENABLED` on, the Cloudflare applies, writing Vault
  secrets, minting the pool token, adding the ExternalSecrets, scaling to 1,
  switching an account to managed, and the soak.
- Production (`services/labs/mctl-telegram`, a production pool worker,
  `custom-nebius` and the release image). These wait for mctl-telegram#889 and
  #334.
- Any change to mctl-telegram CI. mctl-telegram#1094 (PR #1114, merged) already
  dispatches `agent-worker-managed-preview` on every push to main, guarded by
  an existence check of this values file on mctl-gitops main: it skips with a
  notice until this change lands, then bumps `image.tag` with no further
  change.
- Any change to the own-runtime `agent-worker-preview` deployment.
- New custom providers or changes to the `mctl-support` gateway.

## Activation (owner amendment 2026-11-03; not part of this change)

Each step starts only after the previous one is verified, and the sequence as a
whole starts only after the owner's separate activation approval. Nothing here
runs when this change merges.

1. PR: `MANAGED_RUNTIME_ENABLED: "true"` on `mctl-telegram-preview`. Verify:
   `POST /api/agent/pool-token` answers (no 404) and still no account is
   `managed`.
2. Cloudflare: `cloudflare-apply.yml` for `infrastructure/cloudflare/account`
   (one gateway create) and `infrastructure/cloudflare/tokens` (one token
   create), each plan reviewed before the apply. Verify by reading the
   gateway back: logs off, auth on, byok_only on, cache 0.
3. Mint the pool token on tg-preview (`pool_name=agent-worker-managed-preview`),
   record its `jti`, and write all three Vault secrets: `.../api` (pool token),
   `.../openai` (Hetzner key), `.../gateway` (run token; also its canonical
   copy at `secret/platform/mctl-telegram/ai-gateway`).
4. PR: add the three ExternalSecrets and `envFrom` specified above, still at
   `replicaCount: 0`. Verify: all three are `SecretSynced` and the Application
   is Healthy. This step never shares a PR with step 5.
5. PR: `replicaCount: 1`. Verify: pod Ready, scrape target up,
   `mctl_agent_credential_domain{domain_id="platform/labs/agent-worker-managed-preview/openai"}`
   present, and the T6 gateway smoke request (200 with the bearer, 401 without).
6. The owner switches one preview account to `runtime: managed` (with
   consent), then the soak of at least 30 jobs runs.

Rollback, at any step, in this order: account back to `runtime: own`, then
`replicaCount: 0`, then revoke the pool `jti`, then
`MANAGED_RUNTIME_ENABLED: "false"`.

## Resolved (owner amendment 2026-11-03)

- C1 gate: closed (mctl-telegram#1093, mctlhq/.github#293). Preview runs
  `Qwen/Qwen3.6-35B-A3B` on Hetzner through `custom-hetzner`; production will
  run GLM-5.1 on Nebius. Shadow prices are Nebius GLM-5.1, 1.40/4.40 per MTok.
- Worker env names: `AGENT_OPENAI_API_KEY` and `AGENT_GATEWAY_TOKEN`, read in
  mctl-telegram `cmd/agent-worker/main.go`.
- Budget scope label: `global_day`.
- Image: `main-a787e97` is the #1113 merge, so it contains #1089, #1090 and
  #1092 (server and worker).
- `MANAGED_MAX_JOB_COST_USD`: 0.25, equal to the worker cap.
- mctl-telegram#1092, #1093 and #1094 are closed; none of them is a task here.

## Open questions

- The issue puts the run token in Vault `secret/platform/mctl-telegram/ai-gateway`
  (manifest) but has the worker read
  `secret/platform/labs/agent-worker-managed-preview/gateway`. This proposal
  keeps both as written: the manifest names the canonical home and activation
  step 3 writes both. The alternative is to point the worker's gateway
  ExternalSecret straight at `platform/mctl-telegram/ai-gateway` and keep a
  single copy; that is decided at activation step 4 and changes no file here.
- The hourly spend threshold is not given in the issue. This proposal uses
  $1.00/h (20 % of the $5.00 global daily cap).
