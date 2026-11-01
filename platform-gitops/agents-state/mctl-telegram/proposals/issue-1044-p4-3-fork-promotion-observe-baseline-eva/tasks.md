# Tasks: issue-1044-p4-3-fork-promotion-observe-baseline-eva

S1 (`internal/agenteval`) is already merged. Tasks 1-8 are slice S2 (one PR),
tasks 9-16 are slice S3 (a second PR), per `docs/assistants/adr-forks.md`.

## S2: eval runs

- [ ] 1. Add `AssistantForkEvalEnabled` (`ASSISTANT_FORK_EVAL_ENABLED`,
  default false) to `internal/config/config.go`. Wire it in
  `cmd/server/main.go`. — DoD: the flag is parsed, logged at startup, and
  has a config test.
- [ ] 2. Add the `assistant_fork_eval_runs` and `assistant_fork_eval_tasks`
  tables to `agentSchemaSQLite`/`agentSchemaPG` in
  `internal/db/agent_schema.go`, with indexes. Purge them in
  `purgeAgentData`. Cancel open runs in `DeleteAssistantFork`. — DoD: the
  migration test passes on both engines, and `agent_purge_test.go` covers
  the new tables.
- [ ] 3. (depends on 2) Add `internal/db/assistant_fork_evals.go` with
  `CreateForkEvalRun` (all limits enforced in the transaction under
  `beginForkTx`), `ClaimForkEvalTask`, `FinishForkEvalTask`,
  `LatestScoredForkEvalRun` and `ExpireForkEvalRuns`. Register the
  24 h expiry in `internal/sweeper`. — DoD: every limit refuses with a typed
  error and writes nothing. Expired, incomplete and cancelled runs are never
  "scored".
- [ ] 4. Add the `agent-eval` audience to `internal/auth/localjwt` with
  claims `EvalRunID` and `EvalTaskAttempt`, and `selectAgentEvalProvider`
  in `cmd/server/main.go`. — DoD: an `agent-eval` token is refused on every
  existing `/api/agent/v1` route, and `agent`/`agent-job` tokens are refused
  on eval routes.
- [ ] 5. (depends on 3, 4) Add `internal/agentapi/eval.go`:
  `POST /api/agent/v1/eval/claim`, which yields 204 while real jobs are
  claimable or the flag is off, renders via `lookupFork` and
  `agenteval.Prepare`, and mints a task-bound `agent-eval` token. Serve the
  task routes through `agenteval.NewTask`. Score with `agenteval.Score` on
  the last fixture. Retry an infrastructure failure once, and only before
  any tool call. — DoD: the server-computed verdict is stored, the worker's
  body never sets the verdict, and only per-fixture metadata is stored.
- [ ] 6. (depends on 5) In `internal/agentworker/worker.go`, poll
  `eval/claim` only after an empty real claim, and run the task through the
  existing invoker. — DoD: a worker test shows real jobs always take
  priority.
- [ ] 7. (depends on 3) Add `internal/web/manage_forks.go`: a fork list
  section on the manage page and `POST /telegram/connect/manage/fork/eval`,
  restricted to `isBrowserSignIn`. Refuse `ErrNoSuite`/`ErrNothingToPromote`
  before writing anything. Send owner notices and audit entries (fork ref
  and run id, no text). — DoD: an MCP `account:manage` token is refused, and
  each limit's refusal text is shown.
- [ ] 8. (depends on 1-7) Enable `ASSISTANT_FORKS_ENABLED` and
  `ASSISTANT_FORK_EVAL_ENABLED` on preview through a separate gitops PR, and
  do one real run of an `hr-recruiter` fork. — DoD: a stored `passed` or
  `failed` run with a complete report, and no text in the DB.

## S3: promotion and revocation

- [ ] 9. Add `AssistantForkGuardedEnabled`
  (`ASSISTANT_FORK_GUARDED_ENABLED`, default false). — DoD: the flag is
  wired and logged.
- [ ] 10. Stamp `auth_time` in `ExchangeConnect`
  (`internal/oauth/server.go`) on the code and the access token. Copy it on
  renewal. Expose it as `auth.Identity.AuthTime`. — DoD: a token minted
  after a sign-in carries it, and a token without it fails the freshness
  helper.
- [ ] 11. Add columns `promoted_at`, `promoted_eval_run_id`, `revoked_at`
  and `written_by_client` to `assistant_forks` via `addColumnIfMissing`.
  Add the `assistant_fork_promotion_events` table (purged). Fill
  `written_by_client` in `storeFork` from the MCP client id. — DoD:
  migrations are idempotent on both engines, and existing rows read as
  `observe`.
