# Bind Telegram threads to a canonical mctl-api WorkItem with a resume path

## Context

mctl-telegram today owns its own investigation-shaped state. The communication
agent keeps `conversations`, `incoming_events`, `agent_actions` and
`agent_jobs` rows (`internal/db/agent_schema.go`, `internal/db/agent_domain.go`)
and drives them from `/mctl` commands the owner types into Saved Messages
(`internal/agent/control/command.go`, `internal/agent/control/router.go`).
Nothing in this repository talks *outbound* to mctl-api: the only references to
mctl-api are inbound JWT verification (`internal/auth/sharedhmac/verifier.go`,
`internal/auth/localjwt/issuer.go`). Work that starts in Telegram therefore
cannot be seen, resumed or inspected from any other surface.

Issue #443 asks Telegram to become a *surface adapter* over canonical mctl work
state instead of an owner of it. The pilot is the investigator workflow: an
owner interaction in Telegram creates or opens a canonical WorkItem, records
the user's intent, and exposes stable references (work item id, latest
execution, snapshot pointer) so the same work can be continued from a second
surface without replaying any Telegram history. The binding contract is pinned
in-repo at `docs/contracts/mctl-api-work-context.md` and is non-negotiable:
the bot never supplies an actor, authenticates as the `surface:telegram`
principal, relays the human via `X-MCTL-Surface-Actor`, and never touches
execution, snapshot, approval, list or `PATCH` routes.

## User stories

- AS a Telegram account owner I WANT `/mctl work <title>` to create or open a
  canonical WorkItem SO THAT the work I start on my phone exists in the
  platform rather than only in this bot's database.
- AS a Telegram account owner I WANT `/mctl work status` to show the work item
  id, state and latest execution reference SO THAT I can quote a stable
  identifier when continuing the work elsewhere.
- AS a Telegram account owner I WANT `/mctl work note <text>` to append an
  intent to the bound work item SO THAT the platform investigator has my input
  without the bot mirroring my whole chat transcript.
- AS a Telegram account owner I WANT `/mctl work resume` to ask the platform to
  continue SO THAT I do not need a second tool open to pick a stalled
  investigation back up.
- AS a Telegram account owner I WANT `/mctl link <code>` to bind my Telegram
  identity to my platform identity once SO THAT the platform attributes my work
  to me and not to the bot.
- AS a platform operator I WANT the whole adapter behind a flag that is off by
  default SO THAT rolling it out cannot regress the existing Telegram
  workflows before mctl-api ships the surface principal.
- AS a security reviewer I WANT authorization decided by mctl-api on the
  relayed human SO THAT reachability over Telegram is never mistaken for
  platform authorization.

## Acceptance criteria (EARS)

### Identity and relay

- WHEN the adapter issues any request to mctl-api THE SYSTEM SHALL send
  `Authorization: Bearer <MCTL_SURFACE_TELEGRAM_TOKEN>` and SHALL NOT send
  `MCTL_API_TOKEN` or any `mctl-agent` credential.
- WHEN the adapter issues a request on a relay route THE SYSTEM SHALL send
  `X-MCTL-Surface-Actor` containing only the owner's Telegram user id as
  decimal digits.
- WHILE building any mctl-api request body THE SYSTEM SHALL omit every
  actor-naming field (`actor`, `actor_subject`, `created_by`, `principal`,
  `on_behalf_of`) and SHALL NOT construct a `tg:<id>` subject.
- THE SYSTEM SHALL resolve the Telegram user id for the relay header from the
  authenticated Saved Messages self-peer or the `users` row, and SHALL NOT
  derive it from a deployment allowlist such as `telegram_owner_ids`.
- IF the Telegram user id for the acting account cannot be resolved THEN THE
  SYSTEM SHALL fail closed, make no mctl-api call, and tell the owner the
  account is not linked.
- WHEN the owner sends `/mctl link <code>` THE SYSTEM SHALL call
  `POST /api/v1/surface-identities/redeem` with that code and the relay header,
  and SHALL NOT echo the code back into any reply or log.
- IF mctl-api answers `403 link_not_found`, `link_revoked`, `link_expired` or
  `relay_required` THEN THE SYSTEM SHALL reply with instructions to run the
  one-time link flow and SHALL NOT retry the original call.
- IF mctl-api answers `400 actor_not_accepted` THEN THE SYSTEM SHALL treat it
  as a programming defect: log a non-sensitive error, increment a failure
  metric, and reply that the request was rejected by the platform.

### Route discipline

- THE SYSTEM SHALL call only `POST /api/v1/work-items`,
  `GET /api/v1/work-items/{id}`, `POST /api/v1/work-items/{id}/intents`,
  `POST /api/v1/work-items/{id}/resume`,
  `POST /api/v1/work-items/{id}/surface-refs` and
  `POST /api/v1/surface-identities/redeem`.
- THE SYSTEM SHALL NOT call `GET /api/v1/work-items` (list),
  `PATCH /api/v1/work-items/{id}`, any `/executions`, `/snapshot`,
  `/snapshots`, `/events` or `/approvals` route.
- WHEN the owner asks for execution or approval state THE SYSTEM SHALL read it
  from the `latest_execution`, pending-approval and snapshot pointers returned
  by `GET /api/v1/work-items/{id}` and SHALL NOT evaluate approval logic
  locally.

### Binding and idempotency

- WHEN the owner runs `/mctl work <title>` in a Saved Messages thread that has
  no binding THE SYSTEM SHALL create a work item with
  `origin_surface: telegram` and a deterministic `external_key` derived from
  the Telegram chat id and root message id, then persist a binding row.
