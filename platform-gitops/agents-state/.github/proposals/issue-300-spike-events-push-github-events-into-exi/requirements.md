# Spike: push GitHub events into an existing ChatGPT chat without polling

## Context

The user wants MCTL GitHub activity (PR opened/updated, review submitted, CI
result, merge, release, deploy) to show up as a new message in a ChatGPT
conversation they already have open. It should not show up only in Slack,
Telegram, Claude, an API-only chat or a separate MCTL UI. It must not depend
on periodic polling or use scheduled-task slots. Today the "eyes" on PR
reviews is `codex-watch`, a detached shell loop that calls `gh api` every 180
s. It is shipped as a skill in `services/labs/claude-remote/values.yaml` in
mctl-gitops. The platform also already has a non-polling event path: GitHub
webhook, then the mctl-api producer, then Valkey stream
`mctl:events:github`, then the claude-remote Channel (epic mctlhq/.github#87,
contract in `events/README.md`). That path ends in a Claude session, not in
ChatGPT.

This is a spike with a hard honesty requirement. It must either show a real
GitHub event arriving as a new message in an existing ChatGPT chat, through a
documented and supported mechanism with no scheduled polling, or document
authoritatively that this cannot be done and give the user alternatives to
choose from. In both cases it must leave a requirements/design/tasks plan with
costs, rollout and rollback. No implementation goes to production without
approval, and no existing watcher is switched off before a verified
replacement exists. Preliminary research for this proposal found OpenAI
documentation for "MCP Events": ChatGPT subscribes through a plugin's MCP
server and the server POSTs signed webhooks. The documentation says the event
is received "in the subscribed chat". It names Work chats on ChatGPT web,
Work chats in the desktop app with Cloud selected, and dots as the supported
surfaces. It also describes ChatGPT's own GitHub event-triggered tasks. The
spike has to verify whether either of these really reaches the user's
existing standard chat.

## User stories

- AS the MCTL operator I WANT a GitHub event on an mctlhq repository to appear as a new message in my existing ChatGPT conversation SO THAT I follow PRs, CI, merges, releases and deploys where I already work.
- AS the MCTL operator I WANT an evidence-tagged verdict on what ChatGPT supports SO THAT I decide on a delivery surface knowingly and nothing is substituted silently.
- AS a platform maintainer I WANT the ChatGPT delivery to reuse the existing ingress (signature verification, dedupe, durable stream, audit) SO THAT one event pipeline serves every consumer.
- AS the security owner I WANT event payloads sent to OpenAI to carry references only SO THAT no PR content, diff or secret leaves its system of record through the event channel.

## Acceptance criteria (EARS)

