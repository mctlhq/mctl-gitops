# Spike: revalidate push delivery of a completed Scout digest into an existing, voice-capable ChatGPT chat

## Context

Issue mctlhq/.github#432 asks a fresh question, separate from the #300 Gate A
verdict. #300 recorded `NOT_SUPPORTED_IN_STANDARD_CHAT` on 2026-11-02 for a Plus
account, and its accepted artifact stays untouched. The question: can a
completed MCTL Scout digest (mctlhq/mctl-agents#797, `orchestrator/run_scout.py`,
CronWorkflow `mctl-agents-scout` at 06:40 UTC) arrive as a new message in an
existing ChatGPT conversation, which the owner then opens on Android and
discusses by voice? It must arrive without polling and without a time-based
Automations or Scheduled slot. The ordinary existing standard chat is the
primary requirement. A Work chat, a dot or a new task chat is a different
destination that only the owner can choose.

The deliverable is research only:
- a dated, source-backed capability matrix;
- a minimal references-only `scout.digest.ready` event design, with an authorized
  read of an immutable completed digest;
- an architecture and ownership map;
- a threat model and costs;
- an offline reference model with tests;
- a single proposed verdict with alternatives.

It matters because Scout today delivers only to Telegram. A completed digest is
never persisted, so nothing can be re-read or discussed in another surface.
Earlier attempts also show how easily "notification", "new chat" and "message in
my existing chat" get confused.

## User stories

- AS the platform owner I WANT the completed Scout digest to appear in a ChatGPT conversation I already use SO THAT I can open it on Android and discuss it by voice without copying text.
- AS the platform owner I WANT a clear, dated statement of what OpenAI supports today, for which surface and plan SO THAT I choose a destination on evidence, not on a remembered term such as "GRTC".
- AS a reviewer I WANT every capability claim tagged `documented` (URL and retrieval date), `observed` (account check) or `inferred` SO THAT unsupported delivery claims cannot enter the decision.
- AS an operator I WANT the digest event to be references-only, deduplicated by run ID and audited SO THAT retries never re-run news collection or analysis and a lost event costs nothing.
- AS a security reviewer I WANT browser-automation or CDP bridges assessed against OpenAI terms and session-custody risk before anyone builds them SO THAT no credential extraction or private-API scraping is introduced.

## Acceptance criteria (EARS)

Report and verdict
- WHEN the spike report `docs/spikes/chatgpt-scout-push.md` is produced THE SYSTEM SHALL contain a capability matrix dated 2026-11-27 covering these mechanisms:
  - MCP Events;
  - MCP Apps `ui/message` / `sendFollowUpMessage`;
  - native event-triggered tasks in Work;
  - Scheduled tasks;
  - dots;
  - Work chats;
  - ChatGPT Voice on Android;
  - mobile notifications;
  - the Responses API;
  - a user-controlled browser extension or CDP bridge.
- WHEN the matrix is produced THE SYSTEM SHALL give, for each mechanism, the surface, plan, host platform, delivery kind (notification, new message in existing chat, new assistant turn, new task chat, API conversation, background Work) and an evidence tag.
- WHEN the matrix is produced THE SYSTEM SHALL record, per mechanism, whether a user gesture or an open app is required, or mark it `unknown`.
- WHEN a capability is not stated in a first-party source and not observed in the owner's account THE SYSTEM SHALL record it as `unknown` or `not documented`, never as supported or as absent.
- WHEN the report discusses the term "GRTC" THE SYSTEM SHALL state that no first-party OpenAI source defining it was found on 2026-11-27, list the candidate readings (CDP, WebRTC, gRPC, other) as hypotheses, and assert no equivalence.
- WHEN the report states its verdict THE SYSTEM SHALL name exactly one outcome from `GO_STANDARD_CHAT | PROPOSE_OFFICIAL_WORK_VOICE_PILOT | PROPOSE_USER_CONTROLLED_BROWSER_BRIDGE | DEFER_UNSUPPORTED` and list the others as alternatives with reasons.
- IF the only supported destination is a Work chat, a dot or a newly created conversation THEN THE SYSTEM SHALL label it as distinct from the owner's existing standard chat and SHALL require an explicit owner choice before any pilot.

