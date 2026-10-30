# Tasks: issue-872-feat-agent-760-slice-2-live-coalescing-b

- [ ] 1. Schema and statuses: add `turn_id`, `coalesced_into` and `body_bytes` to
  `agent_jobs` through `addColumnIfMissing` in `internal/db/agent_schema.go`, plus the
  partial index `idx_agent_jobs_coalesced_into`. Add `JobCoalesced` and `JobRouted` in
  `internal/db/agent_jobs.go`. Extend `AgentJob` and `scanAgentJobs` with `TurnID`,
  `CoalescedInto` and `SourceEventIDs`.
  — DoD: migration tests pass on SQLite and Postgres, and re-running the migration is a
  no-op.
- [ ] 2. Write `body_bytes = len(ev.Body)` in `InsertEventEnqueueJobAndTouch` and
  `InsertEventAndEnqueueJob` (depends on 1).
  — DoD: an ingest test asserts the stored size, and the body stays sealed.
- [ ] 3. Config: add `AgentTurnQuiet`, `AgentTurnMaxWait`, `AgentTurnMaxMsgs`,
  `AgentTurnMaxBytes` and `AgentUnclaimedRouteAfter` to `internal/config/config.go`,
  with the defaults 0, 15s, 10, 16384 and 5m. Add the validation rules: when
  coalescing is on, all limits must be > 0 and `UnclaimedRouteAfter` must be greater
  than `MaxWait`; when routing is on, `UnclaimedRouteAfter` must be > 0. Rewrite the
  `EventsOperatorRouting` comment to remove the "Known gap".
  — DoD: config tests cover the defaults, the overrides and each rejection.
- [ ] 4. Coalescing claim: add `Store.WithTurnCoalescing(turn.Config)` and the
  `Store.now` hook. Implement the coalescing branch of `ClaimAgentJobs` as described in
  design.md: candidate scan cap, per-head `turn.Coalescer`, the readiness gate, the head
  claim with `turn_id`, members moved to `coalesced`, and frozen membership on a retry.
  The coalescing-off path keeps the current SQL unchanged. Have `GetAgentJob` fill
  `SourceEventIDs`. Wire it from `cmd/server/main.go` (depends on 1, 2, 3).
  — DoD: T1.1–T1.6 pass, and the existing `agent_jobs_test.go` and
  `agent_admission_sim_test.go` pass unchanged.
- [ ] 5. Route the whole turn: make `routeJobEventTx` in `internal/db/event_outbox.go`
  forward the head and every `coalesced_into` member (depends on 4).
  — DoD: T1.7 passes, and `operator_routing_test.go` passes unchanged.
- [ ] 6. API: add `turn_id` and `source_event_ids` to `jobEnvelope`. Make
  `handleGetEvent`'s job binding accept any event in the turn
  (`internal/agentapi/events.go`) (depends on 4).
  — DoD: T1.8 passes, and the existing binding-denial tests still pass.
- [ ] 7. Worker turn support: add the fields to `JobEnvelope` and `JobContext`, pass
  `AGENT_JOB_SOURCE_EVENT_IDS` in `ClaudeInvoker`, and make `get_event` return every turn
  event while keeping the single-event fields (`internal/agentworker`,
  `cmd/agent-worker/main.go` `runMCPServe`) (depends on 6).
  — DoD: T1.9 passes.
- [ ] 8. Bounded pool: add `Worker.WithConcurrency(n)`, a slot-based `Loop` that polls
  for exactly its free slots, a graceful drain on cancel, and the in-flight conversation
  guard. Add `envInt` and `AGENT_WORKER_CONCURRENCY` (1..10, default 1) in
  `cmd/agent-worker/main.go`. Update the `Loop` doc comment.
  — DoD: T2.1–T2.5 pass under `go test -race`.
- [ ] 9. Unclaimed routing: add `RouteWorkerUnclaimed` and accept it in
  `events.BuildRoutedEnvelope`. Add `Store.RouteUnclaimedAgentJobs` and
  `queue.Queue.RouteUnclaimed` (metrics). Give `sweeper.AgentJobs` an `unclaimedAfter`
  argument, wired from `cmd/server/main.go` (depends on 1, 3).
  — DoD: T3.1–T3.6 pass.
- [ ] 10. Docs: in `docs/agent-worker.md`, document `AGENT_WORKER_CONCURRENCY`, the
  turn envelope fields and the rollout order (worker before server coalescing). In the
  runbook, document the `AGENT_TURN_*` and `AGENT_UNCLAIMED_ROUTE_AFTER` settings and
  the new `coalesced` and `routed` status labels.
  — DoD: docs merged in the same PR, and `docs/runbook_test.go` passes.

