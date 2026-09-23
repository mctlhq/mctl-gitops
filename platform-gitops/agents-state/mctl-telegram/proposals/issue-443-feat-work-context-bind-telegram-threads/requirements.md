# Bind Telegram threads to a canonical WorkItem and a resume path

## Context

Today `mctl-telegram` owns investigation state locally. An incoming Telegram
message becomes an `incoming_events` row, which enqueues an `agent_jobs` row,
which a worker claims over `/api/agent/v1` (`internal/agentapi/server.go`) and
completes with an `agent_actions` or `job_leads` result. The owner drives that
state from Saved Messages with `/mctl ...` commands parsed in
`internal/agent/control/command.go` and routed in
`internal/agent/control/router.go`. All of it — conversation identity, job
lifecycle, approval codes — lives in this service's database
(`internal/db/agent_schema.go`) and is reachable only from Telegram. Work
started in a Telegram thread cannot be inspected, resumed, or approved from any
other mctl surface.

Issue #443 asks us to invert that relationship for the investigator pilot:
Telegram becomes a *surface adapter* over canonical mctl work state rather than
the owner of it. A Telegram interaction should create or open a canonical
WorkItem in the platform (mctl-api#227), start an investigator execution
against it (mctl-agents#267), keep only a minimal correlation record locally,
and expose a stable reference so the same work can be resumed from a second
surface without replaying Telegram history. The service already has the right
instinct for this: `internal/events` publishes reference-only `mctl.events/v1`
envelopes that name a chat and message but never carry the body, on the stated
principle that "an event is a signal, not a copy". This proposal applies the
same principle to work state.

## User stories

- AS a platform owner operating from Telegram I WANT `/mctl work <request>` to
  create or open a canonical WorkItem SO THAT my investigation is tracked in
  platform state rather than only in a chat thread.
- AS a platform owner I WANT the bot to reply with a stable work and execution
  reference SO THAT I can paste it into another surface and continue there.
- AS a platform owner I WANT a repeated `/mctl work` in the same thread to
  reopen the same WorkItem SO THAT a retried or double-tapped command never
  forks my work into duplicates.
- AS an operator on a second surface (MCP client or web) I WANT to inspect and
  resume work that started in Telegram through the canonical API SO THAT I do
  not need access to the Telegram transcript.
- AS a security reviewer I WANT authorization and approval decisions to come
  from platform contracts SO THAT being able to message the bot never by itself
  grants the ability to start or approve platform work.
- AS an operator of an existing deployment I WANT every current `/mctl` command,
  the communication-agent job pipeline, and the MCP tool surface to behave
  exactly as before when the feature flag is off SO THAT rollout carries no
  regression risk.

## Acceptance criteria (EARS)

Creation and binding

- WHEN an authorized owner sends `/mctl work <request>` in a Telegram context
  that has no existing binding THE SYSTEM SHALL call the canonical WorkItem API
  to create or open a WorkItem, persist a `work_item_bindings` row correlating
  the Telegram context to the returned WorkItem id, and reply with the work
  reference.
- WHEN the system persists a binding THE SYSTEM SHALL store only correlation
  identifiers — `user_id`, surface, `chat_tg_id`, `thread_id`, `root_message_id`,
  work/execution/snapshot ids, timestamps — and SHALL NOT store the request
  text, the reply text, or any other message body.
- WHEN the system calls the canonical WorkItem API THE SYSTEM SHALL include
  actor identity (`auth.Identity.Subject`, e.g. `tg:<telegram_id>`), surface
  (`telegram`), the surface reference, and a deterministic idempotency key
  derived from `(user_id, chat_tg_id, thread_id)`.
- WHEN a WorkItem is created or opened from Telegram THE SYSTEM SHALL start an
  investigator execution bound to that WorkItem and SHALL record the returned
  execution id and ContextSnapshot reference on the binding row.

Idempotency

- WHEN `/mctl work` is sent again in a Telegram context that already has a
  binding in a non-terminal state THE SYSTEM SHALL reuse the bound WorkItem,
  SHALL NOT create a second WorkItem, and SHALL reply with the existing work
  reference and current state.
- IF two `/mctl work` commands for the same Telegram context are processed
  concurrently THEN THE SYSTEM SHALL let the unique index on
  `(user_id, surface, chat_tg_id, thread_id)` arbitrate, re-read the winning
  row, and have both commands report the same WorkItem id.
- WHILE a binding exists THE SYSTEM SHALL send the same idempotency key on every
  create-or-open call for that Telegram context so that a locally lost binding
  row cannot cause the platform to mint a duplicate WorkItem.

Authorization and approval

- IF the caller is not authorized for work-context operations by platform
  contract THEN THE SYSTEM SHALL refuse the command with a non-disclosing
  message and SHALL NOT call the WorkItem API on their behalf.
- WHILE handling a work-context command THE SYSTEM SHALL treat Telegram
  reachability (`client_bot_reachability`, `internal/db/reachability.go`) and
  chat membership as routing facts only, never as an authorization input.
- IF the canonical API answers 401 or 403 THEN THE SYSTEM SHALL surface that
  refusal to the user unchanged and SHALL NOT fall back to any bot-local grant.
- WHEN the bound work is in a pending-approval state THE SYSTEM SHALL render
  that state read-only from the canonical API and SHALL NOT create an
  `agent_actions` approval code, a local approval record, or any bot-local
  approve/reject path for it.

Resume and second surface

- WHEN a work reference is reported to the user THE SYSTEM SHALL render a
  stable, copyable form containing the WorkItem id and the current execution id.
- WHEN an authorized identity requests work context for a bound Telegram thread
  from a second surface THE SYSTEM SHALL return the WorkItem, execution and
  ContextSnapshot references and SHALL NOT return Telegram message content.
- WHEN a later Telegram interaction targets a bound WorkItem THE SYSTEM SHALL
  continue it through the canonical resume path, producing a new execution
  against the same WorkItem rather than a new WorkItem.
- WHEN a binding is created or its bound execution changes THE SYSTEM SHALL
  enqueue a reference-only envelope through the existing transactional outbox
  (`internal/db/event_outbox.go`, `internal/events/relay.go`) whose subject
  carries identifiers only.

Rollout and degradation

- WHILE `WORK_CONTEXT_ENABLED` is false THE SYSTEM SHALL behave exactly as it
  does today: no new command is accepted, no outbound call is made, no binding
  row is written, and every existing `/mctl` subcommand, agent job path and MCP
  tool is unchanged.
- IF the canonical WorkItem API is unreachable, returns 5xx, or exceeds its
  timeout THEN THE SYSTEM SHALL reply that work tracking is temporarily
  unavailable, SHALL NOT write a binding row claiming work that may not exist,
  and SHALL leave all pre-existing Telegram functionality working.
- WHEN a user record is deleted THE SYSTEM SHALL delete that user's
  `work_item_bindings` rows through the same `ON DELETE CASCADE` and purge path
  the other per-user agent tables use.

## Out of scope

- Full chat synchronization between Telegram and other surfaces.
- Making `mctl-telegram` the WorkItem database, or mirroring WorkItem fields
  (title, body, status history) into local tables beyond the correlation row.
- Persisting or replaying Telegram transcripts as canonical task state; message
  bodies stay sealed in `incoming_events` under the existing per-user AES-GCM
  key and are never forwarded as work state.
- Generic cross-product CRM or session storage.
- Migrating the existing communication-agent pipeline (`agent_jobs`,
  `agent_actions`, `job_leads`, the `/mctl approve|reject` flow) onto WorkItems.
  That pipeline is untouched by this proposal; only the new investigator path is
  WorkItem-backed.
- Implementing the canonical WorkItem API itself (mctl-api#227) or the
  investigator execution/ContextSnapshot contract (mctl-agents#267).
- Building the second surface. This proposal ships the read path the second
  surface consumes and an end-to-end test against a contract fake.

## Open questions

- The exact canonical contract from mctl-api#227 is not visible from this repo:
  route paths, request and response field names, the idempotency mechanism
  (request field versus `Idempotency-Key` header), and how a ContextSnapshot is
  referenced. Proceeding with a narrow port interface (`workitem.Client`) plus a
  contract fake so only one adapter file changes when the real shape lands.
- Service-to-service credential for the outbound call. This repo has no
  outbound client to `mctl-api` today; it only verifies inbound JWTs
  (`internal/auth/sharedhmac`). Proceeding with a dedicated
  `WORK_CONTEXT_API_TOKEN` sourced from Vault, on the assumption that reusing
  `OAUTH_JWT_SECRET` to mint outbound tokens would re-entrench the shared-HMAC
  coupling ROADMAP M3 is trying to remove.
- "Thread" has no representation in this codebase at all. There is no
  `message_thread_id`, `TopMsgID` or `reply_to_msg_id` anywhere:
  `telegram.Message` has no thread field, `bot.Update` decodes only
  `update_id` and `chat.id`, and `conversations` is keyed
  `UNIQUE (user_id, peer_tg_id)` — per peer, not per thread. Proceeding with a
  nullable `thread_id` column that is written as NULL in this slice, so the
  binding is chat-scoped today and the column can be populated later without a
  schema or index change on a table that by then holds production rows. This
  should be confirmed against what mctl-api#227 expects in a surface reference.
- Which second surface lands first (MCP tool versus web). Proceeding with a
  flag-gated MCP tool, because ROADMAP declares the seven MCP tools locked for
  v1.0 and a flag-gated eighth is the smallest reversible step.
- Whether the ContextSnapshot is produced by the execution and merely referenced
  by us, or must be requested. Proceeding with reference-only: we store an
  opaque snapshot id returned by the platform and never construct one.
- Whether authorization is decided solely by mctl-api or additionally gated by a
  local operator allowlist. Proceeding with both: a local `WORK_CONTEXT_OPERATORS`
  allowlist as a deployment-side restriction, with mctl-api remaining the
  authoritative decision. The local list can only narrow, never widen.
