# PA bot: stream the answer and tool status as Telegram drafts (sendMessageDraft)

## Context

In the PA bot a principal sends a message and sees only the "typing" status
(`internal/pa/typing.go`) until the whole answer arrives. The worker calls the
model with `stream: false` (`internal/agentworker/openaiclient.go`, `chat`),
posts the finished text once to `RouteReply`, and `serveReply`
(`internal/pa/runloop.go`) stores it as an assistant fragment and queues one
outbox row. The outbox renders it again with `safetext.Render` and sends it
exactly once (T14). On preview (GLM-5.3-Flash through the `mctl-telegram` AI
Gateway) a run that reads a chat with `get_messages` and summarises it takes
tens of seconds, and during that time the chat cannot say what is happening.

The issue asks for presentation-only streaming in the private chat: show a
server-authored status while a tool runs, and a growing partial answer while
the model writes, using Bot API `sendMessageDraft`. The final answer keeps its
current path unchanged: stored, rendered, queued in the outbox and sent once.
Drafts are ephemeral (~30 s), are never stored and never enter the outbox, and
every partial goes through the same `safetext` rules as the reply. Streaming is
behind a new server flag `PA_STREAMING_ENABLED` (default `false`, re-read per
job and per draft) and a worker switch, preview first.

## User stories

- AS a PA principal I WANT to see what the assistant is doing ("Reading
  messages...") while a tool runs SO THAT a long run is not met with silence.
- AS a PA principal I WANT to see the answer grow while it is written SO THAT I
  can start reading before the run ends.
- AS a PA principal I WANT exactly one persisted answer, identical to today's
  SO THAT streaming never duplicates or changes what I keep in the chat.
- AS the PA operator I WANT streaming behind a default-off flag re-read at
  runtime SO THAT I can turn it off on preview without a deploy and keep prod
  unaffected.
- AS the security owner I WANT every draft to pass the same `safetext.Render`
  allow-list as the reply and every send to go through `output.Sender` SO THAT
  streaming opens no new path for model text or links to reach the chat (T5,
  T14, S1-O1).

## Acceptance criteria (EARS)

Streaming on, happy path
- WHEN `PA_STREAMING_ENABLED` is `"true"` at claim time AND the worker's
  `AGENT_PA_STREAMING` is `"true"` THE SYSTEM SHALL mark the claim
  `streaming: true` and the worker SHALL call the model with `stream: true` and
  `stream_options.include_usage: true`.
- WHEN a streaming run's tool call is admitted by `RunLoop.AdmitToolCall` THE
  SYSTEM SHALL send, through `output.Sender.SendDraft`, the server template for
  that pinned tool in the chat's language (EN or RU via `output.Languages`),
  containing no model text, no tool argument and no chat title.
- WHILE the model is streaming answer text THE worker SHALL post the
  accumulated text to `RouteDraft` no more often than its minimum interval and
  only after its minimum delta size, and SHALL NOT post tool-call deltas or
  reasoning content.
- WHEN `RouteDraft` accepts a partial THE SYSTEM SHALL render it with
  `safetext.RenderPartial` and the same `safetext.AllowFromUserText` allow-list
  as `serveReply`, and send it as a draft with the job's non-zero `draft_id`.
- WHEN the reply arrives THE SYSTEM SHALL keep today's path exactly (fragment,
  outbox row, one `sendMessage`), and the persisted message SHALL replace the
  draft.
- WHEN the first draft of a job is shown THE SYSTEM SHALL stop sending the
  typing status for that job.
- WHILE a job is running and its last draft is older than the draft refresh
  interval (20 s) THE SYSTEM SHALL re-check the job with the run gate and, only
  if it still runs, re-send the same rendered draft, so a long tool call does
  not let the draft lapse.

Rendering safety
- THE SYSTEM SHALL never send a partial that did not come out of
  `safetext.RenderPartial`.
- WHEN a partial ends inside a run of non-boundary characters (an unfinished
  token) THE SYSTEM SHALL withhold that trailing run from the draft, so a prefix
  of a disallowed URL is never shown as a live link, including a prefix that
  equals an allowed token.
- IF a partial renders to more than one message part or is refused with
  `safetext.ErrTooLong` THEN THE SYSTEM SHALL skip that draft (no send, no
  truncation) and answer the worker `200 {"shown": false}`.
