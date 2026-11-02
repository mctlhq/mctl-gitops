# Spike: can GitHub events reach an existing standard ChatGPT chat without polling?

## Context

The user wants MCTL GitHub activity to appear as new messages in the existing standard ChatGPT conversation they already use. Slack, Telegram, Claude, API-only responses, a new ChatGPT conversation, Work-only surfaces, or dots are not silent substitutes.

MCTL already has a push event path for GitHub activity: GitHub webhook -> mctl-api -> Valkey stream `mctl:events:github` -> consumers. The unknown is the final ChatGPT delivery surface.

Preliminary research found OpenAI MCP Events documentation saying events arrive in a subscribed chat, but the documented surfaces observed by the investigator were Work chats and dots. Whether an arbitrary pre-existing standard chat can subscribe, and whether this consumes scheduled-task capacity, must be verified in the user's actual ChatGPT account before any relay code is written.

## Scope of this proposal

This proposal is **Gate A only: capability verification and a decision**. It must not implement an MCP Events relay, Valkey consumer, callback delivery code, new event producers, or retire any watcher.

If Gate A produces a GO verdict, a **separate follow-up proposal** must be created for the proof relay and end-to-end delivery test, and that follow-up requires a new explicit human approval before implementation.

## Acceptance criteria

- THE SYSTEM SHALL publish `docs/spikes/chatgpt-github-event-push.md` with a capability matrix for MCP Events, native GitHub event-triggered tasks, scheduled tasks, connected-app reads, API responses, and notification-only surfaces.
- EVERY capability claim SHALL be tagged `observed`, `documented` (with URL and retrieval date), or `inferred`.
- THE REPORT SHALL distinguish these delivery classes: (a) OS/app notification only, (b) new message in an existing user-chosen chat, (c) new conversation/task run, (d) standalone API response.
- THE REPORT SHALL record plan/workspace requirements, slot or run-quota behavior when known, and whether the mechanism works in a standard non-Work, non-dots chat.
- THE USER-ACCOUNT CHECK SHALL verify whether an MCP Events subscription or native GitHub event-triggered task can be attached to the user's pre-existing standard chat and whether it consumes an active task slot. This is a human-observed check in the user's ChatGPT account, not an agent assumption.
- IF class (b) is not supported for the user's standard chat, THE SYSTEM SHALL record `NOT_SUPPORTED_IN_STANDARD_CHAT` or `BLOCKED_PLAN_TIER`, list alternatives and stop for a user decision. No alternative is enabled automatically.
- IF class (b) is supported, THE SYSTEM SHALL record either `GO_MCP_EVENTS_EXISTING_CHAT` or `GO_NATIVE_GITHUB_TASK`, document the observed evidence and open a separate implementation/proof proposal. This proposal SHALL stop before implementation.
- WHILE no replacement is proven, THE SYSTEM SHALL leave `codex-watch`, the claude-remote Channel, Slack and Telegram notification paths unchanged.
- THIS PROPOSAL SHALL NOT add or modify production code, deployment config, Valkey consumers, webhook producers, ChatGPT subscription handlers, or feature flags.

## Evidence to verify

- OpenAI MCP Events documentation first-hand, including supported ChatGPT surfaces and callback/subscription semantics.
- OpenAI documentation for GitHub event-triggered tasks and scheduled-task limits/quotas.
- The user's actual ChatGPT plan/workspace and available UI in the existing standard chat.
- Existing MCTL GitHub event pipeline only as architecture context; no changes to it in this proposal.

## Outcomes

- `GO_MCP_EVENTS_EXISTING_CHAT`
- `GO_NATIVE_GITHUB_TASK`
- `NOT_SUPPORTED_IN_STANDARD_CHAT`
- `BLOCKED_PLAN_TIER`

## Out of scope

- Implementing `events/list`, `events/subscribe`, `events/unsubscribe`.
- Building `chatgpt-relay` or any Valkey consumer.
- Sending a real GitHub event through a new relay.
- Adding workflow/release/deploy producers.
- Disabling or replacing existing watchers.
- Automatically moving the user to Work, dots, Slack, Telegram, Claude or another conversation.

## Follow-up on GO

A new proposal must cover: authenticated MCP Events subscription handling, Standard Webhooks signing, references-only payloads, repository authorization, callback SSRF protections, durable retry/replay, dedupe, filtering/noise suppression, audit, feature-flagged rollout, one real end-to-end GitHub event into the pre-existing chat, latency evidence, rollback, and watcher retirement only after successful proof.