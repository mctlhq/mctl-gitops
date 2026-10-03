# Design: issue-438-feat-clients-model-notification-identity

## Current state

### The client projection already exists

`users` is the client row. Its base DDL (`internal/db/db.go`, `pgSchema()` L578-584 /
`sqliteSchema()` L459-465) is only `id, github_login, email, provider, created_at`; every
Telegram-native column was bolted on later through the idempotent ALTER pass inside `Migrate`
(`internal/db/db.go:166-189`):

```go
addColumnIfMissing(ctx, dbConn, pg, "users", "telegram_login_id",      "BIGINT", "INTEGER")
addColumnIfMissing(ctx, dbConn, pg, "users", "telegram_username",      "TEXT",   "TEXT")
addColumnIfMissing(ctx, dbConn, pg, "users", "telegram_display_name",  "TEXT",   "TEXT")
addColumnIfMissing(ctx, dbConn, pg, "users", "access_tier",            "TEXT",   "TEXT")
```

There are no numbered migration files and no version table for the core schema: `db.Migrate`
re-probes the dialect, replays `CREATE TABLE IF NOT EXISTS`, replays `addColumnIfMissing`, runs a few
idempotent backfill `UPDATE`s (`internal/db/db.go:246-284`), then delegates the agent domain to
`migrateAgent` (`internal/db/agent_schema.go:23`), which uses the same dual-dialect statement-list +
`addColumnIfMissing` shape. Any new column or table in this proposal follows exactly that pattern.

`db.IdentityRow` (`internal/db/store.go:288-302`) is the admin-facing projection:
`TelegramID, Username, DisplayName, AccessTier, HasSession, CreatedAt, ConnectedVia`. It is built by
`Store.ListIdentities` (`internal/db/store.go:409-488`) in two queries: one over `users` with an
`EXISTS` subquery against `telegram_accounts` (honouring both the idle and absolute session TTLs and
the TTL-exempt allowlist), and a second `GROUP BY` over `oauth_refresh_tokens.client_name` merged in
memory through an index built by `TelegramID` — the O(n)-merge precedent this proposal reuses.

The projection is exposed by `toolListIdentities` (`internal/mcp/tools.go:1054-1084`), registered at
`internal/mcp/server.go:265`, gated with
`requireAnyScope(id, "admin:users", "admin:users:read")` (`internal/mcp/tools.go:1073`,
helper at `internal/mcp/tools.go:1872-1882`). `admin:users:read` is the read-only lookup tier resolved
from `TG_LOGIN_LOOKUP_ADMINS` in `oauth.Server.ResolveScopes`
(`internal/oauth/server.go:1037-1146`, the lookup branch at L1124-1126); `internal/config/config.go:72`
documents that it is deliberately not the flat `admin:users`. The self-service counterpart is
`toolGetMyIdentity` (`internal/mcp/tools.go:954-996`), which requires no scope and returns
`{telegram_id, username, display_name}` via `Store.GetLoginIdentity`.

### Where identity attributes come from, and where they are lost

Telegram's OIDC `id_token` gives the broker exactly five claims
(`internal/auth/telegramoidc/oidc.go:198-204`): `id`, `sub`, `username`, `first_name`, `last_name`.
There is no `language_code`. The only `LangCode` in the repository is the hardcoded `"en"` this service
sends in its own MTProto client config (`internal/telegram/login.go:123-124`,
`internal/telegram/loginqr.go:56-57`), which describes us, not the user.

`internal/oauth/server.go:1597` then flattens first and last name into one string before persisting:

```go
uid, err := s.store.EnsureUserByTelegramID(r.Context(), identity.TelegramID, identity.Username,
    strings.TrimSpace(identity.FirstName+" "+identity.LastName))
```

and `Store.EnsureUserByTelegramID` (`internal/db/store.go:189-237`) makes it worse:

```go
effectiveUsername := username
if effectiveUsername == "" {
    effectiveUsername = displayName
}
```