Scout digest event and read
- WHEN the design defines `scout.digest.ready` THE SYSTEM SHALL conform to `events/schemas/event-envelope.v1.schema.json`:
  - `type` is `scout.digest.ready`;
  - `id` is derived from the Argo workflow name (`WORKFLOW_NAME`, the `run_id` already used by `run_scout.py`), never random;
  - `subject` holds references only (`kind: scout.digest`, `run_id`, `digest_sha256`);
  - there is no digest text in the envelope.
- WHEN a Scout run completes THE SYSTEM SHALL (as designed) persist the digest once as an immutable record keyed by `run_id` with a content hash, before the event is published.
- WHILE a digest record exists THE SYSTEM SHALL serve it only through an authorized read (admin principal; tenant-bound reads refused) that returns the same bytes and hash on every read.
- IF the same run is retried or the event is redelivered THEN THE SYSTEM SHALL produce no second digest record, no second ChatGPT delivery for the same `eventId`, and no new feed fetch or model scoring call.
- WHILE the pilot design is in effect THE SYSTEM SHALL leave the existing Telegram `send_message` delivery, the `notify-telegram` onExit step and the existing event consumers (mctl-claude-remote, codex-watch) unchanged.
- WHEN any delivery, read, retry, dedupe-drop or revocation occurs in the model THE SYSTEM SHALL write an audit record carrying `correlation_id = run_id`, with no secret material.

Delivery properties the test plan must prove
- WHEN the synthetic test runs THE SYSTEM SHALL show that delivery is triggered by the event and not by `events/poll`, a timer, or a Scheduled/Automations task.
- WHEN the operator proof is executed (only after separate approval) THE SYSTEM SHALL record the conversation identifier before and after delivery and prove they are equal for the chosen destination. It SHALL also record that Voice was started in that same conversation on Android.
- IF the ChatGPT subscription is revoked or the MCP connector is disconnected THEN THE SYSTEM SHALL deliver nothing further and record the revocation in audit. Reconnect SHALL require a new subscription with a fresh client secret.
- WHILE the discussion in ChatGPT continues THE SYSTEM SHALL grant no GitHub write authority from the delivery. Any issue change uses the existing authorized tools and gates, separately.

Process
- WHILE this proposal is `proposed` THE SYSTEM SHALL perform no implementation, rollout, permission change, account linking, browser automation, live event delivery or GitHub write, and SHALL NOT apply `agents:intake`.

## Out of scope

- Any change to #300's accepted artifact, its approval, or its recorded verdict.
- Implementation of the MCP Events adapter (#377, PR mctlhq/.github#386 still open) or of a production `scout.digest.ready` producer.
- Changes to `cwft-mctl-agents-scout.yaml`, `cronworkflow-mctl-agents-scout.yaml`, Valkey ACLs, or the Scout code. Re-running news collection or scoring.
- Building or running a browser extension, a CDP or WebRTC bridge, or any automation of chatgpt.com. Extracting cookies or tokens. Calling private ChatGPT endpoints.
- Live ChatGPT account linking, subscription, or delivery, and spend beyond this investigator run. Each needs separate explicit owner approval.
- Retiring Telegram delivery or any existing watcher.

## Open questions

- Destination choice: documented support covers Work chats, dots and event-triggered tasks, not an ordinary existing chat. Which does the owner accept for the pilot: one dedicated Work chat (proposed), a dot, or none (`DEFER_UNSUPPORTED`)?
- Whether an MCP Events delivery into a Work chat appends to the same subscribed Work chat, or opens a new task run or chat per batch, is not documented ("ChatGPT receives the event in the subscribed chat"). The account proof must settle it.
- Whether an MCP Events subscription or an event-triggered task counts against a Scheduled-task or Automations slot is not documented. The tasks appear under "Scheduled". Observe it; do not assume.
- Plan: #300 recorded a Plus account. Work and event-triggered tasks are documented for eligible Plus and higher plans, but per-account rollout is unknown until observed.
- Digest storage owner: Scout's pod has no `MCTL_TOKEN`, no gitops write and no Valkey user. Where the immutable digest lives (an mctl-api record is proposed) needs owner sign-off, because it adds one narrow write credential to Scout in a later slice.
- ChatGPT's MCP Events dialect (`webhook-id = eventId`, capability key `events`, `CallbackEndpointError -32015`) diverges from the pinned spec. #377 deferred a compatibility mode to an owner ADR. A single-subscription pilot needs that ADR or an explicit exception.
- "GRTC" is unresolved: no first-party source found. If the owner can recall where they saw it, that would refine the browser-bridge row.
