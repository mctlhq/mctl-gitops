# Design: issue-571-feat-human-input-telegram-delivery-reply

## Current state

Two Telegram surfaces exist in mctl-telegram today.

1. **The operator's own account in Saved Messages (MTProto, `gotd/td`).** This is the surface the communication agent and the #443 work-context adapter already use.
   - `internal/agent/listener` picks up owner messages in Saved Messages that parse as `/mctl ...` (`db.EventKindSavedCommand`). Dedup is per-user through `agent_saved_command_cursors`. Messages go to `control.Router.HandleSavedText(ctx, SavedMeta, text)` (`internal/agent/control/router.go`).
   - `SavedMeta` carries `UserID`, `SelfTGID`, `ChatTGID` and `TGMessageID`.
   - `control.ParseCommand` (`internal/agent/control/command.go`) is a pure parser for `/mctl status|leads|conversations|show|continue|pause|takeover|approve|reject|link|work`.
   - `control.Notifier` (`internal/agent/control/notifier.go`) has two paths. The `Reply` path is synchronous. The `DeliverPending` path is crash-safe and runs over `owner_notifications`: the `random_id` is persisted before the RPC, a claim lease applies, a `MaxPendingAge` retirement applies, the `GlobalKill` gate applies, and `truncateForTelegram` caps text at 4096 characters.
   - Approvals use 6-character codes (`internal/agentapi/approvalcode.go`), `agent_actions`, and `/mctl approve <code>` routed to `Router.handleApprove` → `Executor`.

2. **The login bot (Bot API).**
   - `internal/botapi` is a plain-text `SendMessage` only.
   - `internal/bot` is a transport-only receiver with durable exactly-once `bot_updates`. `Update` deliberately decodes no text and no callback `data`; the comment says "#571 will define a format". `Registry` is the handler seam, and its doc names #571 callbacks.
   - In production the bot's webhook is owned by mctl-agent. Only `/start` is forwarded, through `POST /internal/bot-start-observations` (`internal/bot/bridge.go`). The long-poll receiver is off unless `BOT_RECEIVER_ENABLED` (see `cmd/server/main.go` around line 1000).

The **#443 work-context adapter** is the base this design builds on:
- `internal/workctx/client.go`: `Client.relay` authenticates as `surface:telegram` (`MCTL_SURFACE_TELEGRAM_TOKEN`). It sets only `Authorization`, `X-MCTL-Surface-Actor` and `Idempotency-Key`, uses a 20 s timeout, caps response bodies at 1 MiB, checks `schema_version`, and maps typed errors in `errors.go` (`ErrLinkNotFound`, `ErrStateVersionConflict`, ...). Reflection tests `TestNoActorField` and `TestRouteAllowlist` guard the request shapes and routes.
- `internal/agent/control/work.go`: `WorkHandler.resolveActor` is the single rule for deriving the relay actor (self-peer id cross-checked against `Store.TelegramIDByUserID`, fail closed).
- `internal/db/work_item_bindings.go` with the schema in `internal/db/agent_schema.go`: the correlation row stores only numeric Telegram ids and platform opaque ids.
- `docs/contracts/mctl-api-work-context.md` lists `GET /api/v1/human-input`, `GET /api/v1/human-input/{request_id}` and `POST /api/v1/human-input/{request_id}/response` as relay routes "owned by #571".
- Gate: `WORK_CONTEXT_ENABLED` (`internal/config/config.go`).

Sensitive-field log redaction lives in `internal/audit/redact.go` (`sensitiveKeys`).

## Proposed solution

### Surface choice for v1: Saved Messages + typed answer code

Deliver into the operator's own Saved Messages through the existing crash-safe `owner_notifications` / `Notifier.DeliverPending` path. Accept answers as `/mctl input <code> <value>` through the existing listener and router. Reasons:
- Everything needed already exists in this repo and is tested: the identity rule (`resolveActor`), the relay client, crash-safe delivery with MTProto random_id dedup, and per-user command dedup.
- The Bot API path would need inline-keyboard callbacks. Production callbacks arrive at mctl-agent's webhook, not here, so v1 would depend on a cross-repo bridge change. That is deferred (see Alternatives). This design still defines the callback payload format (`hi:<code>:<option-index>`, ≤64 bytes) so the follow-up only adds transport.

### New package `internal/humaninput`

- `client.go`: three new methods on the existing `workctx.Client` (same `relay`, same headers, same allowlist test, extended):
  - `ListHumanInput(ctx, actorTGID) ([]RequestView, error)`
  - `GetHumanInput(ctx, actorTGID, requestID) (*RequestView, error)`
  - `RespondHumanInput(ctx, actorTGID, requestID string, r ResponseRequest, idemKey string) (*ResponseView, error)`

  New DTOs `RequestView{RequestID, RequestHash, Version, Kind, State, Question, Why, Options[]{ID,Label}, Deadline, WorkItemID, WorkRef, Links[], MaxLength}` and `ResponseRequest{RequestHash, Kind, Value}`. There is no actor field and no approval field. New typed errors: `ErrRequestNotActive` (409/410 with codes like `request_expired`, `request_superseded`, `request_hash_mismatch`, `request_cancelled`, `already_answered`), `ErrNotEligible` (403 `not_eligible`, rendered neutrally) and `ErrAnswerInvalid` (400/422). The exact status/code mapping is pinned from mctl-api#261 into a new `docs/contracts/mctl-api-human-input.md`. The methods live in `workctx` so `TestRouteAllowlist` / `TestNoActorField` cover them, and `humaninput` holds only the logic.
