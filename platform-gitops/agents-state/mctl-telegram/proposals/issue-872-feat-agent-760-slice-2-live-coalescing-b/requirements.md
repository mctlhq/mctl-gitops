# #760 slice 2: live turn coalescing, bounded agent-worker pool, routing of unclaimed jobs

## Context

Slice 1 (#858, PR #862) added the pure `ConversationTurn v1` coalescer
(`internal/agent/turn`), bound job tokens to their conversation, and added operator
routing behind `EVENTS_OPERATOR_ROUTING`. Nothing in production imports the coalescer
yet (`internal/agent/turn/turn.go` says so in its package comment). The live path still
creates one `agent_jobs` row per incoming message, and one `claude -p` invocation runs
per row. `agent-worker` handles one job at a time (`internal/agentworker/worker.go`
`Loop` polls with `limit=1`). When no worker claims a job, the job stays `pending`
forever and is never routed to the operator. The `EventsOperatorRouting` comment in
`internal/config/config.go` documents this as a known gap.

This slice does three things. It makes a burst of messages in one conversation become
one job (one turn). It lets one worker process run up to `AGENT_WORKER_CONCURRENCY` jobs
at once, still never more than one per conversation. With operator routing on, it
forwards a never-claimed job to the operator once, after `AGENT_UNCLAIMED_ROUTE_AFTER`,
with `routing_reason=worker_unclaimed`. The owner's decisions on mctlhq/mctl-agents#760
still bind:
- no double handling;
- cold `claude -p` plus database context, with no per-chat `--resume`;
- job tokens bound to their conversation;
- `session_key = telegram:<users.id>:<peer_tg_id>`;
- an oversized event forms its own turn;
- `turn_id` is derived deterministically from the first event;
- first reason wins per `event_id`.

## User stories

- AS an account owner I WANT a burst of messages from one contact answered as one turn
  SO THAT the agent replies once, with the full context, and not once per fragment.
- AS an operator I WANT one worker process to handle several conversations at once
  SO THAT one slow conversation does not delay every other chat.
- AS an operator with operator routing on I WANT messages that no worker picked up to
  reach my operator stream SO THAT a stopped worker does not leave contacts unanswered
  without anyone knowing.
- AS a platform maintainer I WANT every new behaviour to default to today's behaviour
  SO THAT this release changes nothing until config turns it on.

## Acceptance criteria (EARS)

### Coalescing (task 1)

- WHILE turn coalescing is disabled (`AGENT_TURN_QUIET` unset or `0`) THE SYSTEM SHALL
  claim and deliver one job per incoming event, exactly as today.
- WHEN coalescing is enabled and a worker claims the oldest pending job of a
  conversation THE SYSTEM SHALL run the slice-1 `turn.Coalescer` over that job and the
  conversation's never-claimed pending jobs, in arrival (`id`) order. The events use
  `At` = the job's `created_at`, `Bytes` = the job's `body_bytes`, and
  `SessionKey = turn.SessionKey(users.id, chat_tg_id)`.
- WHILE the head job's turn is still COLLECTING at claim time (its quiet window and
  maximum wait have not passed) THE SYSTEM SHALL NOT claim that job. Other
  conversations' ready jobs stay claimable.
- WHEN the head job's turn is READY THE SYSTEM SHALL, in one transaction:
  - claim the head job;
  - stamp `turn_id` on it;
  - move every other member job of the turn to status `coalesced`, with
    `coalesced_into = <head id>` and the same `turn_id`.

  The claim response SHALL carry `turn_id` and `source_event_ids` (all member event ids,
  in arrival order).
- WHEN N messages of one conversation arrive inside the quiet window and within
  `MaxMsgs`/`MaxBytes` THE SYSTEM SHALL produce exactly one claimed job whose
  `source_event_ids` lists all N.
- IF a single event's `body_bytes` reaches `AGENT_TURN_MAX_BYTES` THEN THE SYSTEM SHALL
  close the open window. The oversized event forms its own turn, and a following event
  opens a new turn.
- WHEN the same events are coalesced again (a retried claim of the same head, or the same
  rows replayed into a fresh store) THE SYSTEM SHALL produce the same `turn_id`. On a
  retried claim it SHALL also produce the same membership. Membership is frozen when the
  head is first claimed.
