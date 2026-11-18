# Tasks: issue-1313-feat-pa-bot-chat-loop-and-executionconte

Scope reminder: implementation only, under the owner GO of 2026-11-18. This item makes no deployment and no gitops change, and does not call `setWebhook` against the real bot.

- [ ] 1. **Config.** Add the `PA_*` fields to `internal/config/config.go`:
  - `PA_ENABLED`;
  - `PA_BOT_TOKEN`, `PA_WEBHOOK_SECRET`, `PA_WEBHOOK_URL`;
  - `PA_CONVERSATION_TTL`;
  - `PA_RATE_MESSAGES`, `PA_RATE_WINDOW`;
  - `PA_MAX_CONTEXT_TOKENS`;
  - `PA_BUDGET_USD_PER_JOB`, `PA_BUDGET_USD_PER_PRINCIPAL_DAY`, `PA_BUDGET_USD_PER_PRINCIPAL_MONTH`.

  Validation: the PA token must differ from `TELEGRAM_LOGIN_BOT_TOKEN`, and the webhook secret must be at least 32 characters from `[A-Za-z0-9_-]`. Add `pa_bot_token` and `pa_webhook_secret` (env and Go field names) to `sensitiveKeys` in `internal/audit/redact.go`.
  — DoD: config tests cover the defaults (everything off), every validation error, and redaction of both fields.

- [ ] 2. **Schema** (depends on 1). Add `internal/db/pa_schema.go` with `migratePA(ctx, conn, pg)`, called from `Migrate`, and register it in `migrate_cached.go`. It creates these tables, with SQLite and Postgres DDL:
  - `pa_updates`, `pa_conversations`;
  - `pa_fragments`, with `provenance NOT NULL CHECK IN ('user','external')`;
  - `pa_consents`, `pa_callbacks`, `pa_jobs`, `pa_usage`, `pa_rate`.

  — DoD: migrations are idempotent on both dialects, the existing migration tests stay green, and a new test asserts the CHECK constraint.

- [ ] 3. **Principal-scoped store methods** (depends on 2). `internal/db/pa_*.go`: `AcceptPAUpdate`, conversation CRUD, fragments, consent, callbacks, jobs, usage and rate. Every method takes `principal` first and filters on it. Add `crypto.SealForPrincipal` / `OpenForPrincipal` with HKDF info `mctl-pa-conversation/v1`.
  — DoD: `RunPrincipalScopedContract` passes for every store, and fragment bodies are never stored in plaintext.

- [ ] 4. **`internal/pa/execctx`** (depends on 3). `ExecutionContext`, the unexported `Trigger` with `Interactive()`, `ConnectionRevision`, canonical-JSON `Digest()`, the `ConnectionSource` interface and `EmptyConnections`. Add the AST guard test for `.Trigger()` reads.
  — DoD: the digest is stable across field order, and the guard fails on an injected `.Trigger()` read in a non-allowlisted file.

- [ ] 5. **`internal/pa/memory`.** The `Store` interface and `NoopMemory`.
  — DoD: `Load` returns empty, `Save` stores nothing, `Forget` is a no-op without error.

- [ ] 6. **`internal/pa/limits`.** The constants, `TruncateToolOutput`, `AdmitToolCalls` (via a store method `AdmitPAToolCall`), the DB-backed rate limiter, the single-in-flight rule and the context budgeter.
  — DoD: unit tests cover each limit at the boundary (4096/4097 runes, 64 KiB exactly and +1 byte, the 8th and 9th tool call).

- [ ] 7. **`internal/pa/output`.**
  - `Sender`: plain text, previews always disabled, keyboards only from template constructors.
  - `Render`: markup strip and URL neutraliser, with `idna` normalisation, `t.me`, `tg://` and bot mentions.
  - Templates: the consent card, hold, rate-limited, still-working and unavailable messages.

  — DoD: a fake Bot API records every request, and table tests cover the T14 cases.

- [ ] 8. **`internal/pa/consent`** (depends on 3, 7). The `pa-data-flow/v1` text with a hash pin test, the consent card, the accept callback resolved under `from.id`, and `/consent` / `/consent withdraw` (one transaction: withdraw, delete state, cancel jobs).
  — DoD: S1-N1..N4 pass.