- `render.go`: a pure `Render(RequestView, code) string`. It takes only allowlisted fields and runs each through `internal/sanitize` (`UserContent` with per-field caps: question 600, why 400, option label 120, at most 10 options). Format:
  ```
  INPUT REQUEST (not an approval)
  Work: mctlhq/mctl-telegram#571
  Question: ...
  Why: ...
  Options:
    1. A ...
    2. B ...
  Deadline: 2026-10-04 12:00 UTC
  Answer: /mctl input K7QM3R <number>
  Ref: request <request_id> v<version>
  ```
  For free_text, the answer line is `/mctl input K7QM3R <your answer>`. The header string `INPUT REQUEST` is deliberately distinct from approval notifications.
- `poller.go`: `Poller.RunOnce(ctx)` runs every `HUMAN_INPUT_POLL_INTERVAL` (default 30 s) as a goroutine in `cmd/server/main.go`, the same pattern as the other sweeps. For each candidate actor (see below):
  - `ListHumanInput`.
  - For each pending request, an idempotent `Store.UpsertHumanInputDelivery(user, request_id, request_hash)`. If it inserts, it generates a code and queues an `owner_notifications` row of new kind `human_input` (body encrypted like other rows) in the same transaction.
  - Delivery rows for this user that are `sent` but no longer listed move to `inactive`, and a one-line follow-up notification is queued.
  - A new hash for a known request_id marks the old row `superseded`.
  - A 403 link_* response marks the actor dormant with exponential backoff (max 1 h). This is not an authorization decision; it only stops wasted polling.
- `handler.go`: `Handler.Handle(ctx, SavedMeta, Command)` handles `/mctl input <code> <value>` and `/mctl input status [code]`. Flow:
  1. `resolveActor`, shared by extracting it from `WorkHandler` into a package-level function.
  2. Look up `human_input_deliveries` by (user_id, code). An unknown or terminal row gives "This question is no longer active."
  3. Validate value locally only for shape: an option index or id within the delivered options, or non-empty text within `MaxLength`.
  4. `RespondHumanInput` with `Idempotency-Key = sha256(request_id|request_hash|tg_message_id)`. A redelivered command reuses the key, and mctl-api dedupes it.
  5. Map the canonical result to a reply and a row state. A transport error or timeout leads to `GetHumanInput`, and the reply renders that canonical state (never "success" without platform confirmation).

### Command wiring

- `control.ParseCommand` adds `CmdInput = "input"`. Only the first token after `input` is the code (same rationale as approve/link). The remainder, with whitespace preserved via the original text, is the value. `status` is a reserved subcommand.
- `Router` gets a nilable `Input *humaninput.Handler`, like `Router.Work`. If it is nil, the command falls through to the existing unknown-command reply. `Router` dispatches `CmdInput` to `Input.Handle` only. It never touches `Executor`, `handleApprove` or `agent_actions`.
- `Notifier.DeliverPending` formats kind `human_input` by passing the stored body through (render happens at enqueue time). It records the sent `tg_message_id` back on the delivery row for support/debugging.

### Storage (migrations in `internal/db/agent_schema.go`, SQLite + PG variants)

```
human_input_deliveries(
  id PK, user_id FK users ON DELETE CASCADE,
  request_id TEXT NOT NULL, request_hash TEXT NOT NULL, request_version INTEGER NOT NULL DEFAULT 0,
  work_item_id TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
  answer_code TEXT NOT NULL, option_ids_json TEXT NOT NULL DEFAULT '[]',
  max_length INTEGER NOT NULL DEFAULT 0,
  notification_id INTEGER REFERENCES owner_notifications(id) ON DELETE SET NULL,
  tg_message_id INTEGER, state TEXT NOT NULL DEFAULT 'queued',  -- queued|sent|answered|inactive|superseded|rejected
  last_outcome TEXT NOT NULL DEFAULT '', delivered_at, responded_at, created_at, updated_at)
UNIQUE(user_id, request_id, request_hash)
UNIQUE(user_id, answer_code)
human_input_actors(user_id PK FK users, tg_id INTEGER NOT NULL, dormant_until DATETIME, last_error TEXT NOT NULL DEFAULT '', updated_at)
```

There is no question, why, label or answer column. The rendered body exists only in the encrypted `owner_notifications.body_encrypted`, which the existing purge nulls. `option_ids_json` stores option ids only, never labels.

