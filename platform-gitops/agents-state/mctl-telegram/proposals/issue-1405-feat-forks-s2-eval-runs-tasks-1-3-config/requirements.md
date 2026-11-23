# Fork eval runs, S2 tasks 1-3: config flag, schema and DB layer

## Context

Issue #1405 is a slice of #1044 (P4.3 fork promotion, epic #1002) and of its
re-file #1403. The implementer refused the whole #1403 proposal (16 tasks
across slices S2 and S3), so the work is split. This proposal covers only S2
tasks 1-3 of the #1403 proposal, which was refreshed at mctl-telegram
`0ef3857a` (tag 0.142.0): a new off-by-default flag
`ASSISTANT_FORK_EVAL_ENABLED`, two new tables (`assistant_fork_eval_runs`,
`assistant_fork_eval_tasks`) with purge and fork-delete cancellation, and a
store layer that creates, claims, finishes, scores-lookup and expires eval
runs, with every rate limit from `docs/assistants/adr-forks.md` enforced in
the database transaction.

This matters because promotion of a fork to `guarded` (S3) depends on a
server-held eval verdict that cannot be forged and cannot spend unbounded
budget. The storage and the limits must be correct before any route (task 5),
token audience (task 4) or worker (task 6) is built on top. On 2026-11-22
the owner confirmed the S2 eval-claim design: a separate
`POST /api/agent/v1/eval/claim` route that accepts the account `agent` token
(own account's tasks only) and the pool credential (any account's tasks).
This slice records that decision and does not implement it. The store API
below is shaped so the route can serve both callers.

## User stories

- AS the platform operator I WANT an `ASSISTANT_FORK_EVAL_ENABLED` switch
  that is off by default and logged at startup SO THAT later slices can gate
  eval runs and I can see the setting of every replica.
- AS the platform operator I WANT the eval rate limits enforced inside the
  database transaction SO THAT no request path can create a run that exceeds
  them and a refused request writes nothing.
- AS an account owner I WANT my eval runs deleted with my account, and
  cancelled when I delete the fork version they evaluate, SO THAT no eval data
  outlives what it is about.
- AS the later S3 promotion code I WANT `LatestScoredForkEvalRun` to return
  only `passed` or `failed` runs SO THAT an expired, incomplete or cancelled
  run can never back a promotion.

## Acceptance criteria (EARS)

Config (task 1)

- WHEN the server starts THE SYSTEM SHALL parse `ASSISTANT_FORK_EVAL_ENABLED`
  into `config.Config.AssistantForkEvalEnabled` with `envBool`, default
  `false`, and log it at info level next to the existing
  `"assistant forks"` startup line.
- WHILE this slice is deployed THE SYSTEM SHALL NOT read
  `AssistantForkEvalEnabled` anywhere except the startup log line.

Schema (task 2)

- WHEN migrations run on SQLite or Postgres THE SYSTEM SHALL create
  `assistant_fork_eval_runs` and `assistant_fork_eval_tasks` and their
  indexes with `CREATE ... IF NOT EXISTS`, so a second migration run is a
  no-op and existing tables are unchanged.
- WHEN an account is hard-deleted (`purgeAgentData`) THE SYSTEM SHALL delete
  every eval task and eval run of that account.
- WHEN `DeleteAssistantFork` deletes one or more fork versions THE SYSTEM
  SHALL, in the same transaction, set every `queued` or `running` eval run of
  that account for the deleted digests to `cancelled`, with `finished_at`
  set.
- IF `DeleteAssistantFork` refuses (`ErrForkInUse`, `ErrAssistantForkNotFound`)
  THEN THE SYSTEM SHALL leave every eval run unchanged.
- THE SYSTEM SHALL NOT store model output text in either table. The task
  result holds only fixture id, category, action, flags, leak-marker ids and
  cost, encoded by the caller. The store treats it as opaque bytes.

Store (task 3)

- WHEN `CreateForkEvalRun` is called THE SYSTEM SHALL, in one transaction
  under `beginForkTx(userID)`, check that the fork version
  `(user_id, fork_digest)` exists, then check every limit, then insert the run
  in state `queued` and one `pending` task per fixture id.
- IF the account already has a `queued` or `running` run THEN THE SYSTEM
  SHALL refuse with `ErrForkEvalRunOpen` and write nothing.
- IF the account has created 3 runs (any state) in the last 24 h THEN THE
  SYSTEM SHALL refuse with `ErrForkEvalAccountLimit` and write nothing.
- IF 20 runs (any account, any state) were created in the last 24 h THEN THE
  SYSTEM SHALL refuse with `ErrForkEvalGlobalLimit` and write nothing.
