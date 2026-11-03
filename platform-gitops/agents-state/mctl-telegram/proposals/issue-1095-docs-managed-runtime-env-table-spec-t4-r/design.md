# Design: issue-1095-docs-managed-runtime-env-table-spec-t4-r

## Current state

Code (merged on `main`, HEAD `a787e97`, the merge of #1113 for #1092):

- `cmd/agent-worker/main.go` reads these in poll mode: `AGENT_API_BASE_URL`,
  `AGENT_API_TOKEN`, `AGENT_CREDENTIAL_DOMAIN_ID`, `AGENT_MAX_BUDGET_USD`,
  `AGENT_RUNNER` (l.98), `AGENT_POOL_MODE` (l.102, `envBoolStrict`),
  `AGENT_CLAUDE_BIN`, `AGENT_SYSTEM_PROMPT`, `AGENT_MODEL`,
  `AGENT_OPENAI_BASE_URL`, `AGENT_OPENAI_API_KEY`, `MODEL_INPUT_USD_PER_MTOK`,
  `MODEL_OUTPUT_USD_PER_MTOK`, `AGENT_MAX_TURNS` (default 12),
  `AGENT_OPENAI_MIN_INTERVAL`, `AGENT_GATEWAY_TOKEN`,
  `AGENT_WORKER_CONCURRENCY`, `AGENT_HEALTH_ADDR` and `AGENT_METRICS_ALLOW_CIDR`.
- Pool mode: `OpenAIRunner.Run` (`internal/agentworker/openairunner.go` l.56-65)
  sends the cost report on a client built from `job.JobToken` with
  `WithJobScope()` when `PoolMode` is set. `ClaudeInvoker`
  (`claudeinvoker.go` l.209, l.284-291) refuses a job without a job token and
  finishes on the job token. `jobBudget` (`finishrun.go` l.99) takes the
  smaller of the configured budget and `job.MaxJobCostUSD`.
- Server: `cmd/server/managedpool.go`. `managedPoolEnabled` requires both
  `MANAGED_RUNTIME_ENABLED` and `OAUTHJWTSecret`. `wireManagedPool` mounts
  `POST /api/agent/pool-token` behind `adminMW`. `warnManagedJobsPaused` logs
  at start when the flag is off.
  `internal/agentapi/pooltokenhandler.go`: the scope is `admin:users`, the
  request is `{pool_name, ttl_hours}`, the response is
  `{pool_token, expires_at, jti}`, and the TTL is clamped by `poolTokenTTL`
  to `defaultAgentTokenTTL`/`maxAgentTokenTTL`.
  `localjwt.ValidPoolName` uses `^[a-z0-9][a-z0-9-]{0,62}$`. `requireNotPool`
  is in `internal/agentapi/binding.go`.
- Config: `internal/config/config.go` reads `MANAGED_RUNTIME_ENABLED`,
  `MANAGED_RUNTIME_MAX_ACCOUNTS` (default 1, l.580),
  `MANAGED_MAX_INFLIGHT_PER_ACCOUNT`, `MANAGED_MAX_JOB_COST_USD` and the three
  `MANAGED_BUDGET_USD_*`.
- Metrics (`internal/metrics/metrics.go`): `mctl_agent_budget_exhausted_total`,
  `mctl_agent_budget_deferred_total`, `mctl_agent_managed_accounts`,
  `mctl_agent_usage_cost_usd_total`, `mctl_agent_usage_tokens_total`,
  `mctl_agent_usage_held_usd` and `mctl_agent_usage_held_rows`. The budget
  scopes in `internal/db/agent_usage.go` are `account_day`, `account_month`
  and `global_day`. `mctl_agent_openai_requests_total`, which the ADR names,
  does not exist.
- Consent: `managed-data-flow/v1` is in `internal/db/managed_runtime.go` and
  `internal/mcp/assistant_tools.go`. `managed_consent_required` is in
  `internal/assistantinstall/service.go` and `internal/agentapi/profilehandler.go`.

Docs today:

- `docs/agent-worker.md`: the config table (l.92-111) has every runner row but
  no `AGENT_POOL_MODE`. "Own and external runtimes" (l.23-38) says the
  managed runtime "is planned ... that is not implemented". The bullet "Job
  token for tools, account token for accounting" (l.127) is wrong for pool
  mode. l.111 says "Hetzner allows about 35 requests per minute per key",
  which contradicts ADR 0008 (10 per 60 s).
- `docs/assistants/spec.md`: the install example (l.126) already has
  `runtime: own  # own (default) | managed; ...` and a short paragraph
  (l.141-146). The T4 row (l.768) says the pool credential is "planned
  (#1090, ADR 0008), not implemented". There is no consent text and no budget
  hold.
- `docs/assistants/how-it-works.md` section 5 "Worker" (l.417-424) only
  describes the Mac mini LaunchAgent.
- `docs/contracts/agent-job-api.md` l.15 and `docs/agent-runtime/threat-model.md`
  l.22 say "planned, not implemented".
- `docs/runbook.md`: the "Configuration reference" (l.336-363) has the
  `MANAGED_*` rows and the worker `AGENT_POOL_MODE` row, but no
  `MANAGED_RUNTIME_MAX_ACCOUNTS`. "Credential rotation" (l.473) covers only
  the account token. There is no pool-token procedure, no managed alert
  section and no anchors `mctlagentmanaged*`. "Revoking a leaked worker token"
  (l.2470) describes `revoke_worker_token` by `jti` for `/api/mcp/worker-token`
  tokens only.
- `docs/adr/0008-managed-runtime.md` has `Status: Proposed`, and
  `docs/adr/README.md` l.19 says `Proposed`.
- Doc tests: `docs/agent_job_api_test.go`
  `TestCredentialBoundary_DocumentsAgree` requires "planned" or "not
  implemented" in the four documents, so it currently enforces the stale
  wording. `docs/runbook_test.go` has `TestRunbookAnchorsPresent` (a fixed
  list) and `TestRunbookMetricNamesRegistered` (every `mctl_*` in the runbook
  must appear in `metrics.go`).

Deployed state checked:

- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-managed-preview/values.yaml`:
  `replicaCount: 0`; image `ghcr.io/mctlhq/agent-worker-preview:main-a787e97`;
  `AGENT_RUNNER=openai`, `AGENT_POOL_MODE=true`,
  `AGENT_MODEL=Qwen/Qwen3.6-35B-A3B`, a base URL on the `mctl-telegram`
  gateway with `custom-hetzner`, `AGENT_MAX_BUDGET_USD=0.25`,
  `AGENT_MAX_TURNS=12`, `AGENT_OPENAI_MIN_INTERVAL=6s`, concurrency 1, prices
  1.40/4.40, and an in-cluster `AGENT_API_BASE_URL`. There are no
  ExternalSecrets yet; the header says they are added in activation step 4
  and that the secret env names are `AGENT_API_TOKEN`, `AGENT_OPENAI_API_KEY`
  and `AGENT_GATEWAY_TOKEN`. The rollback comment gives the same order as the
  ADR.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`
  l.287-299: `MANAGED_RUNTIME_ENABLED: "false"`,
  `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`, `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY:
  "1.00"`, `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"` (not the code default
  20.00), `MANAGED_MAX_JOB_COST_USD: "0.25"`.
- `$MCTL_GITOPS_ROOT/infra-components/observability/vm-rules/mctl-telegram-ops.yaml`,
  group `mctl-telegram-managed`: `MctlAgentManagedGlobalCapHit` fires on
  `increase(mctl_agent_budget_exhausted_total{scope="global_day"}[15m]) > 0`.
  `MctlAgentManagedSpendHigh` fires on
  `increase(mctl_agent_usage_cost_usd_total{runner="openai"}[1h]) > 1.00`.
  `MctlAgentManagedPoolWorkerDown` fires when
  `max(mctl_agent_managed_accounts) > 0` and the `up` of
  `labs-agent-worker-managed-preview-base-service` is absent, for 10m. All
  three have a `runbook_url` that points at an anchor that does not exist yet
  in `docs/runbook.md` (`grep -c mctlagentmanaged` = 0).
- `mctl_get_service_status(labs, agent-worker-managed-preview)`: Argo CD
  Healthy and Synced, image tag `main-a787e97`.
- Not observed: the merged PR numbers of #1089-#1091, #1093 and #1094. The
  clone is shallow. See Open questions.

## Proposed solution

This is a docs-only PR, plus doc tests that pin each fact to the code. Changes
by file:

1. `docs/agent-worker.md`
   - Config table: add an `AGENT_POOL_MODE` row (`no`, `true`/`false`, strict
     parse, anything else refuses to start). Mark `AGENT_API_TOKEN` as "the
     account token (`aud=agent`) or, with `AGENT_POOL_MODE=true`, the pool
     token (`aud=agent-pool`, `POST /api/agent/pool-token`)". Replace the
     Hetzner "35 requests" note with "`6s` keeps within Hetzner's 10 requests
     per 60 s (ADR 0008); the labs pool worker uses `6s`".
   - Rewrite "Own and external runtimes" so the managed runtime is
     implemented and behind `MANAGED_RUNTIME_ENABLED`. Keep the strings
     `aud=agent` and `agent-pool`.
   - New section `### Pool mode (managed runtime, #1090)`: the pool token can
     only call `POST /jobs/claim`. Every per-job call uses the job token, which
     the server mints from the job's user with the pool's `jti`. A job without
     a job token is a hard error. The budget is
     `min(AGENT_MAX_BUDGET_USD, max_job_cost_usd)`. The worker never chooses
     the account it bills. Include an example env block that mirrors the labs
     values, with secrets named but no values.
   - Limit the "Job token for tools, account token for accounting" bullet to
     own mode, and add the pool-mode sentence.
2. `docs/assistants/spec.md`
   - T4 row: "Own or managed runtime | runs their own worker against the agent
     job API, or the platform's managed worker via `runtime: managed`". The
     gate column names `aud=agent` (own), `aud=agent-pool` (platform pool,
     claim only) and `aud=agent-job` (both), and says that policy and the send
     gate are server-side either way.
   - New `### Runtime and consent` under Install. It covers the field
     semantics, including that an install without `runtime` leaves it
     unchanged. It quotes the consent text verbatim from ADR 0008 section 1
     and checks it against the descriptor in `internal/mcp/assistant_tools.go`.
     It covers the value `managed-data-flow/v1`, the stored version and time,
     the erase on `managed -> own`, the refusals
     (`managed_consent_required`, `managed_disabled`, `managed_quota`), the
     install-revision bump and fence on a switch, and the budget hold (jobs
     stay pending until the window resets, the owner is notified once, and
     messages are not dropped). The existing l.141-146 paragraph moves into
     this section.
   - Install example: keep `runtime: own` with its comment (see Open
     questions).
3. `docs/assistants/how-it-works.md` section 5: rename "Worker" to "Where jobs
   run". Own: the Mac mini LaunchAgent, as today. Managed: one pool worker
   per environment, `labs/agent-worker-managed-preview`, in-cluster API URL,
   `AGENT_RUNNER=openai`, `AGENT_POOL_MODE=true`, the model through the
   `mctl-telegram` AI Gateway with logging and caching off. Separation: the
   claim SQL predicate on `agent_profiles.runtime`. When the flag is off,
   managed jobs wait.
4. `docs/contracts/agent-job-api.md` l.15 and
   `docs/agent-runtime/threat-model.md` l.22: say the runtime is implemented
   behind `MANAGED_RUNTIME_ENABLED`, and give the pool route allowance
   (`POST /jobs/claim` only, `requireNotPool` elsewhere). The threat model gets
   the pool row's residual risk from ADR 0008 Consequences.
5. `docs/runbook.md`
   - Configuration reference: add `MANAGED_RUNTIME_MAX_ACCOUNTS` (`1`). Note
     that the flag also needs the JWT signing secret (`managedPoolEnabled`).
   - New `### Managed runtime: pool token` under Communication Agent
     operations:
     - Mint: an `admin:users` bearer, `POST /api/agent/pool-token` with
       `{"pool_name":"labs-preview","ttl_hours":720}`. Record `jti` and
       `expires_at`, and write `pool_token` straight to
       `secret/platform/labs/agent-worker-managed-preview/`. Never paste it
       into a chat or a log.
     - Rotate: with one replica, mint a new token and write it to Vault. Wait
       for ExternalSecret refresh or force it, roll the pod, and verify claims
       on the new token. Then revoke the old `jti`. Make clear that job tokens
       from the old pool die with it within 15 s, which ends their in-flight
       jobs; those jobs are requeued by the sweeper and their reservations
       become `held`.
     - Revoke: `revoke_worker_token` with the `jti`, by cross-reference to
       "Revoking a leaked worker token", with a note that it also covers
       `aud=agent-pool` because `derivedAudiences` includes it.
   - New `### Managed runtime rollback`: the ordered list from ADR 0008
     section 6, the flag-off effect and the start log line.
   - Three alert sections, each with an `<a id>` that matches the gitops
     `runbook_url`, the same Symptom / Likely causes / Diagnostic queries /
     Mitigation / Escalation shape as `MctlAgentJobCostHigh`, and TOC entries.
     They use only metrics registered in `metrics.go`. The budget-exhausted
     section explains durable versus in-flight exhaustion, the
     `budget_paused_until` hold, `mctl_agent_usage_held_usd` drift, and when
     to raise a cap.
6. `docs/adr/0008-managed-runtime.md` and `docs/adr/README.md`: set the status
   to `Accepted (<date>)` and list each slice with its merged PR. Fix the
   drift found so far:
   - In section 5, mark `mctl_agent_openai_requests_total` and the retries
     metric as not implemented.
   - Section 2 says the pool route is mounted "only under the flag". Add that
     `managedPoolEnabled` also requires the JWT secret.
   - The worker cost report goes through the job token in pool mode. The ADR
     is right here; check the wording against `openairunner.go`.
   - The ADR says "Unlike 0001-0007 this record is written before the code";
     add a line that it has now been reconciled with the code.
   - Grep every other backticked symbol in the ADR before it is listed as
     correct (see tasks).
7. Tests in `docs/`:
   - `agent_job_api_test.go`: change `TestCredentialBoundary_DocumentsAgree`
     to require `aud=agent`, `agent-pool` and `aud=agent-job`, and to refuse
     the phrase `planned, not implemented` and the regex
     `agent-pool[^.]*(planned|not implemented)`. Mutation: restore the old
     T4 row, and the test fails.
   - New `agent_worker_env_test.go` `TestAgentWorkerEnvTableComplete`: scan
     `../cmd/agent-worker/main.go` for `requireEnv|requiredEnvFloat|env*(` and
     `os.Getenv("...")` literals, exclude `AGENT_JOB_*`, and require each name
     as a table cell in `agent-worker.md`. Mutation: delete the
     `AGENT_POOL_MODE` row, and the test fails.
   - New `TestRunbookManagedConfigComplete`: every `"MANAGED_[A-Z_]+"` literal
     in `../internal/config/config.go` appears in `runbook.md`. Mutation: drop
     the `MANAGED_RUNTIME_MAX_ACCOUNTS` row.
   - `runbook_test.go` `TestRunbookAnchorsPresent`: add the three
     `mctlagentmanaged*` anchors. Mutation: delete one anchor.
   - New `TestRunbookManagedRollbackOrder`: in the managed rollback section,
     the indexes of `runtime: own`, `replicaCount`/`scale`, `revoke_worker_token`
     and `MANAGED_RUNTIME_ENABLED` are strictly increasing. Mutation: swap two
     steps.
   - New `TestSpecConsentTextMatchesCode`: the consent value
     `managed-data-flow/v1` appears in `spec.md`, and the consent sentence in
     `spec.md` equals the constant in `internal/db/managed_runtime.go` (or the
     MCP descriptor, whichever holds the text). Mutation: edit one word in the
     doc.

Why this way: the doc tests already pin docs to code (route tables, metric
names). Extending that pattern makes every fact the issue asks for fail CI when
it drifts, and that is how the epic's "every regression test must fail with
the bug reintroduced" rule applies to a docs slice.

## Alternatives

- Keep the env table only in the runbook and link to it from
  `agent-worker.md`. Dropped: the issue names `agent-worker.md` as the home,
  and the runbook table is server-centric. The runbook keeps the single
  `worker AGENT_POOL_MODE` cross-reference row.
- Point the gitops alert `runbook_url`s at ADR 0008 instead of adding runbook
  sections. Dropped: the ADR is a decision record, not a procedure. The URLs
  are already merged in gitops, and changing them is another repo's PR.
- Generate the env table from code. Dropped: it is more machinery than one
  docs slice needs. The completeness test gives the same guarantee and keeps
  hand-written meanings.

## Platform impact

- No migrations, no runtime or config change, no resource impact. Only Markdown
  under `docs/` and `_test.go` files in package `docs` change.
- Backward compatibility: `TestCredentialBoundary_DocumentsAgree` changes
  meaning, from "say planned" to "say implemented". This is intentional and
  is stated in the PR.
- Risk: the new completeness test parses `main.go` with a regex and can
  break on a helper rename. Mitigation: match the helper set (`requireEnv`,
  `requiredEnvFloat`, `envFloat`, `envBoolStrict`, `envPositiveInt`,
  `envDuration`, `envConcurrency`, `os.Getenv`) and fail loudly if it finds
  fewer than 15 names, so the test cannot pass vacuously.
- Risk: the runbook could document the pool token in a way that leaks it,
  for example `curl ... | tee`. Mitigation: the procedure pipes the response
  through `jq -r .pool_token` straight into `vault kv put ... -`, and names
  only `jti` in notes. `internal/audit/redact.go` is not affected.
- Risk: the ADR could list PR numbers for slices that are not merged.
  Mitigation: the implementer verifies each one with `gh pr view`. Unmerged
  slices are listed as pending.

## Open questions

- Merged PR numbers for #1089, #1090, #1091, #1093, #1094 and
  mctl-gitops#2345 were not observable from the shallow clone. Only #1113
  (#1092) was seen.
- The Hetzner request limit in `agent-worker.md` (35 per minute) conflicts
  with the ADR (10 per 60 s). The deployed `6s` matches the ADR. The proposal
  follows the ADR and the deployment.
- "`runtime: own` commented" is read as annotated, not commented out.
- The global day cap is deployed as 5.00 on tg-preview, against a code
  default of 20.00. The runbook gives both and says which one applies where.
  This is not a defect.