- [ ] 9. **`internal/pa/convo`** (depends on 3, 5). Provenance classification of an accepted message (user versus external parts), `Load` with fail-closed provenance, the TTL from creation, `/new`, `/forget`, and a PA pass in `internal/sweeper` (expired conversations, `pa_updates` older than 48h).
  — DoD: S1-I2..I4 pass, and the sweeper test deletes only expired rows.

- [ ] 10. **`internal/pa/ingress`** (depends on 6, 8, 9). The webhook handler:
  - constant-time secret check, then the 1 MiB cap, then the raw-key decode;
  - `Classify` and the drop counters;
  - accept plus dispatch in one transaction, with replies sent after commit;
  - `EnsureWebhook` with `allowed_updates=["message","callback_query"]`;
  - `Monitor` (`getWebhookInfo`, metric 0 on mismatch or error).

  Command routing lives in `internal/pa/commands.go`.
  — DoD: S1-B1..B3 pass, and the monitor reports not-OK on a wrong URL, wrong `allowed_updates`, an HTTP error and malformed JSON.

- [ ] 11. **Job token** (depends on 4). Add `PAPrincipal` and `ContextDigest` to `localjwt.Claims`, add `"pa-job"` to `derivedAudiences`, and add a mint helper in `internal/pa/jobs`.
  — DoD: a minted token round-trips, a revoke-by-telegram_id covers `pa-job`, and existing token tests are unchanged.

- [ ] 12. **Claim, turn and reply routes** (depends on 6, 10, 11). Under `/api/pa/v1`:
  - `POST /jobs/claim` (agent-pool only): the global budget lock, consent recheck, a reservation in `pa_usage`, a held state plus one hold message on exhaustion, and filling the context and the signed tool set (empty in Phase 1).
  - `POST /jobs/turn` (pa-job only): the context digest, consent, status and TTL rechecks, and the turn and tool-call counters.
  - `POST /jobs/reply` (pa-job only): an external fragment, `Render`, `Sender`, usage settle.

  Also generalise `usageSums` so `global_day` includes `pa_usage`.
  — DoD: S1-R2..R3 pass, and the existing `agent_usage` budget tests are unchanged.

- [ ] 13. **Worker PA mode** (depends on 12). In `internal/agentworker`, add `AGENT_WORKER_PA=1`: claim from the PA route, call `/jobs/turn` before each model call, build delimited data blocks by provenance, apply a local 8-call cap, and post the reply. It is off by default.
  — DoD: a fake-server worker test covers a one-turn answer, a 409 stop on withdrawal, and the cap.

- [ ] 14. **Wiring** (depends on 10, 12). In `cmd/server/main.go`, mount the webhook and `/api/pa/v1` only when `PA_ENABLED` and the token and secret are set. Start the monitor, and wire `NoopMemory` and `EmptyConnections`.
  — DoD: with no `PA_*` env the route table and goroutine count match today's (test), and with env set the routes respond.

- [ ] 15. **Docs and manifest** (depends on all). Add a `docs/agent-runtime` note on the PA chat loop, and S1 ID markers (`// S1-B1` ...) on each owned test, for #1317's manifest. Update `CHANGELOG.md` through release-please conventions (`feat(pa): ...`).
  — DoD: every owned ID has exactly one test, and a recorded mutation run is listed in the PR description.

## Tests

Each test runs in CI against SQLite and Postgres where it uses the DB, with a fake Bot API and a fake worker. Fixtures use the personas `Alice`, `Bob`, `Carol` and `Dana`, with ids checked by `git grep` first. Each ID has a mutation run that reverts its guard and observes the failure.

- [ ] T1. **S1-B1.** A table of updates is dropped with no job, fragment or reply, each counted under its own reason:
  - `business_message`, `business_connection`, `edited_message`, `channel_post`;
  - group chat, supergroup, channel;
  - `sender_chat`, `via_bot`, `chat.id != from.id`, `from.is_bot`;
  - a callback from a non-private message.
  Mutation: remove the `chat.id != from.id` check.
