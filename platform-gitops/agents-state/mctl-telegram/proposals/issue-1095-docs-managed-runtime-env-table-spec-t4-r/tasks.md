# Tasks: issue-1095-docs-managed-runtime-env-table-spec-t4-r

- [ ] 1. Collect the facts. List the merged PRs for #1089, #1090, #1091, #1092
  (#1113), #1093, #1094 and mctl-gitops#2345 with `gh pr list --state merged
  --search`. Grep every backticked file, symbol, env var and metric in
  `docs/adr/0008-managed-runtime.md` against `cmd/` and `internal/`. Read the
  consent text constant (`internal/db/managed_runtime.go` /
  `internal/mcp/assistant_tools.go`).
  DoD: a drift list in the PR description. Each entry is "exists", "renamed
  to X" or "not implemented". It includes at least
  `mctl_agent_openai_requests_total` (not implemented) and the
  `managedPoolEnabled` JWT-secret condition.
- [ ] 2. Update `docs/agent-worker.md`.
  - Add the `AGENT_POOL_MODE` row.
  - Clarify `AGENT_API_TOKEN` for pool mode.
  - Fix the Hetzner rate note to 10 per 60 s, with `6s` as used in labs.
  - Rewrite "Own and external runtimes" so the managed runtime reads as
    implemented.
  - Add a `### Pool mode (managed runtime, #1090)` section with an example env
    block (secret names only, no values).
  - Limit the "account token for accounting" bullet to own mode.
  DoD: every env var read by `cmd/agent-worker/main.go` in poll mode has a
  row, and pool-mode token use matches `openairunner.go` l.56-65 and
  `claudeinvoker.go` l.284-291.
- [ ] 3. Update `docs/assistants/spec.md`.
  - Rewrite the T4 row: own worker, or the platform's managed worker via
    `runtime: managed`. Name `aud=agent`, `aud=agent-pool` and `aud=agent-job`.
  - Add a `### Runtime and consent` section with the verbatim consent text,
    `managed-data-flow/v1`, the refusals, the erase on switch back, the
    install-revision fence and the budget hold.
  - Keep `runtime: own` with its comment in the example.
  DoD: no "planned" or "not implemented" next to `agent-pool`.
- [ ] 4. Update `docs/assistants/how-it-works.md` section 5. Rename "Worker" to
  "Where jobs run" and cover the own runtime (Mac mini), the managed runtime
  (`labs/agent-worker-managed-preview`, openai runner, pool mode, AI Gateway
  with logs and cache off) and the SQL runtime predicate.
  DoD: a reader can tell which process claims a given account's job.
- [ ] 5. Update `docs/contracts/agent-job-api.md` l.15 and
  `docs/agent-runtime/threat-model.md` l.22 (depends on 1): mark the managed
  runtime as implemented behind `MANAGED_RUNTIME_ENABLED`, with the pool
  identity limited to claim only (`requireNotPool`).
  DoD: the four credential-boundary documents agree.
- [ ] 6. Update `docs/runbook.md` (depends on 1).
  - Add the `MANAGED_RUNTIME_MAX_ACCOUNTS` row and the JWT-secret note.
  - Add a `### Managed runtime: pool token` section with mint, rotate and
    revoke steps. The token goes straight to Vault and is never echoed.
  - Add a `### Managed runtime rollback` section, in this order: runtime own,
    then scale 0, then revoke jti, then flag off.
  - Add three alert sections with anchors `mctlagentmanagedglobalcaphit`,
    `mctlagentmanagedspendhigh` and `mctlagentmanagedpoolworkerdown`, and list
    them in the TOC.
  DoD: every gitops `runbook_url` in group `mctl-telegram-managed` resolves,
  and every metric named is registered in `internal/metrics/metrics.go`.
- [ ] 7. Update `docs/adr/0008-managed-runtime.md` and `docs/adr/README.md`
  (depends on 1): set `Status: Accepted (<date>)` with the slice-to-PR list,
  apply the drift corrections, and set the README row to Accepted.
  DoD: every name in the ADR exists in code or is explicitly marked as not
  implemented.
- [ ] 8. Change the doc tests (depends on 2-7). See Tests. Run
  `go test ./docs/...` green.
  DoD: the PR description lists each test with the mutation that makes it
  fail, and the result of running that mutation locally.

## Tests

- [ ] T1. `TestCredentialBoundary_DocumentsAgree` (`docs/agent_job_api_test.go`),
  inverted: the four documents name `aud=agent`, `agent-pool` and
  `aud=agent-job`, and none of them says the managed runtime is "planned, not
  implemented". Mutation: restore the old T4 row in `spec.md`, and the test
  fails.
- [ ] T2. `TestAgentWorkerEnvTableComplete` (new): every env name read by
  `cmd/agent-worker/main.go` in poll mode, except `AGENT_JOB_*`, is a table
  cell in `agent-worker.md`. The test fails if it finds fewer than 15 names.
  Mutation: delete the `AGENT_POOL_MODE` row.
- [ ] T3. `TestRunbookManagedConfigComplete` (new): every `MANAGED_*` literal in
  `internal/config/config.go` appears in `runbook.md`. Mutation: delete the
  `MANAGED_RUNTIME_MAX_ACCOUNTS` row.
- [ ] T4. `TestRunbookAnchorsPresent`: add the three `mctlagentmanaged*`
  anchors. Mutation: remove `id="mctlagentmanagedpoolworkerdown"`.
- [ ] T5. `TestRunbookManagedRollbackOrder` (new): the rollback steps appear in
  ADR order. Mutation: swap "revoke" and "scale 0".
- [ ] T6. `TestSpecConsentTextMatchesCode` (new): `spec.md` contains
  `managed-data-flow/v1` and the exact consent sentence from the code
  constant. Mutation: change one word in the doc's sentence.
- [ ] T7. Existing `TestRunbookMetricNamesRegistered` stays green. This guards
  against naming `mctl_agent_openai_requests_total` in the runbook.

## Rollback

Docs and tests only. Revert the merge commit (`git revert -m 1 <merge>`). That
restores the "planned" wording together with the old version of
`TestCredentialBoundary_DocumentsAgree`, so CI stays consistent. No deployed
component, config or data is affected. The gitops alert `runbook_url`s would
point at missing anchors again, which is how things are today.
