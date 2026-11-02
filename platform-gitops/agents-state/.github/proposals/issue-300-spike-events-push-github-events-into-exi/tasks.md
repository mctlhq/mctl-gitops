# Tasks: issue-300 — capability gate only

- [ ] 1. Add/update `roadmap/spikes/chatgpt-github-event-push.yaml` with lifecycle `proposed`, issue `mctlhq/.github#300`, outcomes `GO_MCP_EVENTS_EXISTING_CHAT`, `GO_NATIVE_GITHUB_TASK`, `NOT_SUPPORTED_IN_STANDARD_CHAT`, `BLOCKED_PLAN_TIER`, and report `docs/spikes/chatgpt-github-event-push.md`. DoD: roadmap validation passes.
- [ ] 2. Build the capability matrix from first-hand OpenAI documentation: MCP Events, native GitHub event-triggered tasks, scheduled tasks, connected apps, API responses, notification-only surfaces. Record URLs, retrieval dates, delivery class, plan/workspace requirement, slot/run-quota behavior and standard-chat support. Tag each claim `observed`, `documented` or `inferred`.
- [ ] 3. Perform the user-account check in the user's existing standard ChatGPT conversation. Record whether MCP Events or a native GitHub event task can bind to this already-existing chat and whether it consumes an active scheduled-task slot or another quota. This is a human-observed step; do not substitute an agent assumption.
- [ ] 4. Write exactly one verdict:
  - `GO_MCP_EVENTS_EXISTING_CHAT`, or
  - `GO_NATIVE_GITHUB_TASK`, or
  - `NOT_SUPPORTED_IN_STANDARD_CHAT`, or
  - `BLOCKED_PLAN_TIER`.
  Include the supporting evidence and trade-offs.
- [ ] 5. If verdict is NO/BLOCKED: stop and ask the user to choose among alternatives. Enable nothing and leave every watcher unchanged.
- [ ] 6. If verdict is GO: open a **separate follow-up proposal** for implementation and end-to-end proof. The follow-up must require a new explicit human approval before any relay/subscription code runs.
- [ ] 7. Mark this spike `decided` only after the user decision is recorded. Keep `codex-watch`, claude-remote Channel, Slack and Telegram unchanged.

## Explicit stop conditions

This proposal SHALL NOT:

- implement `events/list`, `events/subscribe` or `events/unsubscribe`;
- create a `chatgpt-relay` Valkey consumer group;
- add callback delivery/signing code;
- add workflow/release/deploy event producers;
- deploy a feature flag or subscription storage;
- send a real event through newly written relay code;
- disable or retire any current watcher.

## Tests / evidence checks

- [ ] T1. Roadmap/spike schema validation passes.
- [ ] T2. Every capability-matrix claim has an evidence tag and source/retrieval date where applicable.
- [ ] T3. The report explicitly distinguishes notification-only, existing-chat message, new conversation/task run and standalone API response.
- [ ] T4. The user-account check records the actual target chat and plan/workspace surface; no inferred support is promoted to observed.
- [ ] T5. Static proposal review confirms there are no implementation tasks before the GO verdict and new human approval.

## Rollback

Documentation-only changes are reverted through the normal PR path. No runtime state or existing event/notification path is changed by this proposal.