- WHEN the owner repeats `/mctl work <title>` for a thread that already has a
  binding whose work item is `active` or `waiting` THE SYSTEM SHALL reuse the
  bound work item and SHALL NOT create a second one.
- WHEN the adapter issues any mutating mctl-api request THE SYSTEM SHALL send
  an `Idempotency-Key` derived deterministically from the binding key and the
  operation, so that a retry after a crash or timeout is a no-op.
- WHILE a binding row exists THE SYSTEM SHALL store only numeric Telegram
  correlation identifiers (chat id, root message id, owning user id) plus the
  work item id, its last observed state and state version, and SHALL NOT store
  message bodies, titles, transcripts or peer handles.
- WHEN a work item is created or opened THE SYSTEM SHALL register the Telegram
  thread with `POST /api/v1/work-items/{id}/surface-refs` as correlation
  metadata only.
- IF a binding's work item has reached `completed`, `superseded` or `archived`
  THEN THE SYSTEM SHALL create a new work item for the next `/mctl work` in
  that thread rather than resuming a terminal one.

### Concurrency and resume

- WHEN the owner runs `/mctl work resume` THE SYSTEM SHALL first
  `GET /api/v1/work-items/{id}` and send the returned `state_version` as
  `expected_state_version` on the resume call.
- IF a resume returns `409` for a state-version mismatch THEN THE SYSTEM SHALL
  re-read the work item and retry at most once, and on a second mismatch SHALL
  tell the owner the item changed and ask them to try again.
- WHEN a response's `schema_version` is not `workitem/v1` THE SYSTEM SHALL
  reject the response, make no state change, and report an incompatible
  platform version.

### Rollout and compatibility

- WHILE `WORK_CONTEXT_ENABLED` is false THE SYSTEM SHALL behave exactly as it
  does today: no mctl-api client constructed, no outbound request, and
  `/mctl work` and `/mctl link` answered by the existing unknown-command reply.
- WHILE `WORK_CONTEXT_ENABLED` is true THE SYSTEM SHALL leave every existing
  `/mctl` subcommand (`status`, `leads`, `conversations`, `show`, `continue`,
  `pause`, `takeover`, `approve`, `reject`) byte-for-byte unchanged in parsing
  and behaviour.
- IF `WORK_CONTEXT_ENABLED` is true but `MCTL_SURFACE_TELEGRAM_TOKEN` is empty
  THEN THE SYSTEM SHALL refuse to start the adapter, log the misconfiguration,
  and leave the rest of the server running.
- THE SYSTEM SHALL register `mctl_surface_telegram_token` in the
  `internal/audit/redact.go` sensitive-key set so the surface bearer can never
  reach a log line.
- WHEN an mctl-api call fails for any reason THE SYSTEM SHALL leave all
  existing communication-agent state untouched and SHALL NOT block or fail the
  Saved Messages listener.

## Out of scope

- The human-input relay routes (`GET /api/v1/human-input`,
  `GET /api/v1/human-input/{request_id}`,
  `POST /api/v1/human-input/{request_id}/response`) — owned by #571.
- Minting surface-identity challenges, or listing and revoking links; the human
  does those with their own GitHub credential, not through the bot.
- Starting, attaching, correlating or sealing executions and context snapshots;
  those are platform-owned and service-principal only.
- Full chat synchronization between Telegram and other surfaces.
- Making Telegram the WorkItem database, or storing private message history for
  later retrieval.
- Forum-topic (`message_thread_id`) support. This repository's Telegram surface
  is an MTProto *user account* (`internal/telegram/clientpool.go`), not a Bot
  API bot in a forum; there is no topic id anywhere in the tree.
- End-to-end acceptance against a live mctl-api; that waits on the release with
  the surface principal token configured.
- Changing the existing `conversations` / `agent_jobs` domain or the C1
  communication-agent rollout gate.

## Open questions

- **Which mctl-api tenant does a Telegram-originated work item belong to?**
  `POST /api/v1/work-items` requires a `tenant`, but "tenant" in this repo means
  the local owning user account (`internal/agent/profile/profile.go`), which is
  not an mctl-api tenant. Proceeding with a single configured
  `MCTL_WORK_ITEM_TENANT`, failing closed when it is unset; a per-link tenant
  derived from the relayed human's tenants would be better once mctl-api
  exposes one.
- **What exactly is a "Telegram thread" for binding purposes?** There is no
  forum topic id in this codebase. Proceeding with the pilot definition: a
  thread is `(user_id, chat_tg_id, root_message_id)` where the root message is
  the `/mctl work` command itself, in Saved Messages. Binding a recruiter
  `conversations` row (`internal/db/agent_domain.go:479`) to a work item is a
  plausible follow-up but is not the investigator pilot.
- **Which second surface will close the cross-surface loop?** The issue leaves
  it as "CLI/MCP or web, whichever becomes available first". Proceeding by
  making the Telegram side surface-agnostic — it only needs the work item id —
  and documenting the manual verification against whichever lands first.
- **Does `POST /work-items` return the created item in the `workitem/v1` item
  view shape, or a bare id?** The pinned contract lists the body but not the
  response. Proceeding by decoding the item view and tolerating a response
  that carries only `work_item.id` and `state_version`.
- **What is the deployed namespace's egress posture for `api.mctl.ai`?** The
  communication-agent plan notes the `labs` namespace is
  `allowInternetEgress: true` namespace-wide. Proceeding on that assumption and
  flagging it for the operator to confirm at rollout.