A `human_input_actors` row is a polling hint, not authorization. It is written on a successful `/mctl link`, any successful relay call in `WorkHandler`, or `/mctl input status`. A one-time backfill comes from `DISTINCT user_id FROM work_item_bindings`.

Answer codes reuse the alphabet of `agentapi.newApprovalCode`, extracted to a small shared helper. They live in a separate table and command namespace, so a human-input code can never resolve an agent action and the reverse also holds.

### Idempotency and stale-interaction matrix

| Case | Handling |
|---|---|
| Poll repeats or bot restarts | UNIQUE(user_id, request_id, request_hash) means at most one delivery |
| Crash mid-send | Existing `owner_notifications` random_id persistence; MTProto server-side dedup |
| Duplicate command redelivery | Listener cursor dedup + stable Idempotency-Key |
| Double answer by the user | Second submit returns `already_answered` from mctl-api, rendered as "Already answered." |
| API timeout after acceptance | Re-read `GET /human-input/{id}` and render the canonical state |
| Stale message, newer hash | The old code points at the old hash; mctl-api rejects the hash mismatch; the row becomes `superseded` |
| Expired / cancelled | mctl-api 409/410; or the request drops out of the list, triggering a follow-up "no longer active" |
| Two eligible users | mctl-api decides; the loser sees "This question is no longer active." |
| New request while an old one is visible | Distinct codes per (request_id, hash); every message carries its own code |

### Config

- `HUMAN_INPUT_ENABLED` (default false). It requires `WORK_CONTEXT_ENABLED=true`; `Config.Load` refuses otherwise.
- `HUMAN_INPUT_POLL_INTERVAL` (default 30s, minimum 10s).

### Observability

`internal/metrics` gains:
- `human_input_telegram_events_total{event,outcome}`;
- `human_input_telegram_deliver_latency_seconds` (request `created_at` → sent);
- `human_input_telegram_respond_latency_seconds` (sent → submitted).

slog lines carry `request_id`, `work_item_id`, `delivery_id`, `tg_message_id`, `outcome` and `correlation_id` (from mctl-api's `X-Request-ID` response header, which the relay must expose). `question`, `why`, `options`, `answer` and `value` are added to `audit/redact.go` `sensitiveKeys` as defense in depth.

### Future Bot API transport (not built here)

The callback data is `hi:<answer_code>:<option_index>`. The `bot.Update.CallbackQuery` widening would decode only that prefix-validated token. A `bot.Registry` handler for `db.KindCallbackQuery` would call the same `humaninput.Handler` core with an actor derived from `callback_query.from.id` (verified as the private chat). This needs mctl-agent to forward `hi:` callbacks over a bridge endpoint mirroring `BotStartObservationPath`.

## Alternatives

1. **Login bot with inline buttons as the v1 transport.** This matches the issue's "inline buttons preferred". It was rejected for v1 because, in production, callbacks reach mctl-agent's webhook and not this service (`internal/bot/bridge.go` header comment). The feature would block on a cross-repo bridge, and the `bot.Update` decode policy would have to be widened at the same time. It also adds a second identity path (callback `from.id`) next to the proven Saved Messages self-peer rule. This design keeps it as a defined follow-up.
2. **Reuse `agent_actions` / `/mctl approve <code>` for answers.** This would give the least new code. It was rejected because it merges clarification with approval in both storage and code path, which the issue explicitly forbids. A bug could then let an answer approve a send.
3. **Store request content locally and render from it, or let mctl-api push to a bot webhook.** Local content would be a second copy of canonical state and private data. A push endpoint does not exist in the pinned contract, and it would add an inbound authenticated surface. Polling the relay list is stateless and converges on canonical state. Push can replace the poller later behind the same `Poller` interface.

## Platform impact

- **Migrations:** two new tables, `CREATE TABLE IF NOT EXISTS` in both the SQLite and PG schema lists; additive only. The new `owner_notifications.kind` value `human_input` needs no schema change.
- **Backward compatibility:** everything is behind `HUMAN_INPUT_ENABLED=false` by default. With the flag off, no client methods are called, no poller runs and `Router.Input` is nil, so behaviour is unchanged. `/mctl input` with the flag off returns the existing unknown-command reply.
- **Resources:** one `GET /human-input` per enrolled actor per 30 s. That is negligible at current operator counts. Polling reads do not spend the per-human write budget (20/min); one answer is one write.
- **Risks and mitigations:**
  - *mctl-api#261 contract drift:* pin the contract doc first, use typed DTOs, and reject an unknown `schema_version`. Ship disabled until mctl-api is deployed.
  - *Leaking sensitive context:* only allowlisted DTO fields are rendered, through sanitize with caps; no content columns; redact keys added.
  - *Clarification and approval confusion:* separate table, command, code namespace and header text; a test asserts `Executor` is never invoked.
  - *Poll storms on unlinked users:* dormant backoff on 403 link_*.
  - *Kill switch:* `Notifier.GlobalKill` already silences `owner_notifications` delivery; the poller also skips enqueue when the kill switch is on.
