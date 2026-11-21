# Design: issue-1313-feat-pa-bot-chat-loop-and-executionconte

## Current state

The repository HEAD is `4e8c8f4`, the merge of PR #1311 (Phase 0 docs). Nothing in the tree implements the Personal Assistant: there is no `internal/pa` package and no `PA_*` config. What exists, and what this design reuses or deliberately does not reuse:

- **Login bot ingress: long polling, not a webhook.**
  - `internal/bot/receiver.go` polls `getUpdates` with the login bot token (`cmd/server/main.go:1256-1259`, `cfg.TelegramLoginBotToken`).
  - Its durability lives in `internal/db/bot_updates.go`:
    - `AcceptUpdate` does `ON CONFLICT DO NOTHING` on the `update_id` primary key;
    - `NextOffset` reads `MAX(update_id)`;
    - `DispatchOnce` wraps dispatch and `processed_at` in one transaction.
  - `internal/bot/update.go` decodes only `update_id`, `message` and `callback_query`, with minimal fields: `Chat.ID`, text and entities. It has no `from`, `chat.type`, `sender_chat`, `via_bot` or `forward_origin`.
  - `internal/bot/wiring.go:KnownChatFunc` treats `chatID <= 0` as not private.
  - The table is global to one bot. Its update_id space must not be shared with a second bot.
- **Bot API client.**
  - `internal/botapi/botapi.go:SendMessage` sends plain text **without** disabling link previews.
  - `SendHTMLMessage` sets `parse_mode=HTML` and `link_preview_options={"is_disabled":true}`.
  - Neither fits T14: the PA needs plain text **and** previews disabled on every send.
- **Constant-time secret checks** already follow one pattern: `subtle.ConstantTimeCompare` in `internal/bot/bridge.go:80`.
- **Managed runtime and #1092 ledger** (`internal/db/agent_usage.go`):
  - `ManagedBudget`, `reserveBudget(ctx, tx, userID, limit)` and `insertReservation`;
  - statuses `reserved` / `held` / `settled`;
  - the global advisory lock `managedBudgetLockKey`;
  - windows `global_day`, `account_month`, `account_day`.
  - `agent_usage.user_id`, `agent_jobs.user_id` and `agent_profiles.user_id` are MCTL account ids (`REFERENCES users(id)` in `internal/db/agent_schema.go:466,670,704`).
  - Claims run through `ClaimManagedAgentJobs` (`internal/db/agent_jobs.go:342`, `agent_managed_claim.go`).