- WHEN the spike concludes THE SYSTEM SHALL publish `docs/spikes/chatgpt-github-event-push.md` with one verdict from the declared outcomes. Every capability claim in it is tagged as observed (live proof), documented (an OpenAI page cited with its retrieval date) or inferred.
- WHEN the report describes a ChatGPT mechanism THE SYSTEM SHALL say which delivery class it produces: (a) an OS/app push notification only, (b) a new message in an existing, user-chosen conversation, (c) a new conversation or task run, or (d) a standalone API response.
- WHEN the report evaluates a mechanism THE SYSTEM SHALL record the plan/workspace tier it needs, whether it uses a scheduled-task slot or a run quota, its documented rate limits, and whether it works in a standard (non-Work, non-dots) chat.
- WHEN a GitHub delivery for an mctlhq repository reaches MCTL ingress THE SYSTEM SHALL verify the `X-Hub-Signature-256` HMAC and deduplicate by `X-GitHub-Delivery` (envelope `id`) before publishing a references-only `mctl.events/v1` envelope to `mctl:events:github`.
- WHEN the proof relay forwards an event to a ChatGPT MCP Events subscription THE SYSTEM SHALL sign it with the subscription's Standard Webhooks secret, send exactly one event per request, keep the body under 256 KiB, and include only envelope reference fields (`id`, `type`, `occurred_at`, `correlation_id`, `subject`).
- WHEN ChatGPT calls `events/subscribe` THE SYSTEM SHALL check the caller's authorization against the requested repositories, validate the filter arguments, and complete the single-use challenge verification before it delivers any event.
- WHEN the end-to-end proof runs THE SYSTEM SHALL record a timestamped capture of one real GitHub event (merge or review on a test PR in an mctlhq repository) arriving in a pre-existing ChatGPT conversation. The capture must include the `X-GitHub-Delivery` id, the audit-stream entries keyed by `correlation_id`, and the end-to-end latency.
- WHILE the proof relay is running THE SYSTEM SHALL do no scheduled polling of GitHub or ChatGPT on the delivery path and SHALL create no time-based ChatGPT scheduled task.
- WHILE no replacement has been verified THE SYSTEM SHALL leave the `codex-watch` skill, the claude-remote Channel and every existing Telegram/Slack notification unchanged.
- IF ChatGPT supports delivery only to a Work chat, a dots surface or a new conversation, and not to an existing standard chat, THEN THE SYSTEM SHALL record the verdict `NOT_SUPPORTED_IN_STANDARD_CHAT`, list the closest alternatives with their trade-offs, and stop for a user decision without enabling any of them.
- IF a callback delivery fails or the subscription expires THEN THE SYSTEM SHALL retry with bounded exponential backoff and keep undelivered envelopes in the durable stream for replay. Reconciliation SHALL be on demand only, never periodic.
- IF an event matches the noise-suppression rules (bot authors, draft PRs, superseded `synchronize` bursts, non-allowlisted repositories or event types) THEN THE SYSTEM SHALL drop it from ChatGPT delivery and write an audit entry with the reason.
- IF the operator removes the ChatGPT subscription or the plugin connection THEN THE SYSTEM SHALL stop delivery on the next attempt, drop the stored subscription and its signing secret, and leave the Valkey stream unaffected.

## Out of scope

- Production rollout of any ChatGPT delivery path. This proposal ends at a proof and a user decision.
- Disabling or changing `codex-watch`, the claude-remote Channel or any Telegram/Slack notification.
- Swapping in Slack, Telegram, email or Claude as the target without the user explicitly choosing it.
- Claiming that a Slack connector read in ChatGPT, or the ChatGPT Responses/Assistants API, writes into a user's existing chat.
- Sending PR titles, bodies, diffs, logs or secrets in the event payload.
- Producers for new event families (workflow_run, release, deploy) beyond a schema and producer design. Building them is follow-up work after the verdict.

## Open questions

- Is the user's "existing standard ChatGPT chat" a Work chat? The MCP Events docs list Work chats (web, desktop with Cloud) and dots only. If the user's chat is a regular chat, the documented path may not apply. This is the deciding question, and the spike must answer it with a live observation.
- Do MCP Events subscriptions or native GitHub event-triggered tasks count against the user's active scheduled-task limit? The docs retrieved for this proposal did not say. One third-party source lists 30 runs/hour and 720/day across event-triggered tasks; this is unverified.
- Which ChatGPT plan/workspace does the user have? Free and Go cannot create event-triggered tasks, and Enterprise/Edu admins must enable "Allow event-triggered scheduled tasks".
- Which MCP server should advertise the `events` capability: the mctl connector served by mctl-api, or a new dedicated endpoint? MCP Events requires the same authenticated endpoint as the tools. This run did not verify mctl-api's MCP hostname or protocol version.
- The OpenAI help article on scheduled tasks returned HTTP 403 to this run. Its claims here come from search snippets and third-party summaries and must be re-read first-hand during the spike.
- Deploy events have no producer today. `events/README.md` lists only `github.pull_request.*` and `github.pull_request_review.submitted`. Which source should be authoritative for deploys (Argo Workflows, ArgoCD sync, or GitHub `deployment_status`)?