so `users.telegram_username` may hold a display name. The result is the two defects the issue reports:
the digest's `name := r.Username; if name == "" { name = r.DisplayName }; if name == "" { name = "(no username)" }`
(`internal/digest/digest.go:125-131`) degrades to `(no username) — id …`, and nothing distinguishes
"Telegram supplied no @handle" from "this row predates capture" from "this row's username field is
actually a display name".

The Local Bridge activation path performs the same flatten at
`internal/oauth/local_bridge_activate.go:1037-1038`.

### There is no reachability model and no bot update receiver

The only Telegram Bot API call in the entire repository is outbound:
`digest.sendTelegramMessage` (`internal/digest/digest.go:147-177`) POSTs to
`https://api.telegram.org/bot<token>/sendMessage`. It carefully unwraps `*url.Error` so the bot token
cannot leak into logs, reads at most 512 bytes of the error body, and returns it as an unstructured
`error`; `runDigest` (`internal/digest/digest.go:88-93`) logs `"digest: send failed"` and moves on.
The delivery outcome — the one legitimate, non-probing reachability signal that exists today — is
thrown away.

There is no `getUpdates` poller and no webhook handler for the login bot: a grep for
`getUpdates`/`setWebhook`/`BotToken` finds only `config.TelegramLoginBotToken`
(`internal/config/config.go:69,277`) and the `digest.StartDailyDigest` wiring at
`cmd/server/main.go:857-860`. The digest's recipients are `cfg.TGLoginAdmins`, not clients.

### There is no notification state

Table inventory (grep of `CREATE TABLE IF NOT EXISTS` across `internal/db`) has no notification
preference table. `owner_notifications` exists but belongs to the communication-agent domain
(`internal/db/agent_schema.go`) and is operator-facing — a name this proposal must not collide with.

### Existing self-service surface

`internal/web/account.go` defines `AccountHandlers`, mounted at `/api/account`, with
`Register` binding `GET /`, `POST /disconnect`, `DELETE /`, `GET /audit`, `GET /audit/verify`
(`internal/web/account.go:47-58`). Every handler resolves `auth.From(r.Context())`, 401s when absent,
and writes an audit row through `h.audit(...)` so `/api/account` calls appear in `get_my_audit_log`.
`internal/web/manage.go` renders the HTML dashboard at `/telegram/connect/manage`
(`ManageServer.HandleManage`, `managePageData`), which already carries a self-service `send_enabled`
toggle. Both are gated by the `account:manage` scope granted to the client tier in `ResolveScopes`.

### Deletion contract

`Store.HardDeleteAccount` (`internal/db/store.go:769-814`) runs in one transaction: count active
`telegram_accounts`, `DELETE FROM telegram_accounts`, then `purgeAgentData(ctx, tx, userID)` —
with an explicit comment (L798-802) that the agent tables nominally cascade on `users(id)` but must be
deleted explicitly because **the `users` identity row deliberately survives account deletion**. Any new
consent state keyed on `users.id` must be purged the same explicit way or it outlives the deletion.

### Logging and audit invariants

`audit.sensitiveKeys` (`internal/audit/redact.go:30-74`) redacts slog attribute values by key;
`audit.ScrubText` masks `@handles` and phone-like digit runs in free text. Names (`username`,
`display_name`, `first_name`, `last_name`) are not currently in the list. Separately,
`internal/db/db.go:127-137` documents a hard constraint: **never add a column with a non-NULL default
to `audit_logs`**, because `hashAuditEntry`'s canonical field order
(`internal/db/audit_chain.go:17-57`) would change retroactively and `VerifyAuditChain` would report the
whole chain as tampered.

## Proposed solution

Three additions, all additive, all inside the existing projection.

### 1. Identity attributes with explicit provenance (`users`)

Add via `addColumnIfMissing` next to the existing block in `internal/db/db.go:166-189`:

