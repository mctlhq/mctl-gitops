# Tasks: issue-2345-feat-labs-agent-worker-managed-preview-m

Git changes (one PR, feature branch):

- [ ] 1. Quote in the PR description the worker env contract already resolved in
  requirements.md: `AGENT_MODEL=Qwen/Qwen3.6-35B-A3B`, prices 1.40/4.40, and the
  names `AGENT_OPENAI_API_KEY` / `AGENT_GATEWAY_TOKEN` read by mctl-telegram
  `cmd/agent-worker/main.go`. DoD: no TODO and no placeholder in any file.
- [ ] 2. (depends on 1) Create `platform-gitops/services/labs/agent-worker-managed-preview/values.yaml`
  as described in design.md section 1. It has `replicaCount: 0`, the same image
  and tag as `agent-worker-preview`, OpenAI or pool env, no `AGENT_SYSTEM_PROMPT`,
  NO ExternalSecret and NO `envFrom` (a header comment points at activation
  step 4 in requirements.md), resources 50m/64Mi to 500m/256Mi, read-only root
  fs, and a `/tmp` emptyDir only. DoD: `helm template test platform-gitops/helm-charts/base-service -f <file>`
  renders a Deployment with 0 replicas and no ExternalSecret.
- [ ] 3. Create `catalog-info.yaml` for the component, cloned from
  `agent-worker-preview`. DoD: all names and annotations read
  `agent-worker-managed-preview`.
- [ ] 4. Add the new values path to `.github/deploy-signal.yaml` with
  `tracks_main: true`. DoD: `python3 .github/scripts/deploy-signal.py --self-test`
  and the coverage check pass.
- [ ] 5. Add `MANAGED_RUNTIME_ENABLED: "false"`, `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`,
  `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"`,
  `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"` and `MANAGED_MAX_JOB_COST_USD: "0.25"`
  to `services/labs/mctl-telegram-preview/values.yaml`, with a comment that the
  flag turns on only in activation step 1 after the owner's approval. DoD:
  production `services/labs/mctl-telegram/values.yaml` is untouched, and no
  file in this PR sets `MANAGED_RUNTIME_ENABLED: "true"`.
- [ ] 6. Add `cloudflare_ai_gateway.mctl_telegram` (id `mctl-telegram`) and the
  output `mctl_telegram_ai_gateway_url` to `infrastructure/cloudflare/account/ai-gateway.tf`.
  DoD: `tofu validate`. The `cloudflare-plan.yml` plan shows exactly one create
  and no change to `mctl_support` or the custom providers.
- [ ] 7. Add the token `mctl-telegram-ai-gateway-run (Vault platform/mctl-telegram/ai-gateway)`
  with `local.pg.ai_gateway_run` to `infrastructure/cloudflare/tokens/manifest.tf`.
  DoD: the plan shows one token create.
- [ ] 8. Add `labs-agent-worker-managed-preview` to the instance list in
  `bootstrap/templates/mctl-platform/mctl-telegram-agent-preview-monitor.yaml`,
  with a comment. DoD: the bootstrap chart renders and the keep filter is
  unchanged.
- [ ] 9. Add the group `mctl-telegram-managed` to
  `vm-rules/mctl-telegram-ops.yaml` with `MctlAgentManagedGlobalCapHit`,
  `MctlAgentManagedSpendHigh` and `MctlAgentManagedPoolWorkerDown` (global cap
  rule on `scope="global_day"` exactly), and extend the provenance table. DoD: `scripts/check-vm-rules.sh` passes.
- [ ] 10. (depends on 9) Add promtool tests to
  `vm-rules/tests/mctl-telegram-ops_test.yaml`. DoD: `promtool test rules` passes.

Activation (NOT part of this change; each step only after the owner's separate
activation approval and after the previous step is verified; the exact steps
and checks are in requirements.md, "Activation"):

- [ ] A1. PR: `MANAGED_RUNTIME_ENABLED: "true"`. Verify the mint route answers and
  no account is managed.
- [ ] A2. `cloudflare-apply.yml`: `account` then `tokens`, each plan reviewed.
  Verify the gateway reads back with logs off, auth on, byok_only, cache 0.
- [ ] A3. Mint the pool token, record its `jti`, write the three Vault secrets.
- [ ] A4. PR: add the three ExternalSecrets and `envFrom`, still at 0 replicas.
  Verify all `SecretSynced` and the Application Healthy. Never in the same PR
  as A5.
- [ ] A5. PR: `replicaCount: 1`. Verify pod Ready, scrape target up, credential
  domain series present, T6 smoke.
- [ ] A6. The owner switches one preview account to `managed`; the soak of at
  least 30 jobs runs (p50/p95 latency, cost per job, reservation drift = 0,
  cross-account violations = 0, gateway logs = 0); the new series are
  confirmed live and the provenance table is updated.

## Tests

- [ ] T1. `helm lint platform-gitops/helm-charts/base-service` and `helm template`
  of the new values file. Expected: 0 replicas, no ingress, only `/tmp` writable,
  `readOnlyRootFilesystem: true`, and no ExternalSecret and no `envFrom`.
- [ ] T2. `helm template` of `mctl-telegram-preview` shows the five `MANAGED_*`
  env vars with `MANAGED_RUNTIME_ENABLED` = "false". A grep confirms no
  `MANAGED_` in `services/labs/mctl-telegram/values.yaml`.
- [ ] T3. promtool tests: GlobalCapHit fires on a `scope="global_day"` increase
  and not on an `account_day` or `account_month` one. SpendHigh fires at $1.20/h and not at $0.80/h.
  PoolWorkerDown fires after 10m with `mctl_agent_managed_accounts=1` and no
  `up` series, and does not fire with `up=1` or with `mctl_agent_managed_accounts=0`.
- [ ] T4. The deploy-signal coverage check passes with the new entry.
- [ ] T5. Cloudflare plan: one gateway create and one token create, with no
  other diff.
- [ ] T6. After activation step A2, one smoke request with `cf-aig-authorization` returns
  200 at `<mctl-telegram gateway>/custom-hetzner/v1/chat/completions`, and the
  same request without the bearer returns 401.

## Rollback

Follow the issue's order, smallest step first:
1. The owner switches the account back to `runtime: own`. The install-revision
   fence requeues any in-flight managed attempt.
2. Set `replicaCount: 0` on `agent-worker-managed-preview`.
3. Revoke the pool token's `jti` on tg-preview. This kills all job tokens
   derived from it.
4. Set `MANAGED_RUNTIME_ENABLED: "false"` in `mctl-telegram-preview` (or revert
   the four keys).
To remove everything, revert the PR. Deleting the `mctl-telegram` gateway and
token is a destroy that needs `allow_destroy` on `cloudflare-apply`. Then delete
the Vault paths under `secret/platform/labs/agent-worker-managed-preview/` and
`secret/platform/mctl-telegram/ai-gateway`. `agent-worker-preview`,
`mctl-support` and production `mctl-telegram` are not touched at any step.