## Tests

Coalescing (`internal/db/agent_turn_claim_test.go`; `internal/agentapi` and
`internal/agentworker` for T1.8–T1.9):
- [ ] T1.1. Ingest N=4 events of one conversation within `AGENT_TURN_QUIET`. With `now`
  before the window closes, no job is claimed. After it closes, exactly one job is
  claimed. Its `SourceEventIDs` holds all 4 event ids in order, and the other 3 rows
  are `coalesced`, with `coalesced_into` set to the head.
- [ ] T1.2. Oversized event: a small event, then an event with
  `body_bytes >= MaxBytes`, then a small event. Three turns result. The oversized
  event's turn has one event and closes the first window.
- [ ] T1.3. Replay: ingest the same synthetic events (same ids and timestamps) into two
  fresh stores and claim. The `turn_id` values are equal and match
  `turn.Coalescer.Offer` run directly. Retry the head (`RetryAgentJob`), then claim
  again: same `turn_id`, same membership.
- [ ] T1.4. A conversation still collecting does not block a different conversation's
  ready head at `limit=1`.
- [ ] T1.5. With coalescing off, behaviour is byte-identical to today: one job per
  event, and no `turn_id` or `coalesced` rows.
- [ ] T1.6. `MaxMsgs` closes the turn. Events past the cap form the next turn, which is
  claimable only after the first job completes (the `NOT EXISTS` rule).
- [ ] T1.7. A coalesced head that fails, with operator routing on, writes one
  `worker_failure` outbox row per source event. An event already routed keeps its first
  reason.
- [ ] T1.8. A job-bound token may `GET /event/{id}` for every member event. A different
  event of the same conversation is denied.
- [ ] T1.9. The MCP `get_event` returns every turn event in order. The single-event job
  keeps the old fields.

Bounded concurrency (`internal/agentworker/worker_test.go`, using a fake poller and
runner; `cmd/agent-worker/main_test.go` for T2.4):
- [ ] T2.1. N=2 with two jobs from different conversations: both runners are observed
  in flight at the same time (barrier).
- [ ] T2.2. Two jobs of the same conversation never overlap at N=1, 2 and 4, against a
  real `db.Store` and `queue` (SQLite) driving the claim. The peak in-flight count per
  conversation is 1.
- [ ] T2.3. The poll limit equals the number of free slots, and no claimed job waits for
  a slot.
- [ ] T2.4. `AGENT_WORKER_CONCURRENCY` is unset (giving 1), `3` (giving 3), and `0`,
  `11` or `abc` (refused).
- [ ] T2.5. Cancel while jobs are in flight: Loop returns only after the runners return.

Unclaimed routing (`internal/db/operator_routing_test.go`, `internal/sweeper`):
- [ ] T3.1. A pending job with `attempts=0` older than the threshold is routed exactly
  once. A second sweep writes nothing, and the job is `routed`. The envelope carries
  `routing_reason=worker_unclaimed`.
- [ ] T3.2. A job claimed before the threshold is not routed. This also holds once it is
  back to `pending` after `RetryAgentJob` or a stale requeue.
- [ ] T3.3. A job whose event was already routed for another reason gets no second
  outbox row and keeps its first reason. The job is no longer claimable.
- [ ] T3.4. Race: the sweep and `ClaimAgentJobs` on the same job. Exactly one of them
  moves it, never both.
- [ ] T3.5. With operator routing off, the sweep is a no-op and the job stays `pending`.
- [ ] T3.6. `BuildRoutedEnvelope` accepts `worker_unclaimed` and still rejects unknown
  reasons.

All fixtures use the existing synthetic personas and ids (Alice, Bob, Carol, Dana).
Run `git grep <id>` before choosing any numeric id.

## Rollback

- Config rollback, no redeploy of code needed:
  - set `AGENT_TURN_QUIET=0` (coalescing off: new claims use the old path, and existing
    `coalesced` rows stay finished);
  - set `AGENT_WORKER_CONCURRENCY=1`;
  - set `EVENTS_OPERATOR_ROUTING=false` (stops the unclaimed sweep along with the rest
    of operator routing).
- Code rollback: revert the merge commit and redeploy. The added columns are nullable
  and the old code ignores them, so no schema rollback is needed. Rows in
  `coalesced`/`routed` are terminal for the old code: the old claim selects only
  `pending`, so they are never re-handled. The old code reports them under unknown
  status labels in `CountAgentJobs`, which is harmless.
- Roll back the worker after the server, or turn coalescing off first. An old worker
  against a coalescing server would see only the head event.