| column | PG | SQLite | meaning |
|---|---|---|---|
| `telegram_first_name` | `TEXT` | `TEXT` | verified `first_name` claim |
| `telegram_last_name` | `TEXT` | `TEXT` | verified `last_name` claim |
| `telegram_language_code` | `TEXT` | `TEXT` | reserved; no verified source today |
| `identity_source` | `TEXT` | `TEXT` | `telegram_oidc` / `local_bridge_activation` / `admin_tool` / `backfill_legacy` |
| `identity_captured_at` | `TIMESTAMPTZ` | `DATETIME` | when capture last ran |
| `onboarding_completed_at` | `TIMESTAMPTZ` | `DATETIME` | first finalised session |
| `last_seen_at` | `TIMESTAMPTZ` | `DATETIME` | last authentication |

All nullable, no defaults — mirroring the `audit_logs.call_path` reasoning that a non-NULL default
would make pre-existing rows indistinguishable from newly written ones.

**The provenance rule is the whole point of the feature.** A reader answers three-valued, not
two-valued:

- `identity_captured_at IS NULL` → provenance `unknown`: capture/backfill never ran for this row. Empty
  attributes say nothing.
- `identity_captured_at` set and the attribute empty → `not_supplied`: Telegram genuinely did not send it.
- attribute non-empty → `supplied`, attributable to `identity_source`.

This is expressed once, in Go, as `db.AttributeProvenance` and a helper
`db.ResolveIdentityProvenance(row)` so every consumer agrees.

`Store.EnsureUserByTelegramID` gains a sibling that takes a struct rather than growing more positional
parameters:

```go
type TelegramIdentityCapture struct {
    TelegramID  int64
    Username    string
    FirstName   string
    LastName    string
    Source      string
    CapturedAt  time.Time
}
func (s *Store) EnsureUserByTelegramCapture(ctx context.Context, c TelegramIdentityCapture) (int64, error)
```

It keeps the existing `INSERT ... ON CONFLICT DO NOTHING` + `SELECT` race-safe shape and the
`COALESCE(NULLIF($1,''), col)` refresh, and additionally writes the new columns, always stamping
`identity_captured_at`/`identity_source`. Critically it writes `telegram_username` **without** the
`effectiveUsername := displayName` fallback, and derives `telegram_display_name` from
`TrimSpace(FirstName + " " + LastName)`. The old `EnsureUserByTelegramID` stays, unchanged, for the
three call sites that genuinely have only a username (`internal/auth/localjwt/issuer.go:293`,
`internal/oauth/server.go:2018`, `internal/mcp/tools.go:1480`) so no behaviour changes under them.

Call sites switched to the new capture: `internal/oauth/server.go:1597` (source `telegram_oidc`) and
`internal/oauth/local_bridge_activate.go:1038` (source `local_bridge_activation`). Both already hold
`identity.FirstName` / `identity.LastName` and currently discard the split.

`telegram_language_code` is added but left empty and reported `not_supplied`, because no verified
source exists: the `idTokenClaims` struct has no such claim and `internal/telegram/login.go:123`'s
`LangCode: "en"` is our own client's locale. Adding the column now means the backfill story is already
in place if a source is later approved (see Open questions in `requirements.md`).

Backfill inside `Migrate`, using the same idempotent in-`Migrate` `UPDATE` precedent as
`last_used_at`/`expires_at` (`internal/db/db.go:246-284`):

```sql
UPDATE users SET onboarding_completed_at = (
    SELECT MIN(ta.connected_at) FROM telegram_accounts ta
     WHERE ta.user_id = users.id AND ta.revoked_at IS NULL AND ta.telegram_user_id IS NOT NULL)
 WHERE onboarding_completed_at IS NULL;

UPDATE users SET identity_source = 'backfill_legacy'
 WHERE identity_source IS NULL AND telegram_login_id IS NOT NULL;
```

Note what the backfill deliberately does **not** do: it never splits `telegram_display_name` into first
and last name, because that column may already contain a username-fallback value written by the current
`effectiveUsername` behaviour. Legacy rows are honestly labelled `backfill_legacy` with
`identity_captured_at` left NULL, so their empty first/last name reads as `unknown`, not as
"Telegram did not supply it". They self-heal to `telegram_oidc` on the client's next login.

### 2. Bot reachability as its own table