- IF the digest already has a `passed` run THEN THE SYSTEM SHALL refuse with
  `ErrForkEvalDigestPassed` and write nothing.
- IF the digest already has 2 scored (`passed` or `failed`) runs THEN THE
  SYSTEM SHALL refuse with `ErrForkEvalDigestLimit` and write nothing.
- IF the fork version does not exist for that account THEN THE SYSTEM SHALL
  refuse with `ErrAssistantForkNotFound` and write nothing.
- IF the input has no fixtures, a duplicate fixture id, or an empty binding
  field THEN THE SYSTEM SHALL refuse it and write nothing.
- WHEN `ClaimForkEvalTask` is called THE SYSTEM SHALL atomically claim the
  oldest claimable task of an open run, optionally filtered to one account,
  set its `deadline`, move the run from `queued` to `running`, and return the
  run binding, task fixture id and attempt. It SHALL return
  `ErrForkEvalNoTask` when nothing is claimable.
- WHEN a claimed task's deadline has passed and its attempt is 1 THE SYSTEM
  SHALL make it claimable again with attempt 2. WHEN a claimed task's deadline
  has passed at attempt 2 THE SYSTEM SHALL set its run to `incomplete`.
- WHEN `FinishForkEvalTask` records the result of the last unfinished task of
  a run THE SYSTEM SHALL, in the same transaction, call the caller-supplied
  scorer over all task results and store the run as `passed` or `failed`
  with its report. The verdict SHALL come from that scorer, never from a
  value in the task result.
- IF `FinishForkEvalTask` names a task that is not claimed at that attempt,
  or a run that is not `running`, THEN THE SYSTEM SHALL refuse with
  `ErrForkEvalTaskStale` and write nothing.
- IF a task finishes as an infrastructure failure THEN THE SYSTEM SHALL set
  the run to `incomplete`.
- WHEN `ExpireForkEvalRuns(now)` runs THE SYSTEM SHALL set every `queued` or
  `running` run created at or before `now - 24h` to `expired`, and return the
  count.
- WHEN `LatestScoredForkEvalRun(userID, digest)` is called THE SYSTEM SHALL
  return the newest run in state `passed` or `failed` for that account and
  digest, or `ErrForkEvalRunNotFound`. Runs in `queued`, `running`,
  `incomplete`, `expired` or `cancelled` SHALL never be returned and SHALL
  never count as scored in `CreateForkEvalRun`.
- WHILE the server runs THE SYSTEM SHALL run a `sweeper.ForkEvals` loop that
  calls `ExpireForkEvalRuns` at boot and every 15 minutes. A failure is logged
  and retried on the next tick.

## Out of scope

- S2 tasks 4-8: the `agent-eval` token audience, the
  `POST /api/agent/v1/eval/claim` route and eval task routes, worker
  polling, the manage-page UI and preview enablement.
- All of S3: promotion, revocation, `assistant_fork_promotion_events`, the
  promotion columns on `assistant_forks`, `ASSISTANT_FORK_GUARDED_ENABLED`,
  and `policy.Input.ForkPromoted` callers.
- Turning `ASSISTANT_FORK_EVAL_ENABLED` on in any gitops values file.
- Any change to `internal/agenteval`. The store does not import it.

## Open questions

- "20 runs per day globally": a rolling 24 h window or a UTC calendar day?
  Assumption: a rolling 24 h window, the same as the per-account limit, so one
  query shape serves both. `beginForkTx` locks one account only, so two
  accounts racing can rarely produce a 21st run. The #1403 design tolerates
  this.
- Scoring is server-side (`agenteval.Score`), but `internal/agenteval`
  already imports `internal/db`, so the store cannot call it directly.
  Assumption: `FinishForkEvalTask` takes a scorer callback that task 5
  supplies (wrapping `agenteval.Score`). The store runs it inside the
  transaction that finishes the last task.
- The ADR allows one infrastructure retry "only before any tool call". The
  store cannot see tool calls before task 5 exists. Assumption: the store
  re-offers a timed-out task once, and `FinishForkEvalTask` with outcome
  `infra_failed` marks the run `incomplete`. Task 5 must call
  `FinishForkEvalTask` with `infra_failed` itself once a task has made a tool
  call, so a timed-out task with effects is never re-offered. A
  `tool_called` column could be added in task 5 if that proves too weak.
- The per-task claim deadline is not fixed by the ADR. Assumption: the caller
  passes it (`ClaimForkEvalTask` takes a lease duration). The tests use 10
  minutes.
- Runtime state was not observed through mctl MCP tools in this run; see
  design.md `Deployed state checked`. It does not affect this slice, which
  changes no deployed configuration.