- **Job tokens.**
  - `internal/agentapi/events.go:271` defines `jobTokenAudience = "agent-job"`.
  - `internal/auth/localjwt/issuer.go` carries `JobID`, `JobAttempt`, `ConversationID` and `JobTools` (the #1041 signed tool set) as claims.
  - `derivedAudiences = {"bridge","agent","agent-job","agent-pool"}` gives revoke-by-telegram_id coverage.
  - `internal/agentapi/toolgate.go` refuses a route whose tool is outside the signed set.
- **Managed worker.**
  - `internal/agentworker/openairunner.go:OpenAIRunner.Run` runs the tool loop with `MaxTurns` (default 12).
  - It claims from `POST /api/agent/v1/jobs/claim` (`internal/agentapi/server.go:225`).
- **Consent today.** It belongs to managed `AssistantInstall` only: `ManagedConsentVersion` / `ManagedConsentCurrent` in `internal/db/agent_domain.go:107` and `internal/assistantinstall/runtime.go`. ADR 0011 and T13 require the PA consent to be stored separately.
- **Encryption.**
  - `internal/crypto/aesgcm.go` has `SealForUser` / `OpenForUser` with HKDF per-user keys (`deriveKey(master, userID, info)`).
  - `internal/sanitize` has `UserContent`, `Name` and `SensitiveTelegramContent`, but no URL neutraliser.
- **Migrations.**
  - `internal/db/db.go:Migrate` runs `CREATE TABLE IF NOT EXISTS` plus `addColumnIfMissing`.
  - Agent tables live in `internal/db/agent_schema.go:migrateAgent(ctx, conn, pg)`, with separate SQLite and Postgres DDL.
- **Redaction.** `internal/audit/redact.go:sensitiveKeys` is matched case-insensitively.
- **Dependencies.** `go.mod` already has `golang.org/x/net` (for `idna`) and `golang.org/x/time` (for `rate`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram/values.yaml`:
  - tenant `labs`, host `tg.mctl.ai`, `replicaCount` 1 (comment at line 368);
  - `AGENT_ENABLED: "true"`;
  - the ExternalSecret maps `TELEGRAM_LOGIN_BOT_TOKEN`;
  - **no** `PA_*` variable and no PA bot token.
- `$MCTL_GITOPS_ROOT/services/labs/mctl-telegram-preview/values.yaml`:
  - `MANAGED_RUNTIME_ENABLED: "true"`, `MANAGED_RUNTIME_MAX_ACCOUNTS: "1"`;
  - `MANAGED_BUDGET_USD_PER_ACCOUNT_DAY: "1.00"`, `MANAGED_BUDGET_USD_GLOBAL_DAY: "5.00"`, `MANAGED_MAX_JOB_COST_USD: "0.25"`;
  - comment: no pool worker runs until activation step A5;
  - no `PA_*` variable.
- `$MCTL_GITOPS_ROOT/services/labs/agent-worker-managed-preview/values.yaml` exists; only its rollback comment was read.
- `gh issue view 1312/1315` (read-only):
  - the epic records an owner GO, dated 2026-11-18, for #1313 implementation only, and HOLD on preview deployment and activation;
  - #1315 owns S1-X3..X4 and S1-U1..U3 and the executor.
- The mctl MCP read tools were not called. The gitops checkout answered every deployed-config question this design needs, and the design changes no deployed config.

## Proposed solution

### Package layout

The ADR places the PA in a new package next to `internal/bot` and `internal/agentworker`:

    internal/pa/
      ingress/      webhook handler, update decoding, filter, webhook registration and monitor
      execctx/      ExecutionContext, Trigger, digest
      convo/        conversation and fragment store facade, provenance, TTL, /new, /forget
      memory/       MemoryStore interface + NoopMemory
      consent/      pa-data-flow/v1 text, version, accept/withdraw flow
      limits/       size caps, tool-call cap, rate limiter, TruncateToolOutput
      output/       Sender (Bot API, previews off, no parse_mode), Render (URL neutraliser, markup strip), server templates
      jobs/         HTTP routes for the pool worker: claim, turn admission, reply
      commands.go   /start /help /new /forget /consent /consent withdraw dispatch
    internal/db/pa_schema.go   migratePA(ctx, conn, pg) + store methods (pa_*.go)

The PA has its own durable tables. It shares nothing with the login bot's `bot_updates`, because the update_id spaces of two bots collide.

### Ingress (T4)

- **Route.** `POST /pa/bot/webhook` is mounted on the main chi router only when `cfg.PABotToken != ""` and `cfg.PAWebhookSecret != ""`. Both come from new env vars `PA_BOT_TOKEN` and `PA_WEBHOOK_SECRET`. Both are added to `sensitiveKeys` in `internal/audit/redact.go`.
- **Handler order.** Each step either refuses or passes to the next:
  1. `subtle.ConstantTimeCompare` of `X-Telegram-Bot-Api-Secret-Token` against the secret. A mismatch gets 401, with nothing read or stored (S1-B3).
  2. `http.MaxBytesReader` at 1 MiB, then a JSON decode into `ingress.RawUpdate`. That type keeps the set of top-level keys (`map[string]json.RawMessage`), so unknown kinds are detectable.
  3. `ingress.Classify(raw) (Accepted, DropReason)`:
     - any top-level key outside `{update_id, message, callback_query}` is `drop:kind`;
     - a message is checked for `chat.type=="private"`, `from != nil`, `!from.is_bot`, `chat.id == from.id`, `sender_chat == nil` and `via_bot == nil`;
     - a callback_query is checked for `message != nil`, a private message chat, and `message.chat.id == from.id`.
     Each drop reason is a counter label (`mctl_pa_updates_total{kind,outcome}`), never a log line with content.
  4. `store.AcceptPAUpdate(ctx, updateID, kind, principal)`, `ON CONFLICT (update_id) DO NOTHING`. A duplicate returns 200 immediately (S1-B2). Dropped updates are recorded too, so a retried drop is cheap.
  5. Dispatch to the command or message handler **inside the accept transaction**. Any job, fragment or consent mutation commits atomically with the `update_id` row. Bot replies are sent after commit; a failed send is counted, not retried into a duplicate run.
  6. Answer 200. Telegram retries only on non-2xx. A handler error answers 500, and because the transaction rolled back, the retry re-runs cleanly.
- **Webhook registration.** `ingress.EnsureWebhook` runs at startup when `PA_WEBHOOK_URL` is set. It calls `setWebhook` with:
  - `url` = `PA_WEBHOOK_URL`;
  - `secret_token`;
  - `allowed_updates=["message","callback_query"]`;
  - `max_connections=10`.
- **Webhook monitor.** `ingress.Monitor` calls `getWebhookInfo` every 5 minutes. It compares the URL and `allowed_updates`, and exports `mctl_pa_webhook_info_ok` (1/0) and `mctl_pa_webhook_info_last_error_timestamp`. An unreadable or unparseable result sets 0 (I9). The alert rule itself is gitops work under #1318.
- **Message classification.** This is the T5 provenance at ingress:
  - `message.text` with no `forward_origin` becomes a `user` fragment.
  - Forward origin, `reply_to_message.text`, `quote.text`, `caption`, and a placeholder for media or documents become `external` fragments.
  - A text starting with `/` that matches a known command is handled by the server and never becomes a fragment, so the model cannot see or issue it.

### ExecutionContext

```go
// internal/pa/execctx
type Trigger struct{ kind string } // unexported field; only Interactive() is constructible in Phase 1
func Interactive() Trigger

type ConnectionRevision struct{ ConnectionID int64; AuthorityRevision int64 }

type ExecutionContext struct {
    Principal       int64                // Telegram user id from the filtered update (I2)
    trigger         Trigger              // read only through Trigger() by audit labelling
    ConversationID  int64
    Connections     []ConnectionRevision // empty until #1314
    ReservationID   int64                // pa_usage row, set at claim
    ConsentVersion  string               // "pa-data-flow/v1"
    JobID           int64
    Attempt         int
    ToolSet         []string             // signed tool set; empty in Phase 1 until #1315
}
func (c ExecutionContext) Digest() [32]byte // SHA-256 of canonical JSON, stored on the job and in the token
```

- **Persistence.** The context is persisted as `pa_jobs.execution_context` (canonical JSON), with the digest in `pa_jobs.context_digest`. Every server-side PA decision loads the context from the job row by `(principal, job_id)` taken from the token. Request fields never supply it.
- **Trigger is read only by audit.** The issue requires that tiering and approval code read only the context, never the trigger. Two mechanisms enforce it:
  - the trigger is unexported with an accessor;
  - `internal/pa/execctx/trigger_guard_test.go` parses every Go file under `internal/pa/...` with `go/ast` and fails on any `.Trigger()` call outside an allowlist (the audit label helper).
  Phase 2 approval code inherits the guard automatically.
- **Connection revisions.** `Connections` is filled at claim from a `ConnectionSource` interface. Phase 1 uses `EmptyConnections{}`; #1314 supplies the real one. The source returns `(nil, err)` on a read failure, and the claim refuses (I9).

### Job token (`aud=pa-job`)

- **Claims.** Extend `localjwt.Claims` with `PAPrincipal int64 \`json:"pa_principal,omitempty"\`` and `ContextDigest string \`json:"ctx,omitempty"\``. The existing `JobID`, `JobAttempt`, `ConversationID` and `JobTools` fields are reused.
- **Minting.** On claim, `internal/pa/jobs` mints `aud=["pa-job"]` with the TTL of the job lease. `"pa-job"` is added to `derivedAudiences` so revoke-by-telegram_id reaches it.
- **Routes in this item.** The routes added here (`/api/pa/v1/jobs/{turn,reply}`) accept **only** `pa-job`. Claim accepts only `agent-pool`. The general refusal tests on executor and agent routes (S1-X3..X4) belong to #1315.

### Jobs and the worker loop

Three tables carry the loop:
- `pa_jobs`: `id`, `principal`, `conversation_id`, `update_id`, `status` (`pending|held|claimed|done|cancelled|expired`), `attempts`, `turns`, `tool_calls`, `execution_context`, `context_digest`, `claimed_at`, `expires_at`, `created_at`.
- `pa_usage`: `id`, `job_id`, `attempt`, `principal`, `reserved_usd`, `cost_usd`, `status`, `created_at`, `updated_at`.
- `pa_rate`: `principal`, `window_start`, `count`.

HTTP routes under `/api/pa/v1`, mounted only when the PA is configured:
- **`POST /jobs/claim`** (agent-pool token).
  1. In one transaction, take `managedBudgetLockKey` (same lock as #1092), then the per-principal lock.
  2. Pick the oldest `pending` job, or a `held` job whose window reset, that is not expired.
  3. Re-check consent; a missing one cancels the job.
  4. Compute room under the windows:
     - `global_day`, summed over **both** `agent_usage` and `pa_usage` by generalising `usageSums`;
     - `principal_day` and `principal_month` over `pa_usage`.
  5. If there is room: insert the `pa_usage` reservation, fill `ReservationID`, `Connections` and `ToolSet` into the context, mint the token and return the job envelope. The envelope carries the conversation fragments with provenance tags and the catalog-authored tool definitions; it is empty in Phase 1.
  6. With no room: set `held` and queue one hold message per job ("budget for today is used up; your request is held until HH:MM UTC"). No token is minted and no model call happens (S1-R3).
- **`POST /jobs/turn`** (pa-job). The worker calls it before **every** model call.
  1. Load the job by `(token.PAPrincipal, token.JobID, token.JobAttempt)` and compare `context_digest`.
  2. Re-check consent (S1-N4), job status, and the conversation's existence and TTL.
  3. Increment `turns`. The body may declare `tool_calls_proposed`; `limits.AdmitToolCalls` increments `tool_calls` atomically and refuses beyond 8.
  4. A refusal returns 409 `{"stop":"<reason>"}`; the worker must then stop and post a final reply or abandon.
  `store.AdmitPAToolCall(principal, jobID)` is exported, and #1315's executor must call it before dispatch. The cap therefore holds server-side even against a non-cooperating worker (S1-R2).
- **`POST /jobs/reply`** (pa-job).
  1. Re-check consent and status.
  2. Store the model output as an `external` fragment.
  3. Run `output.Render(text, userURLs)`, where `userURLs` is the set of URLs extracted from `user` fragments of this conversation.
  4. Send it through `output.Sender`.
  5. Settle usage through `RecordPAJobUsage`, which mirrors `RecordAgentJobUsage`.
  6. Mark the job `done`.

**Worker side.** `internal/agentworker` gets a `PAMode` (env `AGENT_WORKER_PA=1`) that:
- claims from `/api/pa/v1/jobs/claim`;
- builds messages from the envelope, with fragments wrapped as delimited data by provenance;
- calls `/jobs/turn` before each `chatWithRetry`;
- caps its own loop at 8 tool calls, as defence in depth;
- posts `/jobs/reply`.
Tool execution goes to #1315's executor route. In Phase 1, before #1315, the tool definitions are empty, so the model can only answer.

### Conversation state and provenance (T5)

- **Schema.**
  - `pa_conversations`: `id`, `principal`, `created_at`, `expires_at`, `deleted_at`.
  - `pa_fragments`: `id`, `principal`, `conversation_id`, `seq`, `role` (`user_msg|model|tool|context`), `provenance TEXT NOT NULL CHECK (provenance IN ('user','external'))`, `body_encrypted`, `created_at`.
- **Encryption.** Bodies are sealed with a new `crypto.SealForPrincipal(plaintext, principal, "mctl-pa-conversation/v1")`, which reuses `deriveKey` with a distinct HKDF info. Telegram ids and MCTL user ids therefore never share a key space.
- **Loading.** `convo.Load(principal, convID)` returns `[]Fragment{Provenance, Text}`. An unknown provenance value or a decrypt failure yields `Provenance=external`, and a decrypt failure also yields the placeholder text `[unreadable]` (S1-I4). An expired conversation reads as absent.
- **TTL.** `expires_at = created_at + PA_CONVERSATION_TTL` (default 24h). The existing `internal/sweeper` pattern gets a PA sweep that hard-deletes expired conversations, their fragments, and `pa_updates` older than 48 h.
- **`/new` and `/forget`.**
  - `/new` deletes the active conversation and its fragments, then creates a new one.
  - `/forget` deletes every conversation of the principal, cancels `pending|held` jobs and calls `memory.Forget`.
  - Both run in the update's accept transaction.
- **Memory.** `memory.Store` is an interface with `Load(ctx, ec ExecutionContext) ([]Fragment, error)`, `Save(ctx, ec, []Fragment) error` and `Forget(ctx, principal) error`. `NoopMemory` is the only implementation and is wired in `cmd/server/main.go`.
- **Taint.** Taint bookkeeping is Phase 2. In Phase 1 the run envelope carries `tainted = any external fragment`, so the field and its fail-closed read exist. Nothing gates on it yet, because no write path exists (S1-I1).

### Consent (T13)

- **Schema.** `pa_consents`: `principal PRIMARY KEY`, `version`, `granted_at`, `withdrawn_at`. The table is separate from `agent_profiles`.
- **Text.** `consent.Current = "pa-data-flow/v1"`. The text lives in `internal/pa/consent/text.go` and names the provider class, the data categories and the retention. A test pins its hash to the version string, so editing the text without bumping the version fails CI (S1-N3 support).
- **Accept flow.** Any non-command message without current consent gets the consent card. Its keyboard comes from `output.ConsentKeyboard(callbackID)`. The `callback_data` is a 128-bit random id stored in `pa_callbacks(id, principal, kind, expires_at, used_at)`. It is resolved by `(from.id, id)` and is single use.
- **Refusals.** A read error gives a "temporarily unavailable" message and no job (S1-N2).
- **`/consent withdraw`.** In one transaction it sets `withdrawn_at`, deletes conversations and fragments, and cancels `pending|held|claimed` jobs. Turn admission and reply re-check consent, so an in-flight run stops at its next model call (S1-N4).

### Limits (T10)

`internal/pa/limits`:
- `MaxMessageChars=4096` (rune count, checked at ingress);
- `MaxToolOutputBytes=64<<10` with `TruncateToolOutput` appending `\n[truncated by mctl]`;
- `MaxToolCallsPerRun=8`;
- `MaxContextTokens` (env, default 32000; the estimate is bytes/4, conservative). The envelope builder drops the oldest fragments first, and never drops the triggering message.
- Phase 2 constants `MaxApprovalCardBytes=4096` and `MaxAlicePhraseChars=1000` are defined but unused.

The per-principal rate limit is DB-backed through `pa_rate` (fixed window, `PA_RATE_MESSAGES`/`PA_RATE_WINDOW`), so it survives restarts and later replicas. It also allows at most one `pending|claimed` job per principal.

### Output hardening (T14)

- **`output.Sender`** wraps an `http.Client` and the PA token. It has two methods:
  - `Send(ctx, principal, text, kb *Keyboard)`: always `link_preview_options={"is_disabled":true}`, never `parse_mode`. The `reply_markup` is built only from `*Keyboard`, a type whose constructors live in `output/templates.go` and produce `callback_data` buttons only.
  - `AnswerCallback`.
  Model text cannot construct a `Keyboard`. Every PA send goes through `Sender`; a test asserts that there is no other `sendMessage` call site under `internal/pa` (S1-O1).
- **`output.Render(text, userURLs)`** runs three steps:
  1. Strip markup: `[label](url)` becomes `label url`, HTML tags are removed, and Markdown emphasis markers are left as literal text because no parse_mode is set.
  2. Tokenise URL candidates with a single scanner covering:
     - `scheme://...`;
     - `tg://...`;
     - bare `host.tld[/...]`, where the TLD is alphabetic with at least 2 letters or `xn--`;
     - IDN hosts normalised with `idna.Lookup.ToASCII`;
     - `t.me/...` and `telegram.me/...`;
     - `@name` ending in `bot`.
  3. Keep a candidate only if its exact original string is in `userURLs`. Otherwise neutralise it: drop the scheme, replace `.` in the host with `[.]`, replace `://` with `[:]//`, and render `@xbot` as `@ xbot`. A user host plus an appended query is not an exact match, so it is neutralised (S1-O2).

### Cross-user isolation (S1-X1..X2)

- **Scoped store methods.** Every `pa_*` store method takes `principal` as its first argument and puts it in the WHERE clause, including deletes and updates.
- **Shared contract test.** `internal/db/pa_isolation_contract_test.go` defines `RunPrincipalScopedContract(t, store)`. For each PA store it seeds rows for A and B, then shows that B's list, read, mutate and delete calls on A's ids behave as "not found" and leave A's rows untouched (S1-X1). #1314's connection store adds itself to this contract.
- **Run isolation.** S1-X2 runs a full A run (fake Bot API, fake worker), then asserts that B's conversations, fragments, consent, `pa_usage` sums, rate window and audit rows are byte-identical before and after.

### Config

New fields in `internal/config/config.go`. Everything is empty or off by default, and the PA mounts nothing unless the token, secret and `PA_ENABLED` are all set:
- `PA_ENABLED`;
- `PA_BOT_TOKEN`, `PA_WEBHOOK_SECRET`, `PA_WEBHOOK_URL`;
- `PA_CONVERSATION_TTL`;
- `PA_RATE_MESSAGES`, `PA_RATE_WINDOW`;
- `PA_MAX_CONTEXT_TOKENS`;
- `PA_BUDGET_USD_PER_JOB`, `PA_BUDGET_USD_PER_PRINCIPAL_DAY`, `PA_BUDGET_USD_PER_PRINCIPAL_MONTH`.

The full switch semantics (`PA_EXTERNAL_TOOLS_ENABLED`, per-server flags, dispatch recheck) belong to #1318. Validation rules:
- `PA_BOT_TOKEN` equal to `TELEGRAM_LOGIN_BOT_TOKEN` is a startup error, to keep the blast radius separate (ADR 0011);
- a `PA_WEBHOOK_SECRET` shorter than 32 characters, or outside Telegram's `[A-Za-z0-9_-]` set, is an error.

### Test manifest

Each S1 ID owned here is mapped to a test function in the checked-in manifest that #1317 assembles. Each test carries a `// S1-XX` marker comment so the manifest checker can find it:
- B1..B3, X1..X2, I1..I4, R1..R3, N1..N4, O1..O3.

## Alternatives

1. **Reuse the login bot's long-poll receiver and `bot_updates` table for the PA bot.**
   - Dropped. ADR 0011 requires a separate bot, and the issue requires a webhook with a secret token.
   - Two bots' `update_id` spaces would collide in one table, and `NextOffset` assumes a single bot.
   - The login receiver's `Update` type also lacks `from`, `chat.type`, `sender_chat`, `via_bot` and `forward_origin`. Widening it would change a hardened surface for no gain.
2. **Store PA jobs and usage in `agent_jobs` / `agent_usage`.**
   - Dropped. Both tables `REFERENCES users(id)`. A PA principal is a Telegram id that may have no MCTL account (T4).
   - Reusing them would force fake account rows, or nullable foreign keys on a hardened ledger. It would also mix two security models in one queue (ADR 0011 rejects extending `AssistantInstall` for the same reason).
   - Separate tables that share the global budget lock and the global-day window keep one platform cap without that coupling.
3. **Run the model loop inside mctl-telegram instead of on the managed worker.**
   - Dropped. ADR 0011 places the model on the ADR 0008 managed runtime.
   - Running provider calls in the server process would put provider credentials, and the long-lived calls, inside the process that holds downstream OAuth tokens. That weakens I1's separation.
4. **Check consent and limits only at ingress.**
   - Dropped. The threat model requires withdrawal to stop every further model call (S1-N4) and the tool-call cap to stop the loop (S1-R2).
   - Only server-side checks on each turn and tool call achieve that against a worker that might not cooperate.

## Platform impact

- **Migrations.**
  - New tables only: `pa_updates`, `pa_conversations`, `pa_fragments`, `pa_consents`, `pa_callbacks`, `pa_jobs`, `pa_usage`, `pa_rate`. They are added via a new `migratePA` called from `Migrate`, with SQLite and Postgres DDL, and `CREATE TABLE IF NOT EXISTS` makes them idempotent.
  - No existing table changes.
  - `usageSums` is generalised to add `pa_usage` to the `global_day` window. When `pa_usage` is empty, the sum is unchanged; a regression test pins existing behaviour.
  - `migrate_cached.go` templates must include the new tables.
- **Backward compatibility.**
  - With no `PA_*` env set, nothing mounts and no goroutine starts.
  - The new JWT claims are `omitempty` and ignored by existing verifiers.
  - Adding `"pa-job"` to `derivedAudiences` only widens revocation coverage.
- **Resource impact.** One extra goroutine (webhook monitor, 5-minute period), one sweeper pass, and small tables bounded by TTL. Deployment is `replicaCount` 1 today; the design keeps all dedup and rate state in the DB, so it remains correct with more replicas.
- **Risks and mitigations.**
  - *A second bot token in the process.* The token comes from a separate env var, is redacted, and cannot equal the login token.
  - *A webhook endpoint exposed on the public host.* The constant-time secret check runs before parsing, with a 1 MiB body cap. Before #1318 sets `PA_*` it is unmounted, so it does not exist in prod.
  - *Shared global budget.* PA spend can consume the managed global-day window. That is intended (one platform cap) and visible in the `global_day` scope counter.
  - *URL neutraliser false positives* (for example `file.txt`). These are acceptable: the neutralised form is still readable, and safety wins over fidelity (T14).
  - *Worker changes affect the managed worker image.* `PAMode` is off unless `AGENT_WORKER_PA=1`, and no PA worker is deployed in this item.
- **Deployment.** None in this item. Vault secret, ExternalSecret, env vars, `setWebhook` and the alert rule are #1318's, under a separate owner GO.

## Open questions

- Ledger subject and PA budget env vars: see requirements.md.
- TTL anchor (creation versus last activity).
- S1-X1 split with #1314.
- Rate-limit and context-cap default values.
- Running the PA worker mode inside the existing managed worker image.
- The mctl MCP read tools were not called. The deployed state above comes from the gitops checkout only, so live runtime state (for example whether a managed pool worker is currently running) was not observed.
