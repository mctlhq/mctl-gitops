# Design: issue-300 — Gate A capability verification only

## Decision boundary

This proposal answers one question before any delivery code is built:

> Can an external GitHub/MCTL event produce a new message in the user's already-existing **standard ChatGPT chat**, without periodic polling and without consuming a time-based scheduled-task slot?

The investigator found a promising documented mechanism — OpenAI MCP Events — but the observed documentation names Work chats and dots as supported surfaces. That is not enough to claim support for the user's ordinary existing chat.

Therefore this proposal is intentionally research-only. It stops at a documented, human-observed verdict.

## Existing MCTL architecture

MCTL already has a push-style GitHub event path:

`GitHub webhook -> mctl-api -> Valkey mctl:events:github -> consumers`

The existing contract is references-only, at-least-once, deduplicated by event id and auditable by correlation id. The claude-remote Channel consumes this stream today. A separate `codex-watch` polling skill also exists and must remain untouched until a verified replacement is proven.

No changes to this pipeline are part of Gate A.

## Gate A: authoritative capability matrix

Create `docs/spikes/chatgpt-github-event-push.md` and evaluate these candidates:

| Mechanism | Required question |
|---|---|
| MCP Events | Can a subscription be attached to this pre-existing standard chat? |
| Native GitHub event-triggered task | Can it deliver into this same chat, and does it consume an active task slot/run quota? |
| Time-based scheduled task | Rejected: polling/slot use |
| Slack/Gmail connected-app read | Rejected as push: connector reads require a user/agent action |
| Responses/Assistants API | Rejected as destination: standalone API response is not the user's ChatGPT chat |
| Mobile/OS notification | Notification only, not a message in the chat |

Every claim must be tagged `observed`, `documented` with URL and retrieval date, or `inferred`.

## Human account check

The decisive check happens in the user's own ChatGPT account. Record:

- plan/workspace;
- whether the current standard chat exposes MCP Events/plugin event subscription or a GitHub event-triggered task binding;
- whether the binding can target this already-existing conversation rather than creating a Work/dots/new task conversation;
- whether it consumes an active scheduled-task slot or another run quota.

This is not delegated to an implementer. If the UI/plan does not expose the capability, record that as evidence rather than assuming support.

## Outcomes

### `GO_MCP_EVENTS_EXISTING_CHAT`
Observed support exists for MCP Events into the user's existing standard chat. Stop this proposal and open a separate implementation/proof proposal.

### `GO_NATIVE_GITHUB_TASK`
Observed native GitHub event-triggered delivery reaches the existing standard chat and satisfies the no-polling/no-time-slot requirement. Stop this proposal; prefer the native path unless broader MCTL events require a relay.

### `NOT_SUPPORTED_IN_STANDARD_CHAT`
Only Work chat, dots, a new conversation/task surface, or notification-only delivery is supported. Stop and ask the user to choose among alternatives. Enable nothing automatically.

### `BLOCKED_PLAN_TIER`
The user's plan/workspace cannot create the relevant event-triggered surface. Stop and report the exact requirement.

## Follow-up proposal on GO

Only after an observed GO and explicit human approval should a new proposal design and implement the proof relay. That follow-up must include:

- MCP `events/list|subscribe|unsubscribe` if MCP Events is chosen;
- repository authorization and filter validation;
- Standard Webhooks challenge/signing;
- callback SSRF protections;
- Vault-managed subscription secrets;
- Valkey consumer group and references-only payloads;
- dedupe, suppression, priority, bounded retry/replay and audit;
- feature flag default-off;
- one real GitHub event delivered into the already-existing chat with correlation evidence and latency;
- rollback and explicit watcher-retirement criteria.

## Alternatives

Slack, Telegram and Claude remain valid external notification channels, but are not substitutes for this requirement unless the user explicitly chooses one. The OpenAI API is not treated as a path into the ChatGPT chat list.

## Platform impact of this proposal

Documentation and decision evidence only. No production migration, no new Valkey group, no webhook producer changes, no subscription records, no secrets, no service deployment, and no watcher retirement.