- [ ] T2. **S1-B2.** The same `update_id` delivered twice (and concurrently) gives one job, one fragment set and one reply. Mutation: drop `ON CONFLICT`.
- [ ] T3. **S1-B3.** A missing, wrong, or same-length-but-different secret gives 401, and nothing is persisted. Mutation: skip the compare.
- [ ] T4. **S1-X1.** `RunPrincipalScopedContract` across every PA store: B cannot list, read, mutate or delete A's conversation, fragment, job, consent, callback or usage rows. A callback id of A tapped by B is refused. Mutation: remove the principal from one WHERE clause.
- [ ] T5. **S1-X2.** A full run for A leaves B's conversations, fragments, consent, `pa_usage` sums, rate window and audit rows unchanged.
- [ ] T6. **S1-I1.** A user message "send hi to @x" yields a claim envelope with an empty or read-only tool set. A worker that proposes `send_message` gets no downstream call (the fake MCP records zero calls).
- [ ] T7. **S1-I2.** Each stored fragment has its own provenance. A mixed message (user text plus a reply-to quote) yields two fragments with different marks.
- [ ] T8. **S1-I3.** Forwarded text, `reply_to_message`, `quote`, a caption and a document placeholder are all `external`.
- [ ] T9. **S1-I4.** A row with an unknown provenance value (inserted via raw SQL on SQLite with the CHECK bypassed by a test-only table copy), or an undecryptable body, loads as `external`.
- [ ] T10. **S1-R1.** These limits are enforced:
  - 4097-rune message refused;
  - tool output over 64 KiB truncated with the marker and kept `external`;
  - context over `PA_MAX_CONTEXT_TOKENS` trimmed oldest-first;
  - rate limit exceeded refused;
  - second in-flight message refused.
- [ ] T11. **S1-R2.** The 9th `AdmitPAToolCall` is refused, `/jobs/turn` returns a stop, and the worker loop ends with a final reply.
- [ ] T12. **S1-R3.** With the budget exhausted, the claim returns no job, the job is `held`, one hold message is sent, and the fake model provider receives zero calls. After the window resets the job is claimable.
- [ ] T13. **S1-N1.** With no consent, a message produces the consent card and no job, and the fake provider receives zero calls.
- [ ] T14. **S1-N2.** An injected consent read error refuses the run, with an unavailable message and no job.
- [ ] T15. **S1-N3.** A stored `pa-data-flow/v0` (or any other version) asks again, with no job. The text-hash pin test fails if the text changes without a version bump.
- [ ] T16. **S1-N4.** `/consent withdraw` deletes the conversation state and cancels queued jobs. An in-flight job's next `/jobs/turn` and `/jobs/reply` are refused, and the provider gets no further call.
- [ ] T17. **S1-O1.** Every request the fake Bot API sees from the PA carries `link_preview_options.is_disabled=true` and no `parse_mode`, including templates, the consent card, hold and error messages.
- [ ] T18. **S1-O2.** The neutraliser handles each of these cases:
  - an unseen `https://attacker.example/?d=x` is neutralised;
  - a user-supplied `https://example.com` followed by a model-added `?q=` is neutralised;
  - `attacker.example/path`, `xn--80ak6aa92e.com`, a Unicode IDN, `t.me/somebot?start=x`, `tg://resolve?domain=x` and `@evilbot` are neutralised;
  - the exact user URL is kept.
- [ ] T19. **S1-O3.** Model output with `[a](https://x.example)`, `<a href>` and `<b>` is rendered without markup. A model cannot produce a `reply_markup`, and template keyboards contain no `url` buttons.
- [ ] T20. **Trigger guard.** The AST test fails when a `.Trigger()` read is added outside the allowlist (the issue's "tiering and approval read only the context").
- [ ] T21. **Regression.** The existing `agent_usage` budget and claim tests and the login bot receiver tests pass unchanged. A `global_day` sum with an empty `pa_usage` equals today's value.

## Rollback

- Nothing deploys in this item. The PA mounts only when `PA_ENABLED`, `PA_BOT_TOKEN` and `PA_WEBHOOK_SECRET` are set, and none is set in `services/labs/mctl-telegram*/values.yaml`. So merging is inert in prod and preview.
- If a regression appears in shared code (`usageSums`, `localjwt.Claims`, `derivedAudiences`, `Migrate`), revert the merge commit and release a patch tag. The new `pa_*` tables are additive and unused, so they can stay. If dropping them is wanted, that is a separate, explicit migration.
- After #1318 activates the PA, the runtime rollback order is: `PA_ENABLED=false` (unmounts the webhook; Telegram's retries fail harmlessly), then `deleteWebhook` for the PA bot, then image rollback. Conversation state expires through its TTL; `/forget` or a manual delete of the `pa_*` rows is a separate, explicit action.