- [ ] 12. (depends on 3, 11) Add `PromoteAssistantFork`,
  `RevokeAssistantFork` and `ForkPromoted` in
  `internal/db/assistant_forks.go`. Each mutation runs in one transaction
  under `beginForkTx`. Re-check the latest scored run is `passed`,
  `agenteval.RunBinding.Check`, base `published`, both flags, and the
  optional mode switch under `expected_revision`. — DoD: any mismatch
  returns a typed error with zero rows changed.
- [ ] 13. Add `assistant.AuthorityDiff(base, fork)` in
  `internal/assistant/fork.go`. — DoD: it covers tools, intents and tiers,
  userOverride, limits and ceilings, disclosure and variable disclosure.
  Unit tests cover each field. Its output never includes instructions.
- [ ] 14. (depends on 10, 12, 13) Add the promote and revoke pages to
  `internal/web/manage_forks.go`, mounted in `cmd/server/main.go` with
  `Cache-Control: no-store`. Promote requires browser sign-in,
  `account:manage`, `AuthTime` within 15 minutes, the acknowledgement and
  the typed slug. Revoke requires only `account:manage`. Add events, audit
  and bot notices. — DoD: the page shows every element listed in the
  requirements.
- [ ] 15. (depends on 12) Make the four refusals conditional on
  `ForkPromoted && ASSISTANT_FORK_GUARDED_ENABLED`, where a lookup error
  reads as false:
  - `checkForkInstall`, including pin moves while guarded;
  - the claim at `internal/agentapi/events.go:110`;
  - `policy.Input.ForkPromoted` at `internal/agentapi/actions.go:281,718`;
  - `internal/agent/executor/executor.go:384,752`.

  Update the `ForkPromoted` comment in `policy.go` and
  `MsgForkObserveOnly`. — DoD: all four sites share one helper.
- [ ] 16. Update `docs/assistants/spec.md` and mark S2/S3 done in
  `docs/assistants/adr-forks.md`. — DoD: the docs describe both flags, the
  limits, the promote and revoke surfaces, and the absence of an MCP tool.

## Tests

- [ ] T1. Promotion is refused with no eval run, with a `failed` latest run,
  with an `expired`/`incomplete`/`cancelled` run, and when a passed run is
  followed by nothing newer but the base became `deprecated`.
- [ ] T2. Promotion is refused when the submitted run is bound to a different
  fork digest, base digest, suite digest, harness version or account. Each
  case is a table row, and nothing changes in the DB.
- [ ] T3. With a passing run and a fresh browser sign-in, promotion succeeds.
  The install switched to guarded claims jobs, and `policy.Evaluate` gets
  `ForkPromoted=true` and auto-sends an `auto`-tier reply.
- [ ] T4. `update_fork` (patch and minor) creates a version with
  `promotion=observe`. Installing it in guarded is refused, and moving the
  guarded pin to it is refused without lowering the mode.
- [ ] T5. Revocation sets `revoked` and drops a guarded install to observe
  atomically. An auto-send queued before revocation is held at send time.
- [ ] T6. With `ASSISTANT_FORK_GUARDED_ENABLED` off, a promoted fork behaves as
  observe at the claim, the policy and send time, and promotion is refused.
- [ ] T7. `auth_time` absent or older than 15 minutes refuses promotion. An
  MCP-client `account:manage` token is refused on both the eval-start and
  promote routes, and accepted on revoke.
- [ ] T8. Eval limits: a second open run, a 4th run in 24 h, a 21st global
  run, a third scored run, and a second run after a pass are all refused with
  no write.
- [ ] T9. Audience separation: an `agent-eval` token gets 401/403 on every
  `/api/agent/v1` real route, and `agent`/`agent-job` tokens get 401/403 on
  eval task routes. A worker-reported verdict field is ignored.
- [ ] T10. Persistence hygiene: after a run whose fake model output echoes the
  instructions, no stored eval row, event, audit entry or log line contains
  that text (the redaction handler is extended if new fields are logged).
- [ ] T11. Purge: account deletion removes eval runs, tasks and promotion
  events, and fork deletion cancels open runs.
- [ ] T12. There is no fixed "N approved drafts" rule: a fork with many
  approved observe drafts and no eval cannot be promoted.

## Rollback

- Set `ASSISTANT_FORK_GUARDED_ENABLED=false`. Every fork's effective mode
  returns to observe immediately, including at send time, with no redeploy
  of code. Set `ASSISTANT_FORK_EVAL_ENABLED=false` to stop new eval runs and
  eval claims. `ASSISTANT_FORKS_ENABLED=false` stops all fork jobs.
- To revert code, revert the S3 PR, then the S2 PR. The schema changes are
  additive, so the new tables and columns can stay in place harmlessly. An
  older binary ignores them and never reads `promotion` values other than
  `observe` as permission, because the P4.2 code refuses guarded for every
  fork unconditionally.