- THE SYSTEM SHALL never store a partial as a fragment and never enqueue it in
  the outbox.

Stopping and refusal
- IF the job is no longer running under the same attempt, context digest and
  gate (consent withdrawn, conversation closed or expired, principal disabled or
  off the allowlist, cancelled, stale attempt) THEN `RouteDraft` SHALL answer as
  `serveTurn` does (409 or the existing stop code) and send nothing, and no
  later draft refresh SHALL be sent for that job.
- IF `PA_STREAMING_ENABLED` is off, missing or unreadable when `RouteDraft` is
  called THEN THE SYSTEM SHALL answer `404 {"stop":"streaming_off"}` and send
  nothing, and the worker SHALL stop posting drafts for that job.
- IF one job exceeds the server's per-job draft cap (minimum interval between
  sends, maximum drafts per job) THEN THE SYSTEM SHALL answer `429` and send
  nothing, without affecting the run.
- IF a draft post fails for any reason THEN the worker SHALL continue the run
  unchanged; a draft never ends, retries or delays a run.

Cost accounting
- WHEN a streamed response carries a usage chunk THE worker SHALL account its
  cost exactly as for a non-streamed response (`Prices.Cost(res.Usage)`).
- IF a streamed response carries no usage, or zero tokens both ways, THEN the
  worker SHALL set `UsageReported=false`, and the run SHALL fail closed exactly
  as today: no further model call after tool calls, and a reply with no
  `cost_usd`, which the server settles at the full reservation, never at zero.

Flag off and compatibility
- WHILE `PA_STREAMING_ENABLED` is not `"true"` THE SYSTEM SHALL produce a claim
  response byte-identical to today (the `streaming` field omitted), the worker
  SHALL send `stream: false` requests exactly as today, and no draft SHALL be
  sent; the existing run-loop, typing and outbox tests SHALL pass unchanged.
- WHEN a streaming-capable worker claims from a server without `RouteDraft`
  (claim has no `streaming` field) THE worker SHALL not stream.
- THE SYSTEM SHALL keep `internal/pa/output/sender.go` the only file under
  `internal/pa` naming `sendMessageDraft` (`TestS1O1_SenderIsTheOnlyBotAPICallSite`).

## Out of scope

- Streaming in group chats (drafts are private-only).
- `can_stop` / `keep_on_stop` and cancelling a job on
  `stopped_message_generation`: named follow-up.
- The empty-text "Thinking..." placeholder replacing the typing status before
  the first token: named follow-up; typing stays for that gap.
- Showing a chat title or any tool argument in a status.
- Writes and approvals; changing the model; prod rollout (prod stays off with
  the rest of PA).
- `editMessageText` as a fallback (it would make the persisted message mutable).

## Open questions

- Whether the persisted `sendMessage` reliably replaces the draft on Telegram
  Android and Desktop, and whether a `sendChatAction` sent during a visible
  draft disturbs it, can only be confirmed on a real client. The design assumes
  it replaces (Bot API docs) and stops typing once a draft is shown; the PR
  must record the manual check.
- The preview `mctl-telegram-preview` replica count was not confirmed (no
  `replicaCount` read in its values.yaml by this run). The per-job draft cap
  and the typing/draft presence state are in-memory per replica, like the
  typing loop today; with more than one replica a draft arriving at a
  non-claiming replica is still gated and capped there, but cannot stop the
  other replica's typing loop (which then lapses on its idle bound).
- Batching defaults (proposed: 1 s minimum interval, 64 UTF-16 units minimum
  delta on the worker; 700 ms minimum interval and 120 drafts per job on the
  server) are guesses to be tuned on preview.
- Whether GLM-5.3-Flash through the Nebius custom provider on the Cloudflare
  AI Gateway honours `stream_options.include_usage`. If it does not, every
  streamed run settles at the full reservation (fail closed); that would make
  streaming unusable for cost and must be checked on preview before the flag
  stays on.
- Whether answer text the model writes in a turn that ends in tool calls
  ("Let me check...") should be drafted. The design drafts it (it is rendered
  model text, replaced by the tool status a moment later); an alternative is to
  draft only after `finish_reason` is known, which defeats streaming.
