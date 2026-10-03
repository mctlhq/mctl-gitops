# Telegram delivery/reply adapter for agent human-input (clarification) requests

## Context

mctl agents (first the DevLoop issue-investigator) can stop with a typed `needs_input` outcome. The platform then records a `HumanInputRequest`, parks the Temporal workflow in `WAITING_FOR_INPUT`, and exposes the pending request through mctl-api (mctlhq/mctl-api#261). Issue #571 asks mctl-telegram to be the first human-input surface. It should deliver a pending request to the linked operator in Telegram as a compact question. It should accept that operator's single-choice or free-text answer and submit it as a canonical `HumanInputResponse` through mctl-api. Then it should show the canonical outcome: answered, rejected, expired or superseded.

The bot must stay a surface adapter. The pinned contract in `docs/contracts/mctl-api-work-context.md` already reserves the human-input relay routes for #571: `GET /api/v1/human-input`, `GET /api/v1/human-input/{request_id}` and `POST /api/v1/human-input/{request_id}/response`. The same contract fixes the identity rules: authenticate as `surface:telegram`, name the human only through `X-MCTL-Surface-Actor`, and never decide authorization locally. This proposal reuses the #443 work-context adapter (`internal/workctx`, `internal/agent/control/work.go`, `work_item_bindings`) and the Saved Messages command and notification channel. That avoids building a second identity, authorization or workflow store inside the bot. A clarification answer must never be usable as an approval.

## User stories

- AS an operator whose Telegram account is linked to my platform identity I WANT to see an agent's clarification question in Telegram SO THAT the agent can continue without me opening another tool.
- AS an operator I WANT to answer a single-choice question with one short command, and a free-text question with a sentence, SO THAT answering from a phone takes seconds.
- AS an operator I WANT the Telegram message to say whether my answer was accepted, rejected, or arrived too late SO THAT I never assume the agent resumed when it did not.
- AS a platform owner I WANT every authorization decision to stay in mctl-api SO THAT Telegram reachability or bot state can never grant authority.
- AS a security reviewer I WANT clarification answers to be structurally unable to reach the approval path SO THAT a reply like "B, merge it" can never approve `github.merge`.
- AS an SRE I WANT delivery and response events counted and correlated by request ID, without question or answer bodies in logs, SO THAT I can debug the E2E flow safely.

## Acceptance criteria (EARS)

Delivery
- WHILE `HUMAN_INPUT_ENABLED` is true AND `WORK_CONTEXT_ENABLED` is true THE SYSTEM SHALL periodically call `GET /api/v1/human-input` as `surface:telegram`, relaying each candidate operator's Telegram id in `X-MCTL-Surface-Actor`.
- WHEN mctl-api lists a pending request that has no local delivery row for (user, request_id, request_hash) THE SYSTEM SHALL queue exactly one compact message into that operator's Saved Messages. The message is headed `INPUT REQUEST` and contains the work ref, question, optional "why", numbered options (single_choice), deadline, a short answer code, and the exact command syntax to answer.
- WHEN the same request is listed again (poll repeats, bot restart, crash after send) THE SYSTEM SHALL NOT send a second message for the same (user, request_id, request_hash).
- WHEN mctl-api lists a request whose `request_hash` (or version) differs from a previously delivered one for the same request_id THE SYSTEM SHALL mark the old delivery `superseded` and deliver the new version under a new answer code.
- THE SYSTEM SHALL render only the safe fields defined by the human-input DTO (question, why, options, deadline, work/request refs, safe links). Each field is sanitized and length-capped, and the whole message is capped at 4096 characters.
- IF `HUMAN_INPUT_ENABLED` is false THEN THE SYSTEM SHALL construct no human-input client, run no poller, register no `/mctl input` command, and behave exactly as today.

Response
- WHEN the operator sends `/mctl input <code> <value>` in Saved Messages THE SYSTEM SHALL resolve the actor with the same rule as `WorkHandler.resolveActor` (self-peer id cross-checked with `Store.TelegramIDByUserID`). It SHALL look up the local delivery row by (user_id, code) and submit `POST /api/v1/human-input/{request_id}/response` with `{request_hash, kind, value}` and an `Idempotency-Key` derived from (request_id, request_hash, command message id).
- WHEN the request kind is `single_choice` THE SYSTEM SHALL accept only an option number or option id shown in the delivered message, and SHALL reply with a usage hint without calling mctl-api otherwise.
- WHEN the request kind is `free_text` THE SYSTEM SHALL submit the remainder of the command, after trimming, as the value, capped at the request's maximum length (or 2000 characters by default).
- WHEN mctl-api accepts the response THE SYSTEM SHALL reply `Answered by you: <short value>. Agent will resume.` and mark the delivery row `answered`.
- IF mctl-api answers 409/410 for a stale hash, expired, cancelled, superseded or already answered request THEN THE SYSTEM SHALL reply `This question is no longer active.`, or `Already answered.` when the platform says the same actor already answered with an identical value, and mark the delivery row terminal.
- IF mctl-api answers 403 (not eligible, or link not found/revoked/expired) THEN THE SYSTEM SHALL reply with neutral wording that does not reveal eligibility policy, and SHALL NOT retry.
- IF the submit call times out or fails at the transport level THEN THE SYSTEM SHALL re-read `GET /api/v1/human-input/{request_id}` and render the canonical state. If that read also fails, it SHALL reply `Could not confirm; check again with /mctl input status <code>`. It SHALL NOT report success.
- WHILE handling a human-input answer THE SYSTEM SHALL NOT call any approval code path: `Executor.Approve` / `Reject`, `GetAgentActionByCode`, or any `/approvals` route. Human-input answer codes and agent-action approval codes SHALL live in separate tables and namespaces.
- THE SYSTEM SHALL NOT send any actor-naming or execution-identity field in a human-input request body. This is enforced by the existing reflection tests extended to the new types.

Status and recovery
- WHEN the operator sends `/mctl input status [code]` THE SYSTEM SHALL fetch the canonical request state from mctl-api and render it. Local state is never treated as authoritative.
- WHEN a delivered request leaves the pending list (answered elsewhere, expired, cancelled) THE SYSTEM SHALL, on the next poll, post one short follow-up `This question is no longer active.` and mark the delivery row terminal.
- WHEN the service restarts THE SYSTEM SHALL resume from durable delivery rows: pending-unsent rows are retried with the same MTProto random_id, and sent rows are not resent.

Observability
- THE SYSTEM SHALL count `human_input_telegram_events_total{event,outcome}` with events `delivery_attempt`, `delivered`, `response_received`, `response_submitted` and `response_rejected`, and SHALL record delivery and response latency histograms.
- THE SYSTEM SHALL log only request_id, work_item_id, delivery row id, Telegram message id, outcome or error class, and mctl-api correlation id. It SHALL NEVER log question text, option labels, or answer values.

## Out of scope

- Inline-keyboard buttons through the login bot. The bot's production webhook belongs to mctl-agent (`internal/bot/bridge.go`), so callbacks would need a cross-repo forwarding bridge. This proposal defines the callback-data format but defers that transport to a follow-up.
- Multi-choice and structured answers, until mctl-api supports them.
- Broadcast or delivery to anyone other than the operator(s) mctl-api lists the request for.
- Any approval card or approval action, and any change to `/mctl approve` / `/mctl reject`.
- Telegram transcript sync into WorkItem context; ContextSnapshot v2 construction (platform/mctl-agents side).
- Changes to mctl-api, mctl-agents or Temporal. These are dependencies, not deliverables.

## Open questions

- The final mctl-api#261 DTO is not pinned in this repo yet. This proposal assumes the field names `request_id`, `request_hash`, `kind`, `question`, `why`, `options[{id,label}]`, `deadline`, `state`, `work_item_id` and `links[]`, and the response body `{request_hash, kind, value}`. The implementer must pin the real contract into `docs/contracts/mctl-api-human-input.md` first and adapt.
- Discovery is by polling `GET /api/v1/human-input` per candidate actor, because relay routes are per-human. Does mctl-api#261 also offer a push/webhook to the surface, or a surface-wide list? Polling is assumed for v1 (30 s interval).
- Candidate actors: v1 polls for users who have a running agent listener and a local `human_input_actors` row, written on a successful `/mctl link` or any successful relay call. Users who linked before this feature ships must run `/mctl input status` once (or have any work-item binding) to be enrolled. Is a backfill from `work_item_bindings` enough?
- Should the operator reply in Telegram's reply-to-message style, without typing the code? The listener (`internal/agent/listener`) does not expose `reply_to` today. v1 uses the explicit code. Reply-to binding is a follow-up.
- What exact wording should be used for "already answered by another eligible user"? v1 renders the canonical state only ("This question is no longer active.") and does not name the other actor.
