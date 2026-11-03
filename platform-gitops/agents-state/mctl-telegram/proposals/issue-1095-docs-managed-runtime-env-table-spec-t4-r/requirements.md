# Document the managed runtime: worker env table and pool mode, spec T4/Runtime, where jobs run, pool-token runbook, ADR 0008 accepted

## Context

Issue #1095 is the last slice (docs) of epic #1088, which is P5 of #1002. The
code slices (#1089 runtime field and consent, #1090 pool credential and claim
path, #1091 OpenAI runner, #1092 ledger and caps) are on `main`, and the gitops
deployment (mctlhq/mctl-gitops#2345) is in place. On gitops this is
`services/labs/agent-worker-managed-preview` (inert, replicaCount 0), the server
flags in `services/labs/mctl-telegram-preview` (`MANAGED_RUNTIME_ENABLED:
"false"`) and the `mctl-telegram-managed` alert group. The documentation still
says the managed model is "planned, not implemented". That wording is in
`docs/agent-worker.md`, `docs/assistants/spec.md` (T4 row),
`docs/contracts/agent-job-api.md` and `docs/agent-runtime/threat-model.md`, and
`docs/agent_job_api_test.go` (`TestCredentialBoundary_DocumentsAgree`) requires
it. The worker env table has no `AGENT_POOL_MODE` row. `how-it-works.md` only
knows the Mac mini worker. The runbook has the server flags but no procedure for
the pool token, and no sections for the three gitops alerts whose
`runbook_url` already points at `docs/runbook.md#mctlagentmanagedglobalcaphit`,
`#mctlagentmanagedspendhigh` and `#mctlagentmanagedpoolworkerdown`. ADR 0008 is
still `Proposed`.

The issue asks for documentation an operator can act on before the managed
worker is activated: what to set, how to mint, rotate and revoke the one
credential that can claim every managed account's jobs, what to do when the
budget alert fires, and the rollback order. Docs that disagree with the code
are worse than none here, because the pool token is the widest credential in
the agent API. Every new regression test must fail when the documented fact is
removed or reverted. The PR states the mutation for each test.

## User stories

- AS a platform operator I WANT one env table for `cmd/agent-worker` that lists
  every variable the binary reads, including `AGENT_POOL_MODE` SO THAT I can
  configure a pool worker without reading `cmd/agent-worker/main.go`.
- AS an on-call engineer paged by `MctlAgentManagedGlobalCapHit`,
  `MctlAgentManagedSpendHigh` or `MctlAgentManagedPoolWorkerDown` I WANT the
  alert's `runbook_url` to land on a section with diagnosis and mitigation SO
  THAT I do not have to work it out from the ADR.
- AS an admin I WANT a mint / rotate / revoke procedure for the pool token SO
  THAT a leaked or expiring pool credential is handled in a known order.
- AS an assistant author or account owner reading `spec.md` I WANT T4 and the
  install's `runtime` field to describe both the own and the managed worker,
  with the consent text SO THAT I know what changes when I choose `managed`.
- AS a reviewer of ADR 0008 I WANT its status, PR numbers and named
  files/symbols to match the merged code SO THAT the record can be trusted.

## Acceptance criteria (EARS)

- WHEN `docs/agent-worker.md` is read THE SYSTEM SHALL have a configuration table
  row for every environment variable `cmd/agent-worker/main.go` reads in poll
  mode, including `AGENT_POOL_MODE`. The internal `AGENT_JOB_*` subprocess
  variables stay in the existing note below the table.
- WHEN `docs/agent-worker.md` is read THE SYSTEM SHALL contain a "Pool mode"
  section. It SHALL state that `AGENT_API_TOKEN` is then the claim-only
  `aud=agent-pool` token, that every per-job call (tools, status, cost report,
  completion check) uses the job token with no fallback to the pool token, that
  a job without a job token fails, and that the job budget is the smaller of
  `AGENT_MAX_BUDGET_USD` and the claim's `max_job_cost_usd` (`jobBudget` in
  `internal/agentworker/finishrun.go`).
- WHILE `AGENT_POOL_MODE=true` THE SYSTEM SHALL NOT describe the cost report as
  using `AGENT_API_TOKEN`. The existing "Job token for tools, account token for
  accounting" bullet SHALL be limited to own mode, to match
  `OpenAIRunner.Run` and `ClaudeInvoker` (`internal/agentworker/openairunner.go`,
  `claudeinvoker.go`).
- WHEN `docs/assistants/spec.md` is read THE SYSTEM SHALL show the T4 row as
  "own worker, or the platform's managed worker via `runtime: managed`", naming
  `aud=agent`, `aud=agent-pool` and `aud=agent-job`. It SHALL contain a Runtime
  and consent section that quotes the consent text and the value
  `managed-data-flow/v1` verbatim, lists the refusals (`managed_consent_required`,
  `managed_disabled`, `managed_quota`) and explains the budget hold.
- WHEN the install example in `spec.md` is read THE SYSTEM SHALL show
  `runtime: own` with its explanatory comment, and SHALL NOT show `managed`.
- WHEN `docs/assistants/how-it-works.md` section 5 is read THE SYSTEM SHALL say
  where jobs run for each runtime: own on the Mac mini LaunchAgent, managed on
  the in-cluster `labs/agent-worker-managed-preview` pool worker with
  `AGENT_RUNNER=openai` and `AGENT_POOL_MODE=true`. It SHALL say that the
  database claim predicate keeps the two runtimes apart.
- WHEN `docs/runbook.md` is read THE SYSTEM SHALL contain a managed-runtime
  section with mint, rotate and revoke procedures for the pool token
  (`POST /api/agent/pool-token`, `{pool_name, ttl_hours}`, response
  `{pool_token, expires_at, jti}`, revoke with `revoke_worker_token` by `jti`).
- WHEN `docs/runbook.md` is read THE SYSTEM SHALL contain the anchors
  `mctlagentmanagedglobalcaphit`, `mctlagentmanagedspendhigh` and
  `mctlagentmanagedpoolworkerdown`, each with Symptom, Likely causes,
  Diagnostic queries and Mitigation subsections, and SHALL list them in the
  table of contents.
- WHEN `docs/runbook.md` gives the rollback THE SYSTEM SHALL list it in this
  order: `runtime: own`, scale the pool worker to 0, revoke the pool `jti`, then
  `MANAGED_RUNTIME_ENABLED=false`. It SHALL state that flag off pauses managed
  accounts and does not fall back to their own workers.
- WHEN the runbook configuration reference is read THE SYSTEM SHALL list every
  `MANAGED_*` variable `internal/config/config.go` reads, including
  `MANAGED_RUNTIME_MAX_ACCOUNTS` (default `1`), which is missing today.
- WHEN `docs/contracts/agent-job-api.md` and `docs/agent-runtime/threat-model.md`
  describe the managed runtime THE SYSTEM SHALL describe it as implemented and
  behind `MANAGED_RUNTIME_ENABLED`, not as planned.
- WHEN ADR 0008 is read THE SYSTEM SHALL show `Status: Accepted` with the merged
  PR number of each slice, and `docs/adr/README.md` SHALL show 0008 as Accepted.
  Every file, symbol, metric and default the ADR names SHALL either exist in
  the code or be corrected or marked as not implemented.
- IF a documented env var, runbook anchor or credential-boundary statement is
  removed or reverted THEN THE SYSTEM SHALL fail `go test ./docs/...`.

## Out of scope

- Any code change in `cmd/`, `internal/` or the worker or server behaviour.
- Gitops changes: activation steps, ExternalSecrets, alert rule tuning,
  replicaCount. The runbook describes them; mctl-gitops owns them.
- Changing the alert thresholds in `mctl-telegram-ops.yaml`.
- Production rollout docs beyond what ADR 0008 section 6 already gates (#889,
  #334).
- A slimmer worker image without Node and the Claude CLI (an ADR follow-up).

## Open questions

- Merged PR numbers per slice: the clone is shallow (one merge commit,
  #1113 for #1092). The implementer must list the merged PRs for #1089-#1094
  and mctl-gitops#2345 (`gh pr list --state merged --search "<issue>"`). If a
  slice (#1093 C1 gate, #1094 CI image) is not merged, the ADR status stays
  `Accepted` for the decision, and that slice is listed as pending, not as
  done.
- Hetzner rate limit: ADR 0008 says 10 requests per 60 s, `docs/agent-worker.md`
  says "about 35 requests per minute per key", and the deployed
  `AGENT_OPENAI_MIN_INTERVAL` is `6s` (10 per minute). This proposal documents
  the deployed `6s` as the recommended Hetzner setting and keeps the
  ADR figure. It removes the unsourced "35" unless the implementer finds a
  source.
- The issue says the install example "gets `runtime: own` commented". The
  example already has `runtime: own  # own (default) | managed; ...`. This
  proposal reads "commented" as "annotated" and keeps the line live, because
  `own` is the default and the example shows defaults elsewhere too
  (`paused: false  # default: true`). If the author meant a commented-out
  line, the change is one character.
- The ADR lists `mctl_agent_openai_requests_total{status_class}` and a retries
  metric. Neither exists in `internal/metrics/metrics.go` or the worker. This
  proposal marks them as not implemented in the ADR and does not name them in
  the runbook, because `TestRunbookMetricNamesRegistered` would fail.