```sql
CREATE TABLE IF NOT EXISTS client_bot_reachability (
    user_id      BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    state        TEXT NOT NULL DEFAULT 'unknown',  -- unknown|reachable|blocked|cannot_initiate
    reason_code  TEXT NOT NULL DEFAULT '',         -- normalised, e.g. bot_blocked, chat_not_found
    observed_at  TIMESTAMPTZ,
    source       TEXT NOT NULL DEFAULT '',         -- digest_delivery|bot_update|admin_tool
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

A separate table rather than columns on `users` because it is a per-bot fact about a communication
channel, not an identity attribute; it churns on every delivery while `users` should not; and it can be
purged on account deletion without touching the surviving identity row.

New package `internal/notify` holds the classifier and the sender seam:

```go
type DeliveryOutcome struct { State string; ReasonCode string; Conclusive bool }

// ClassifyDelivery is pure and offline-testable, mirroring telegramoidc.parseIdentity.
func ClassifyDelivery(httpStatus int, description string) DeliveryOutcome
```

Mapping, derived from what `sendTelegramMessage` can actually observe:

| observation | state | conclusive |
|---|---|---|
| HTTP 200 | `reachable` | yes |
| 403 `bot was blocked by the user` | `blocked` | yes |
| 403 `user is deactivated` / `bot can't initiate conversation with a user` | `blocked` / `cannot_initiate` | yes |
| 400 `chat not found` | `cannot_initiate` | yes |
| 429, any 5xx, transport error | unchanged | **no** |

`Conclusive == false` must leave the stored state alone: a 429 or a pod-level network blip is not
evidence the user blocked the bot. `Store.RecordBotReachability(ctx, userID, outcome, source)`
upserts only for conclusive outcomes.

`digest.sendTelegramMessage` is changed to return a typed `*notify.APIError{StatusCode, Description}`
instead of a formatted string, preserving the existing `*url.Error` unwrap so the bot token can never
reach a log. `runDigest` (`internal/digest/digest.go:88-93`) resolves the recipient chat id to a
`users.id` via `Store.UserIDByTelegramID` and calls `RecordBotReachability`. Only the normalised
`reason_code` is persisted — never the raw response body, which is already truncated to 512 bytes but
is still attacker-influenced Telegram text.

This wires the one sender that exists. Because the digest sends to `cfg.TGLoginAdmins`, ordinary
clients will legitimately sit at `unknown` until a product sender exists (a non-goal here) or a bot
update receiver is added (out of scope). That is the honest outcome the issue asks for: a login is not
proof of reachability, and **no probe is sent merely to classify**. An admin escape hatch —
`source = admin_tool` — lets an operator record a reachability fact they learned out of band.

### 3. Notification preferences

```sql
CREATE TABLE IF NOT EXISTS client_notification_prefs (
    user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category    TEXT NOT NULL,   -- product_updates|maintenance|security
    state       TEXT NOT NULL,   -- subscribed|unsubscribed
    source      TEXT NOT NULL,   -- self_service_web|account_api|mcp_tool|admin_tool
    decided_at  TIMESTAMPTZ NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, category)
);
```

Row-per-category, not a JSON blob, so `decided_at` and `source` are per-category and queryable on both
dialects (SQLite has no JSONB).

Defaults are resolved in Go by `db.ResolveNotificationPrefs`, never written as rows, so
"never decided" stays distinguishable from "decided, then unsubscribed":

- `product_updates` → `unsubscribed`, `explicit=false`. Marketing consent must be an affirmative act.
- `maintenance`, `security` → `subscribed`, `explicit=false`, and carry
  `classification: "operational"` in the resolved struct. This is the mechanism that keeps an
  operational notice from ever being counted as marketing consent: the classification travels with the
  category, so a future sender cannot conflate them.

Surfaces:

