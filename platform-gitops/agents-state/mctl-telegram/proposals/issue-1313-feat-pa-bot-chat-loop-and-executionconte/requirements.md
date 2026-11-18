# Personal Assistant Phase 1: bot chat loop and ExecutionContext

## Context

Issue #1313 is part of epic #1312 (Personal Assistant). It asks for the read-only Phase 1 chat loop of a dedicated Telegram Bot API bot. The bot is separate from the login bot `MCTL_AI_bot`. It accepts updates only through a webhook protected by a secret token, and only from private chats. Every run gets an `ExecutionContext` (principal, trigger, conversation id, bound connection revisions, budget reservation, consent version) and a job token with `aud=pa-job`. Conversation state has a 24 h TTL and provenance on every fragment. The PA consent `pa-data-flow/v1` is required before the first run. Budget is reserved at claim through the #1092 ledger, with per-principal rate and size limits. Bot output is hardened against link-preview and URL exfiltration. The authoritative source is `docs/agent-runtime/personal-assistant-threat-model.md` (T4, T5, T10, T13, T14) together with `docs/adr/0011-personal-assistant.md`. Where this proposal and the threat model disagree, the threat model wins.

This matters because the chat loop is the substrate that every other Phase 1 item plugs into:
- #1314: linking and connections;
- #1315: catalog pin, connector executor, `pa-job` route enforcement and audit;
- #1316: egress;
- #1318: kill switches.

Identity (I2), cross-user isolation (I10), fail-closed reads (I9) and output safety (I8) start here. The epic records an owner GO dated 2026-11-18 for #1313 **implementation only**. Preview deployment, activation, writes and Alice linking remain on HOLD.

## User stories