- WHEN a job-bound credential calls `GET /event/{eventID}` THE SYSTEM SHALL allow any
  event in that job's `source_event_ids` and deny every other event, as today.
- WHEN a coalesced head job is routed to the operator for any reason THE SYSTEM SHALL
  forward every source event of the turn. First reason wins per `event_id`.

### Bounded concurrency (task 2)

- WHILE `AGENT_WORKER_CONCURRENCY` is unset THE SYSTEM SHALL run at most one job at a
  time (default `1`).
- WHEN `AGENT_WORKER_CONCURRENCY=N` (1..10) THE SYSTEM SHALL run up to N jobs at once.
  It SHALL claim only as many jobs as it has free slots, so no claimed job waits for a
  slot while its visibility deadline runs.
- IF `AGENT_WORKER_CONCURRENCY` is not an integer in 1..10 THEN THE SYSTEM SHALL refuse
  to start, with a clear error.
- WHILE any number of workers or slots is running THE SYSTEM SHALL never run two jobs of
  the same conversation at once. The `ClaimAgentJobs` `NOT EXISTS` rule is kept
  unchanged.
- WHEN the worker shuts down (ctx cancelled) THE SYSTEM SHALL stop claiming and wait for
  in-flight jobs to finish or hit their deadlines before `Loop` returns.

### Routing unclaimed jobs (task 3)

- WHILE `EVENTS_OPERATOR_ROUTING` is on THE SYSTEM SHALL, on every agent-jobs sweep, do
  the following for each job that is `pending`, was never claimed (`attempts = 0`) and
  has `created_at` older than `AGENT_UNCLAIMED_ROUTE_AFTER` (default 5m). In one
  transaction it SHALL move the job to terminal status `routed` and forward its source
  event to the operator stream with `routing_reason=worker_unclaimed`.
- IF a job was claimed before the threshold THEN THE SYSTEM SHALL NOT route it as
  unclaimed. This holds even if the job is pending again after a retry or a stale
  requeue.
- IF the job's event was already routed for another reason THEN THE SYSTEM SHALL NOT
  write a second outbox row. The existing `event_outbox` row keeps its first reason. The
  job still leaves `pending` so that no worker handles it later.
- WHEN two sweeps or a sweep and a claim race for the same job THE SYSTEM SHALL let only
  one of them move it out of `pending`. A job is never both routed and claimed.
- WHILE `EVENTS_OPERATOR_ROUTING` is off THE SYSTEM SHALL NOT run the unclaimed sweep. A
  pending job stays pending, as today.
- IF `AGENT_UNCLAIMED_ROUTE_AFTER` is not greater than `AGENT_TURN_MAX_WAIT` (when
  coalescing is enabled) THEN THE SYSTEM SHALL refuse to start.

## Out of scope

- Per-chat `claude --resume` or any session persistence across turns.
- Any change to mctl-claude-remote. If consuming `worker_unclaimed` needs one, it is
  filed in that repository.
- Any production or preview config change. Enabling the new settings on preview is a
  separate mctl-gitops PR.
- Changing the `ClaimAgentJobs` per-conversation serialization rule, or the `?limit=`
  cap of 10.
- Re-routing or re-coalescing jobs created before this release beyond what the
  migration-tolerant defaults give (`body_bytes` NULL is treated as 0).

## Open questions

- Coalescing defaults. Slice 1 added no config, so env names and defaults are proposed
  here: `AGENT_TURN_QUIET` (default `0` = off), `AGENT_TURN_MAX_WAIT` (15s),
  `AGENT_TURN_MAX_MSGS` (10), `AGENT_TURN_MAX_BYTES` (16384). The recommended preview
  values are quiet 3s and max wait 15s. The owner may prefer coalescing on by default.
- A job already routed for another reason, then retried back to `pending` and left
  unclaimed: this proposal still moves it to `routed` (with no new outbox row) so that
  no late worker handles it after the operator. The alternative is to leave such jobs
  pending.
- A new terminal status `routed` and a membership status `coalesced` are added to
  `agent_jobs.status`. They appear as new label values in `CountAgentJobs` and
  `mctl_agent_jobs_total`. Dashboards that list statuses explicitly may need updating.
- The `worker_unclaimed` reason is new to downstream consumers. Whether
  mctl-claude-remote handles an unknown `routing_reason` cleanly was not verified here.