- `GET /api/account/notifications` → `{"categories":[{category, state, explicit, classification, source, decided_at}]}`
- `PUT /api/account/notifications` with body `{"product_updates":"subscribed"}` — partial update;
  absent categories untouched; unknown category or state → 400 with nothing written.
  `AccountHandlers.Register` (`internal/web/account.go:47-58`) gains a `Put(pattern, fn)` method on its
  structural router interface (chi's `*chi.Mux` already satisfies it).
- `/telegram/connect/manage` renders the three categories with the same toggle affordance as the
  existing `send_enabled` control, posting to the same handler.
- MCP: `get_my_notification_preferences` / `set_my_notification_preferences`, gated on the existing
  `account:manage` scope (granted to the client tier in `ResolveScopes`), alongside `get_my_identity`.
  Explicitly **not** admin-scoped — a preference is the user's own data.

A preference grants nothing. `ResolveScopes` (`internal/oauth/server.go:1037-1146`) is not touched, so
there is no path by which subscribing changes a client's scopes. A regression test asserts this.

### 4. Admin projection

`db.IdentityRow` gains, all `omitempty` so existing consumers keep parsing:

```go
FirstName          string                `json:"first_name,omitempty"`
LastName           string                `json:"last_name,omitempty"`
LanguageCode       string                `json:"language_code,omitempty"`
IdentitySource     string                `json:"identity_source,omitempty"`
IdentityCapturedAt *time.Time            `json:"identity_captured_at,omitempty"`
Provenance         map[string]string     `json:"attribute_provenance,omitempty"` // attr -> supplied|not_supplied|unknown
OnboardedAt        *time.Time            `json:"onboarding_completed_at,omitempty"`
LastSeenAt         *time.Time            `json:"last_seen_at,omitempty"`
BotReachability    *BotReachability      `json:"bot_reachability,omitempty"`
NotificationPrefs  []ResolvedPref        `json:"notification_prefs,omitempty"`
```

`Store.ListIdentities` goes from two queries to four: the existing `users` scan (extended with the new
columns), the existing `connected_via` `GROUP BY`, plus one full-table scan each of
`client_bot_reachability` and `client_notification_prefs`, merged through the same
`idx map[int64]int` built by `TelegramID` that `connected_via` already uses. No per-user query, no N+1.

`toolListIdentities` (`internal/mcp/tools.go:1054-1084`) keeps its
`requireAnyScope("admin:users","admin:users:read")` gate verbatim; only the description and the
auto-derived `outputSchema[identitiesResult]()` change.

`digest.buildDigestMessage` gains one suffix per row — reachability when it is not `unknown` — so the
operator sees `blocked` in the digest that produced the signal. The `(no username)` fallback improves
automatically once first/last name are captured separately.

### 5. Deletion and logging

`Store.HardDeleteAccount` (`internal/db/store.go:769-814`) gains
`purgeNotificationState(ctx, tx, userID)` immediately after the existing `purgeAgentData` call, in the
same transaction, deleting from `client_notification_prefs` and `client_bot_reachability`. Explicit
deletes rather than relying on the `ON DELETE CASCADE`, exactly as the agent-data comment at L798-802
requires, because the `users` row survives. `RevokeActiveSession` is not touched: a disconnect is not a
deletion.

`first_name` and `last_name` are added to `audit.sensitiveKeys` (`internal/audit/redact.go:30-74`)
defensively. No new column is added to `audit_logs` and `hashAuditEntry`'s field order
(`internal/db/audit_chain.go:17-57`) is untouched. Preference changes are audited through the existing
`h.audit(r, id, "PUT /api/account/notifications", err)` path, which records a tool name and a status —
no user-supplied free text.

## Alternatives

**A separate `clients` / customer-directory table.** Dropped. The issue explicitly says to extend the
existing projection, and a second table would split-brain against `users.access_tier`,
`oauth_refresh_tokens` and `telegram_accounts` — the three things `ListIdentities` already joins.
Every consumer (`digest`, `toolListIdentities`, `ResolveScopes`) would need to learn which table wins.

**A single `notification_prefs` JSON column on `users`.** Dropped. SQLite (the local-dev dialect,
`driverFor` in `internal/db/db.go:16-23`) has no JSONB, so the dual-dialect DDL would diverge; per-category
`decided_at`/`source` would not be queryable; and proving "product-update consent records timestamp and
source" in a test would mean asserting on marshalled text rather than columns.

**A boolean `bot_blocked` flag instead of a four-state enum.** Dropped. It cannot express the two states
the issue cares most about: `unknown` (we have never had a delivery result, which is the state almost
every client is in) and `cannot_initiate` (the user never started the bot, which is not the same as
having blocked it and has a different remedy).

**Probe-based classification — send a no-op message or `sendChatAction` to learn reachability.**
Dropped, and forbidden by the issue. Telegram has no silent probe; `sendChatAction` to a user who never
started the bot fails the same way `sendMessage` does, and to a user who did it produces a visible
typing indicator. Classification is therefore a by-product of sends that were going to happen anyway.

**Bot commands `/subscribe` / `/unsubscribe` / `/settings` as the primary surface.** Dropped for this
proposal. The login bot has no update receiver — `internal/digest/digest.go:147` is the only Bot API
call in the repo and it is outbound-only. Adding `getUpdates` or a webhook is a new inbound,
internet-facing attack surface with its own authentication, deduplication and rate-limiting design, and
the issue permits those commands only if the bot "already has or deliberately gains" such a receiver.
The web surface already exists and already has auth.

## Platform impact

**Migrations.** Purely additive: seven `addColumnIfMissing` calls on `users`, two
`CREATE TABLE IF NOT EXISTS` in both `pgSchema()` and `sqliteSchema()`, two idempotent backfill
`UPDATE`s. No existing row is rewritten, so tier, session, OAuth-client and refresh-token state are
byte-identical after migration — the issue's first acceptance criterion. `Migrate` is re-run on every
boot and every statement is idempotent, matching the established contract.

**Audit chain.** Untouched. No column is added to `audit_logs` and `hashAuditEntry`'s canonical field
order is not modified, so `VerifyAuditChain` continues to pass over historical rows. This is the single
most dangerous thing a schema change in this repo can get wrong (`internal/db/db.go:127-137`).

**Backward compatibility.** `IdentityRow`'s new fields are all `omitempty`; a consumer parsing today's
`list_telegram_identities` output keeps working. The MCP output schema
(`outputSchema[identitiesResult]()`) does widen, which matters against the ROADMAP line "lock their
schemas for v1.0" — additive-only widening is the mitigation, and `internal/mcp/output_schema_test.go`
pins it. `EnsureUserByTelegramID` keeps its exact current signature and behaviour; the new capture path
is a sibling function, so the three callers that only have a username are unaffected.

**Resource impact.** Two small tables: at most one reachability row and three preference rows per user.
`ListIdentities` goes from two queries to four, all bounded full scans of tables sized by the user
count, merged in memory. The digest already calls `ListIdentities` once per day; `/api/account` and
`manage` read a single user's rows by primary key.

**Risks and mitigations.**

- *Reachability is mostly `unknown` at launch*, because the only wired sender targets operators. This is
  correct behaviour, not a defect, but it will look empty in the admin view — mitigated by rendering
  `unknown` explicitly with its `observed_at`/`source` absent, and by documenting in the tool
  description that `unknown` means "no delivery attempt observed", never "reachable".
- *Misclassifying a transient failure as `blocked`* would permanently suppress a user. Mitigated by the
  `Conclusive` flag: only an explicit 4xx with a recognised description writes state; 429, 5xx and
  transport errors write nothing. Covered by a table-driven test over `ClassifyDelivery`.
- *Legacy `telegram_username` holding a display name* cannot be repaired from the data we have.
  Mitigated by labelling those rows `backfill_legacy` with `identity_captured_at` NULL, which surfaces
  as provenance `unknown`, and by letting the next login overwrite them with a true `telegram_oidc`
  capture.
- *Names leaking into logs.* `first_name`/`last_name` added to `audit.sensitiveKeys`; a test asserts the
  new code paths log only ids, categories, states and reason codes.
- *Consent surviving deletion.* Mitigated by the explicit in-transaction purge in `HardDeleteAccount`,
  with a test that asserts zero rows in both new tables afterwards.
- *Single-replica assumption.* `StartDailyDigest` has no leader election
  (`internal/digest/digest.go:28-30`). Reachability writes from it inherit that; the upsert is
  idempotent so a second replica would at worst write the same row twice.