- AS a Telegram user (the principal) I WANT to chat privately with the Personal Assistant bot SO THAT I can ask questions that it answers on the managed runtime.
- AS a principal I WANT to be told what data goes to the model provider, and to accept or withdraw consent, SO THAT nothing reaches the provider without my agreement.
- AS a principal I WANT `/new` and `/forget` SO THAT I can start fresh or erase my conversation state at any time.
- AS the platform owner I WANT every run to carry one immutable `ExecutionContext` SO THAT tiering, provenance, approvals, audit and limits are decided from one bound record, never from the trigger or the request.
- AS the platform owner I WANT budget reserved at claim, plus per-principal rate and size limits, SO THAT one principal cannot exhaust spend or capacity.
- AS a security reviewer I WANT every S1 test ID owned by this item to map to a CI test with a recorded mutation run SO THAT the Phase 1 gate (#1317) is evidence-based.

## Acceptance criteria (EARS)

### Ingress (T4; S1-B1..B3)
- WHEN a POST arrives at the PA webhook THE SYSTEM SHALL compare the `X-Telegram-Bot-Api-Secret-Token` header with the configured secret in constant time, before it parses the body.
- IF the secret header is missing or wrong THEN THE SYSTEM SHALL answer 401, SHALL NOT parse or persist the body, and SHALL count the refusal (S1-B3).
- WHEN the system registers the webhook THE SYSTEM SHALL call `setWebhook` with `allowed_updates=["message","callback_query"]` and the secret token.
- IF an update carries any field other than `update_id`, `message` or `callback_query` (including `business_connection`, `business_message`, `edited_message`, `channel_post`, `my_chat_member`) THEN THE SYSTEM SHALL drop it without dispatch, answer 200, and count it by reason (S1-B1).
- IF a message has `chat.type != "private"`, `chat.id != from.id`, a `sender_chat`, a `via_bot`, a missing `from`, or `from.is_bot == true` THEN THE SYSTEM SHALL drop it without creating any state, job or reply (S1-B1).
- IF a `callback_query` has no `message`, or its message chat is not the private chat of `from.id`, THEN THE SYSTEM SHALL drop it (S1-B1).
- WHEN an update is accepted THE SYSTEM SHALL record its `update_id` durably, in the same transaction as any job it creates.
- IF an `update_id` has already been recorded THEN THE SYSTEM SHALL answer 200 and SHALL create no second job, reservation, fragment or reply (S1-B2).
- WHILE the PA bot is configured THE SYSTEM SHALL poll `getWebhookInfo` periodically. IF the URL or `allowed_updates` differ from the configured values, or the call fails or cannot be parsed, THEN THE SYSTEM SHALL set an alerting metric state and SHALL NOT report healthy (I9).

### ExecutionContext and job token
- WHEN a run is created THE SYSTEM SHALL build an `ExecutionContext` with these fields, persisted on the job row:
  - principal (the verified Telegram user id from the update);
  - trigger `interactive`;
  - conversation id;
  - bound connection authority revisions, empty until #1314 provides connections;
  - budget reservation id (set at claim);
  - consent version.
- WHEN a pool worker claims a PA job THE SYSTEM SHALL mint a token with audience `pa-job`. The token SHALL carry the principal, job id, attempt, conversation id, the signed tool set and the context digest. The worker SHALL NOT be able to widen the token.
- WHILE Phase 1 is in force THE SYSTEM SHALL compute the signed tool set from the principal's active connections, restricted to the Phase 1 pinned read tools. Until #1314/#1315 land, the tool set SHALL be empty (S1-I1).
- WHEN a PA route serves a request THE SYSTEM SHALL take the principal, conversation and context from the job row identified by the token, never from request fields.
- WHILE any tiering, provenance, approval, audit or limit decision is made THE SYSTEM SHALL read it from the `ExecutionContext` value, never from the trigger. A CI check SHALL fail if code under `internal/pa` other than the allowlisted audit labelling reads the trigger.

### Conversation state and provenance (T5; S1-I1..I4)
- WHEN a text message from the principal without `forward_origin` is accepted THE SYSTEM SHALL store its `message.text` as a fragment with provenance `user`.
- WHEN the system stores any other content THE SYSTEM SHALL store it with provenance `external` (S1-I3). This covers:
  - forwarded text;
  - `reply_to_message` text and `quote` text;
  - captions;
  - text describing media or documents;
  - model output;
  - tool output.
- WHEN conversation state is loaded THE SYSTEM SHALL treat any fragment whose provenance is missing, unknown or cannot be decrypted or read as `external` (S1-I4). It SHALL NOT load any row from a table without provenance columns.
- WHEN the PA schema is first applied THE SYSTEM SHALL create no conversation state without provenance. No pre-existing state is migrated.
- WHEN a conversation is older than its TTL (default 24 h, from creation) THE SYSTEM SHALL treat it as absent, and a sweeper SHALL delete it.
- WHEN the principal sends `/new` THE SYSTEM SHALL delete the current conversation and its fragments and start a new conversation id.
- WHEN the principal sends `/forget` THE SYSTEM SHALL delete all of the principal's conversations and fragments, cancel the principal's queued jobs, and call `MemoryStore.Forget`.
- THE SYSTEM SHALL define `MemoryStore` as an interface whose only implementation is a no-op: `Load` returns nothing and `Store` stores nothing.
- WHILE Phase 1 is in force, IF a model proposes a write tool THEN THE SYSTEM SHALL produce no downstream call, because no write tool is in the job's signed tool set (S1-I1).

### Consent (T13; S1-N1..N4)
- WHEN a principal without a current `pa-data-flow/v1` consent sends a non-command message THE SYSTEM SHALL reply with the consent text and a server-template inline keyboard, and SHALL create no job (S1-N1).
- WHEN the principal taps Accept THE SYSTEM SHALL resolve the opaque `callback_data` id under `from.id` and store the consent version and time in `pa_consents`, separate from `AssistantInstall` and `agent_profiles`.
- IF the consent record cannot be read THEN THE SYSTEM SHALL refuse the run and send a "temporarily unavailable" message (S1-N2).
- IF the stored consent version differs from the current version THEN THE SYSTEM SHALL ask for consent again before any run (S1-N3).
- WHEN the system claims a job, admits a model turn, or accepts a reply THE SYSTEM SHALL re-check consent.
- WHEN the principal sends `/consent withdraw` THE SYSTEM SHALL do the following in one transaction:
  - mark the consent withdrawn;
  - delete all conversation state;
  - cancel queued and held jobs.
  Every later turn admission or reply of an in-flight job SHALL then be refused (S1-N4).

### Limits and budget (T10; S1-R1..R3)
- IF an incoming message text exceeds 4096 characters THEN THE SYSTEM SHALL refuse it with a message and create no job.
- WHEN tool output is returned to the worker THE SYSTEM SHALL truncate it to 64 KiB with a marker. The truncated output SHALL keep `external` provenance. This applies through the `limits.TruncateToolOutput` helper, which #1315 uses.
- WHEN a run's context exceeds the configured token cap THE SYSTEM SHALL drop the oldest fragments. The run SHALL never exceed the cap.
- IF a principal exceeds the per-principal message rate limit, or already has a run in flight, THEN THE SYSTEM SHALL answer with a "slow down" or "still working" message and create no job.
- WHEN a run proposes its ninth tool call THE SYSTEM SHALL refuse it, and the loop SHALL end with a final answer (S1-R2). The cap is 8 tool calls per run.
- WHEN a pool worker claims a PA job THE SYSTEM SHALL reserve budget in the same transaction, under the #1092 global budget lock.
- IF the budget is exhausted THEN THE SYSTEM SHALL hold the job, send the principal one hold message, and make no model call (S1-R3). A held job SHALL become claimable after its budget window resets, and SHALL expire with the conversation TTL.

### Output hardening (T14; S1-O1..O3)
- WHEN the bot sends any message THE SYSTEM SHALL set `link_preview_options={"is_disabled":true}` and SHALL NOT set `parse_mode` (S1-O1).
- WHEN the system sends model-authored text THE SYSTEM SHALL neutralise every URL-like token unless the exact full URL appears in `user`-provenance text of the same conversation (S1-O2). URL-like tokens include:
  - scheme URLs;
  - scheme-less domains;
  - IDN and punycode hosts;
  - `t.me` links and `tg://` links;
  - `@...bot` mentions.
- WHEN the system sends model-authored text THE SYSTEM SHALL strip model-authored markup (Markdown or HTML link syntax and entity markup). It SHALL attach only server-template inline keyboards whose buttons carry `callback_data`, never a `url` button (S1-O3).

### Cross-user isolation (T4; S1-X1..X2)
- WHEN any PA store reads or mutates conversation, fragment, job, consent, callback, usage or rate-limit state THE SYSTEM SHALL key the lookup by `(principal, id)`. A row of another principal SHALL behave exactly like an absent row (S1-X1).
- WHEN principal A runs THE SYSTEM SHALL leave principal B's state, provenance, audit entries, budget windows and rate limit unchanged (S1-X2).

## Out of scope

- Account linking, the connection store and `/connect` / `/disconnect` (#1314).
- Catalog pin, connector executor, `pa-job` enforcement on executor routes, S1-X3..X4, audit S1-U1..U3 and `/log` (#1315).
- Egress policy (#1316).
- Kill switches `PA_*_ENABLED`, their dispatch-time recheck, per-principal admin disable, and preview deployment (#1318). This item reads `PA_ENABLED` only as a "nothing mounts" guard and leaves the switch semantics and S1-F* tests to #1318.
- Approvals, standing permissions, taint enforcement and the Alice `disclosure` class (Phase 2).
- Long-term memory beyond the no-op `MemoryStore`.
- Scheduled and event triggers. The type exists, but only `interactive` is constructible.
- Any gitops change: Vault secret, ExternalSecret, env vars, PrometheusRule. These are deployment work under #1318 and need a separate owner GO.

## Open questions

- **Ledger subject.** The #1092 ledger (`agent_usage`, `reserveBudget` in `internal/db/agent_usage.go`) is keyed by `users(id)`, an MCTL account. A PA principal is a Telegram id that may have no account. This proposal adds a `pa_usage` table with per-principal windows. The table shares `managedBudgetLockKey` and is counted in the global-day window together with `agent_usage`. The owner should confirm this reading of "through the #1092 ledger". It also needs a decision on whether PA per-principal caps get their own env vars (`PA_BUDGET_USD_PER_PRINCIPAL_DAY`/`_MONTH`, proposed).
- **TTL anchor.** This proposal anchors the 24 h TTL at conversation creation, not at last activity. A sliding TTL would let a conversation, and later its taint, persist indefinitely.
- **S1-X1 scope.** Connections are #1314's. This item tests S1-X1 against every PA store it introduces and publishes a shared `(principal, id)` contract test, which #1314's connection store must also pass. The owner should confirm that S1-X1 stays with #1313, or move the connection half to #1314.
- **Rate-limit values.** These are not in the threat model. Proposed: 20 messages per 10 minutes per principal and 1 in-flight run, via `PA_RATE_*` env vars.
- **Context token cap.** The value is not specified. Proposed default: 32k input tokens, `PA_MAX_CONTEXT_TOKENS`.
- **Worker integration.** This proposal adds a PA mode to the existing pool worker (`internal/agentworker`) instead of a new binary. The owner should confirm this is acceptable for the managed worker image.
