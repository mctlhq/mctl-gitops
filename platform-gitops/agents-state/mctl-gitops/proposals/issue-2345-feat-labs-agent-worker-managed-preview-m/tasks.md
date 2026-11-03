# Tasks: issue-2345-feat-labs-agent-worker-managed-preview-m

Git changes (one PR, feature branch):

- [ ] 1. Confirm the worker env contract in mctl-telegram `cmd/agent-worker/main.go`:
  the names for the provider key and the gateway bearer, `AGENT_MODEL`,
  `AGENT_OPENAI_BASE_URL`, `AGENT_MAX_TURNS`, `AGENT_OPENAI_MIN_INTERVAL` and
  `MODEL_*_USD_PER_MTOK`. Also get the C1 gate model id and its Nebius prices.
  DoD: names and values are quoted in the PR description. If the gate result is
  missing, `AGENT_MODEL` and the prices carry a `TODO(C1 gate)` comment and
  `replicaCount` stays 0.
- [ ] 2. (depends on 1) Create `platform-gitops/services/labs/agent-worker-managed-preview/values.yaml`
  as described in design.md section 1. It has `replicaCount: 0`, the same image
  and tag as `agent-worker-preview`, OpenAI or pool env, no `AGENT_SYSTEM_PROMPT`,
  three `vault-backend` ExternalSecrets (`api`, `openai`, `gateway`) wired via
  `envFrom`, resources 50m/64Mi to 500m/256Mi, read-only root fs, and a `/tmp`
  emptyDir only. DoD: `helm template test platform-gitops/helm-charts/base-service -f <file>`
  renders a Deployment with 0 replicas and three ExternalSecrets with the exact
  remote keys.
- [ ] 3. Create `catalog-info.yaml` for the component, cloned from
  `agent-worker-preview`. DoD: all names and annotations read
  `agent-worker-managed-preview`.
- [ ] 4. Add the new values path to `.github/deploy-signal.yaml` with
  `tracks_main: true`. DoD: `python3 .github/scripts/deploy-signal.py --self-test`
  and the coverage check pass.
- [ ] 5. Add `MANAGED_RUNTIME_ENABLED: "true"`, `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`,
  `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"` and
  `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"` to
  `services/labs/mctl-telegram-preview/values.yaml`, with a comment. DoD:
  production `services/labs/mctl-telegram/values.yaml` is untouched.
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
  `MctlAgentManagedSpendHigh` and `MctlAgentManagedPoolWorkerDown`, and extend
  the provenance table. DoD: `scripts/check-vm-rules.sh` passes.
- [ ] 10. (depends on 9) Add promtool tests to
  `vm-rules/tests/mctl-telegram-ops_test.yaml`. DoD: `promtool test rules` passes.

Operator rollout (after merge, not git, in order):

- [ ] 11. Apply `infrastructure/cloudflare/account` and `tokens` via
  `cloudflare-apply.yml`, then write the run token to Vault
  `secret/platform/mctl-telegram/ai-gateway` (`token`) and to
  `secret/platform/labs/agent-worker-managed-preview/gateway`. DoD: reading the
  gateway back shows logs off, auth on, byok_only on and cache 0.
- [ ] 12. Write the Hetzner key to `.../agent-worker-managed-preview/openai`.
  Mint the pool token with `POST /api/agent/pool-token` on tg-preview
  (`pool_name=agent-worker-managed-preview`), record its `jti`, and write it to
  `.../api`. DoD: all three ExternalSecrets are `SecretSynced`.
- [ ] 13. Follow-up PR: set `replicaCount: 1`. DoD: the pod is Ready, the scrape
  target is up, and `mctl_agent_credential_domain{domain_id="platform/labs/agent-worker-managed-preview/openai"}`
  is present.
- [ ] 14. The owner switches the preview account to `runtime: managed`, then a
  soak of at least 30 jobs runs. DoD: p50/p95 latency and cost per job are
  recorded, reservation drift = 0, cross-account violations = 0, and gateway
  logs = 0. All new `mctl_agent_*` series are confirmed live and the provenance
  table is updated.
- [ ] 15. mctl-telegram follow-up: extend `preview-deploy.yml` to bump this
  values file's `image.tag`. DoD: the tag of the new component matches
  `agent-worker-preview` after the next main push.

## Tests

- [ ] T1. `helm lint platform-gitops/helm-charts/base-service` and `helm template`
  of the new values file. Expected: 0 replicas, no ingress, only `/tmp` writable,
  `readOnlyRootFilesystem: true`, three ExternalSecrets with `ClusterSecretStore`
  `vault-backend`.
- [ ] T2. `helm template` of `mctl-telegram-preview` shows the four `MANAGED_*`
  env vars. A grep confirms no `MANAGED_` in `services/labs/mctl-telegram/values.yaml`.
- [ ] T3. promtool tests: GlobalCapHit fires on a global-scope increase and not
  on an account-scope one. SpendHigh fires at $1.20/h and not at $0.80/h.
  PoolWorkerDown fires after 10m with `mctl_agent_managed_accounts=1` and no
  `up` series, and does not fire with `up=1` or with `mctl_agent_managed_accounts=0`.
- [ ] T4. The deploy-signal coverage check passes with the new entry.
- [ ] T5. Cloudflare plan: one gateway create and one token create, with no
  other diff.
- [ ] T6. After task 11, one smoke request with `cf-aig-authorization` returns
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
