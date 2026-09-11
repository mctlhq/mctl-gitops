# Design: issue-620-feat-clients-identity-attributes-and-pro

## Current state

### Schema

There are no migration files. `internal/db/db.go` holds the whole schema as Go
string slices: `sqliteSchema()` and `pgSchema()` return `CREATE TABLE IF NOT
EXISTS` statements, and `Migrate(ctx, dbConn, ttlExemptTelegramIDs...)` executes
them followed by an idempotent additive pass of `addColumnIfMissing` calls
(`internal/db/db.go:404`), a small set of `CREATE UNIQUE INDEX IF NOT EXISTS`
statements, a backfill block of plain `UPDATE` statements
(`internal/db/db.go:226-260`), `migrateAgent` for the agent domain
(`internal/db/agent_schema.go`), and finally `dropLegacyColumns`. `Migrate` is
run on every boot and is expected to converge.

The base `users` table is small — `id`, `github_login`, `email`, `provider`,
`created_at` — and everything Telegram-native was bolted on later through
`addColumnIfMissing`: `telegram_login_id`, `telegram_username`,
`telegram_display_name`, `access_tier` (`internal/db/db.go:142-161`). A partial
unique index `idx_users_telegram_login_id` enforces one row per Telegram id
while leaving legacy NULL rows valid.

`telegram_accounts` carries the session state: `telegram_user_id` (NULL until a
login is finalised), `display_name`, `username`, `session_encrypted`,
`connected_at`, `revoked_at`, `last_used_at`, `expires_at`, `mode`.
`oauth_refresh_tokens` carries `user_id`, `client_name`, `created_at`,
`expires_at`, `revoked_at`.

### Identity capture paths

`Store.EnsureUserByTelegramID` (`internal/db/store.go:183`) is the single
identity-binding call. It inserts `github_login='tg:<id>'`, `provider='tg-mcp'`,
`telegram_login_id`, `telegram_username`, `telegram_display_name` with `ON
CONFLICT DO NOTHING`, re-selects the id, then best-effort refreshes username and
display name with `COALESCE(NULLIF($1,''), telegram_username)` so a caller that
omits a value never erases a previously captured one. It has four production
call sites, and they supply very different amounts of information:

- `internal/oauth/server.go:1597` — the OIDC callback. It has a full
  `telegramoidc.Identity` (`TelegramID`, `Sub`, `Username`, `FirstName`,
  `LastName`) and passes `strings.TrimSpace(identity.FirstName+" "+identity.LastName)`
  as the display name. First and last name are destroyed at this line.
- `internal/oauth/local_bridge_activate.go:1038` — Local Bridge activation, also
  from a verified `Identity`.
- `internal/auth/localjwt/issuer.go:293` — worker-token issuance. Passes the
  username from the token claims and an empty display name. This path knows
  nothing about first/last name.
- `internal/oauth/server.go:2018` — auth-code redemption, passes the stored
  username and an empty display name.

The hosted MTProto login is the other source of verified attributes.
`telegram.Login` (`internal/telegram/login.go:94`) runs the auth flow, calls
`client.Self(ctx)`, and returns `(telegramUserID int64, displayName, username
string, err error)` — composing `displayName` from `me.FirstName + " " +
me.LastName` at line 154, discarding the parts and `me.LangCode`.
`telegram.LoginQR` has the same shape, both are referenced through the
`oauth.LoginFunc` type (`internal/oauth/server.go:113`, wired at line 675) and
called from `internal/oauth/enable_access.go:204` and `cmd/login/main.go:147`.
`enable_access.go` compares the returned id against the expected `wantTgID`
before it calls `SaveSession` (line 332) — a mismatch means the wrong account
was logged in and the flow is aborted.

### Read paths

`Store.ListIdentities` (`internal/db/store.go:403`) selects
`telegram_login_id, telegram_username, telegram_display_name, access_tier,
created_at` plus an `EXISTS` sub-query for `has_session` that mirrors
`CheckSessionValid`'s TTL predicates (and splices in `ttlExemptClause`), then
runs a second query over `oauth_refresh_tokens` to attach `connected_via`, merged
through a `map[int64]int` index. It returns `[]IdentityRow`
(`internal/db/store.go:284`). Two consumers: the MCP tool
`list_telegram_identities` (`internal/mcp/tools.go:1052`, gated on `admin:users`
or `admin:users:read` via `requireAnyScope`, audited through `s.audit`) and the
daily digest (`internal/digest/digest.go:73`, which only reads `CreatedAt`,
`AccessTier` and the count).

`Store.GetLoginIdentity` (`internal/db/store.go:353`) returns `(tgID, username,
displayName)` for one `users.id`; `toolGetMyIdentity` (`internal/mcp/tools.go:953`)
merges it over the `auth.Identity` in context and renders `myIdentityResult`
(`internal/mcp/tools.go:1977`). Its description already promises provenance
semantics the schema cannot deliver.

### Logging and tests

`internal/audit/redact.go` wraps the slog handler and replaces values for any
attribute key in `sensitiveKeys`; `ScrubText` masks `@handle`/phone-shaped runs
inside error strings. No slog call site currently logs a `display_name`,
`first_name` or `username` attribute. `audit_logs` rows hold only
`tool_name`, `peer_redacted`, `status`, `error`, `call_path`.

Postgres coverage is opt-in through `TEST_DATABASE_URL`:
`internal/db/store_access_tier_test.go:169`, `drop_legacy_columns_test.go:151`,
`local_bridge_devices_test.go:272` and others skip when it is unset, open the
real DSN, run `Migrate`, and register a `t.Cleanup` that deletes the rows they
created. SQLite tests use `file::memory:?cache=shared` or a `t.TempDir()` file
(`newTestStoreCrypted`, `openMigrated`). `drop_legacy_columns_test.go` is the
model for a legacy-row test: it recreates the pre-change column state by hand
with a raw `ALTER TABLE`, asserts the setup actually took effect, then re-runs
`Migrate` and checks convergence. `internal/mcp/output_schema_test.go` asserts
every tool advertises an `OutputSchema`.

## Proposed solution

### 1. Schema: four new nullable columns on `users`

Added in `Migrate`'s additive pass in `internal/db/db.go`, next to the existing
Telegram-native block, all nullable with no `DEFAULT` so existing rows are
untouched and `NULL` keeps its "unknown" meaning:

| column | pg type | sqlite type | meaning |
| --- | --- | --- | --- |
| `telegram_first_name` | `TEXT` | `TEXT` | verified `first_name` claim / self-user field |
| `telegram_last_name` | `TEXT` | `TEXT` | verified `last_name` claim / self-user field |
| `telegram_language_code` | `TEXT` | `TEXT` | verified language code where a source supplies one |
| `identity_captured_at` | `TIMESTAMPTZ` | `DATETIME` | when a capture pass last ran for this row |
| `onboarding_completed_at` | `TIMESTAMPTZ` | `DATETIME` | first finalised MTProto session |

`identity_captured_at` is the whole provenance mechanism. Capture always writes
the full attribute set from one verified source in one statement, so a single
timestamp per row is sufficient to separate the two failure modes:

- `identity_captured_at IS NULL` — capture has never run against this row. Every
  empty optional attribute is `not_captured`.
- `identity_captured_at` set, attribute empty — capture ran and the source
  supplied nothing. The attribute is `not_supplied`.
- `identity_captured_at` set, attribute non-empty — `verified`.

`users.created_at` is reused as "first seen"; it is `NOT NULL` on both dialects,
always trustworthy, and needs no provenance entry or new column. No new index is
required: every read is either by `users.id` or a full scan of a table that is
already fully scanned by `ListIdentities`.

The backfill block gains one idempotent statement, shared by both dialects
(`MIN`, a correlated sub-query and `IS NULL` are portable):

```sql
UPDATE users
   SET onboarding_completed_at = (
         SELECT MIN(ta.connected_at) FROM telegram_accounts ta
          WHERE ta.user_id = users.id AND ta.telegram_user_id IS NOT NULL)
 WHERE onboarding_completed_at IS NULL
   AND EXISTS (SELECT 1 FROM telegram_accounts ta
                WHERE ta.user_id = users.id AND ta.telegram_user_id IS NOT NULL)
```

A finalised `telegram_accounts` row is a verified server-side record that the
user completed onboarding, so this is derivation from a real record, not
inference. Nothing backfills first/last name: the only candidate source is
`telegram_display_name`, which `server.go:1597` and `login.go:154` produced by
joining the two with a space, and splitting a multi-word name back apart is
exactly the guessing the issue forbids. Those rows stay `not_captured` and heal
on the user's next sign-in.

### 2. Capture: an explicit `Store.CaptureTelegramIdentity`

`EnsureUserByTelegramID` keeps its signature and its four call sites unchanged.
A new method sits beside it in `internal/db/store.go`:

```go
// TelegramIdentityAttrs is one verified snapshot of a Telegram identity.
type TelegramIdentityAttrs struct {
    Username     string
    FirstName    string
    LastName     string
    DisplayName  string
    LanguageCode string
}

func (s *Store) CaptureTelegramIdentity(ctx context.Context, userID int64, a TelegramIdentityAttrs) error
```

It runs one `UPDATE users SET ... , identity_captured_at = $now WHERE id = $uid`,
using the same `COALESCE(NULLIF($n,''), column)` shape
`EnsureUserByTelegramID` already uses, so a partial snapshot never erases a
richer earlier one — and it stamps `identity_captured_at` unconditionally,
which is what makes `not_supplied` reachable.

Capture is deliberately *not* folded into `EnsureUserByTelegramID`. Two of that
function's call sites (`localjwt/issuer.go:293`, `oauth/server.go:2018`) only
have a username; if they stamped `identity_captured_at`, every first/last name
they do not know would be mislabelled `not_supplied` instead of `not_captured`.
Provenance is only honest if the stamp means "a source that could have supplied
all of these was consulted".

Call sites added:

- `internal/oauth/server.go` (OIDC callback, after `EnsureUserByTelegramID`
  succeeds) — passes `identity.Username`, `identity.FirstName`,
  `identity.LastName`, the composed display name it already builds, and
  `identity.LanguageCode`.
- `internal/oauth/local_bridge_activate.go:1038` — same, from its `Identity`.
- `internal/oauth/enable_access.go`, after the `wantTgID` check passes and
  `SaveSession` succeeds — passes the MTProto self-user attributes. Placing it
  after the id check is the reason capture does not live inside
  `telegram.Login`: a login that lands on the wrong account must not stamp that
  account's names onto this `users` row.

### 3. Carrying the parts out of the login flow

`telegramoidc.Identity` and `idTokenClaims` gain a `LanguageCode` /
`language_code` field, so the claim is captured if Telegram ever sends it and is
simply empty otherwise. `parseIdentity` copies it across; no verification logic
changes.

`telegram.Login` and `telegram.LoginQR` change their return from
`(int64, string, string, error)` to `(LoginResult, error)`:

```go
type LoginResult struct {
    TelegramID   int64
    DisplayName  string
    Username     string
    FirstName    string
    LastName     string
    LanguageCode string
}
```

populated from the `*tg.User` that `client.Self(ctx)` already returns
(`internal/telegram/login.go:150`), including the flag-gated `LangCode`.
`oauth.LoginFunc` (`internal/oauth/server.go:113`) changes with it, and the two
consumers — `internal/oauth/enable_access.go:204` and `cmd/login/main.go:105,147`
— are updated. This is a compile-time break on purpose: a struct return means
every future attribute is additive, and the compiler names each caller that must
decide what to do with it, rather than letting the values silently drift out of
scope the way `me.LangCode` does today.

### 4. Read model and provenance rendering

`db.IdentityRow` (`internal/db/store.go:284`) gains:

```go
FirstName             string              `json:"first_name,omitempty"`
LastName              string              `json:"last_name,omitempty"`
LanguageCode          string              `json:"language_code,omitempty"`
LastSeenAt            *time.Time          `json:"last_seen_at,omitempty"`
OnboardingCompletedAt *time.Time          `json:"onboarding_completed_at,omitempty"`
Provenance            IdentityProvenance  `json:"provenance"`
```

with `CreatedAt` documented as first-seen (unchanged wire field). Provenance is a
named struct rather than a `map[string]string` so `WithOutputSchema[T]` reflects
a fully described object instead of free-form `additionalProperties`:

```go
type IdentityProvenance struct {
    Username              string `json:"username"`
    FirstName             string `json:"first_name"`
    LastName              string `json:"last_name"`
    DisplayName           string `json:"display_name"`
    LanguageCode          string `json:"language_code"`
    LastSeenAt            string `json:"last_seen_at"`
    OnboardingCompletedAt string `json:"onboarding_completed_at"`
}
```

Values are four package constants in `internal/db`: `ProvenanceVerified`
(`"verified"`), `ProvenanceDerived` (`"derived"`), `ProvenanceNotSupplied`
(`"not_supplied"`), `ProvenanceNotCaptured` (`"not_captured"`). A single unexported
helper `attrProvenance(capturedAt sql.NullTime, value string) string` decides the
first three cases for every Telegram-supplied attribute, so the rule lives in one
place and both read paths share it.

`ListIdentities` extends its first `SELECT` with the four new columns and two
derived expressions, computed as correlated sub-queries against tables the
function already touches:

- `onboarding_completed_at` — read from the column (backfilled), provenance
  `derived` when present, `not_captured` when NULL.
- `last_seen_at` — `MAX` over `telegram_accounts.last_used_at` for the user and
  `MAX` over `oauth_refresh_tokens.created_at` for the user, whichever is later;
  provenance `derived`, or `not_captured` when the user has neither record. This
  avoids adding a per-request write to a hot path — `MarkLastUsed`
  (`internal/db/store.go:995`) already pays that cost for sessions and there is
  no reason to add a second one on `users`.

The existing `connected_via` second query and its map merge are untouched; the
new derived values ride on the first query so the function keeps its two
round-trips.

`GetLoginIdentity`'s three-return signature does not scale to eight values. It is
replaced by `Store.GetIdentity(ctx, userID int64) (*IdentityRow, error)`, which
runs the same projection filtered to one `users.id` and reuses the same
provenance helper, returning `nil` when the row is absent (preserving today's
"missing users row is not an error" behaviour). The old function is deleted and
its one call site in `toolGetMyIdentity` migrated, so there is exactly one
rendering of provenance.

### 5. Tool surface

`myIdentityResult` (`internal/mcp/tools.go:1977`) gains the same fields and the
same `provenance` object. `toolGetMyIdentity` keeps its fallback to the
`auth.Identity` in context when the store has no row, and keeps its "no Telegram
identity on this session" error. Both tool descriptions are rewritten to state
the four provenance values explicitly — `get_my_identity`'s existing prose about
"never captured" becomes accurate instead of aspirational, and
`list_telegram_identities`'s output list is extended. `output_schema_test.go`
needs no new entry (both tools are already listed) but will now reflect the
larger schemas. `docs/portal-allowlist.json`'s `get_my_identity` reason string is
updated to name the added attributes; the tool stays `enabled: true` because the
new fields are still strictly about the caller. `README.md` and `docs/runbook.md`
get one-line updates.

### 6. Logging and audit

Nothing new is logged. As defence in depth, `first_name`, `last_name`,
`telegram_first_name`, `telegram_last_name` and `display_name` are added to
`sensitiveKeys` in `internal/audit/redact.go` so that a future slog call site
cannot leak them by accident. `language_code` is deliberately *not* added — it is
a two-letter locale, not identifying, and redacting it would only make
capture-path debugging harder (the same reasoning the file already records for
`device_pubkey` and `cost_usd`). `audit_logs` rows are unchanged: the
`list_telegram_identities` audit entry still records only the tool name.

## Alternatives

**Split `telegram_display_name` into first/last during the backfill.** This would
immediately populate the new columns for every existing row, which is superficially
attractive. Rejected: the composed value came from
`TrimSpace(FirstName+" "+LastName)`, so a user whose first name is two words
(or whose last name is) would be split wrongly and the wrong value would then read
as `verified`. That is precisely the "never infer names" prohibition, and a wrong
value labelled verified is worse than an honest `not_captured`.

**A `user_identity_attributes` side table with one row per (user, attribute,
value, source, captured_at).** Fully general, gives true per-attribute provenance
with no shared-timestamp approximation, and would make future slices of #438
cheap. Rejected for this slice: it is the "new user directory separate from the
existing projection" the issue lists as a non-goal, it turns `ListIdentities`'
two queries into a join plus a pivot, and the generality buys nothing while every
capture writes all attributes from a single source in a single statement. If a
later slice introduces genuinely independent per-attribute sources, the single
timestamp is the thing that would have to change, and this design confines that
to `attrProvenance` plus one migration.

**Stamp `identity_captured_at` inside `EnsureUserByTelegramID` instead of adding
`CaptureTelegramIdentity`.** Fewer moving parts and no new call sites. Rejected:
two of its four call sites only carry a username, so they would stamp rows whose
first/last name they never had a chance to learn, permanently mislabelling
`not_captured` as `not_supplied`. Provenance that lies is worse than no
provenance.

**Add a `users.last_seen_at` column written on every authenticated request
instead of deriving it.** More precise and a trivial read. Rejected: it adds a
write to the auth hot path for a field only two admin-facing reads consume, and
the data is already recoverable from `telegram_accounts.last_used_at` and
`oauth_refresh_tokens.created_at`. The `derived` provenance value exists so the
approximation is visible rather than hidden.

## Platform impact

**Migrations.** None as files — this repo has no migration directory. The change
is five `addColumnIfMissing` calls plus one `UPDATE` in `internal/db/db.go`'s
`Migrate`, which runs on every pod boot and is idempotent by construction. All
five columns are nullable with no `DEFAULT`, so on Postgres each `ALTER TABLE ...
ADD COLUMN IF NOT EXISTS` is a catalog-only change with no table rewrite; the
`ACCESS EXCLUSIVE` lock is held for microseconds on a `users` table measured in
hundreds of rows. The backfill `UPDATE` touches only rows where the column is
NULL, so it does real work exactly once and is a no-op on every later boot.

**Backward compatibility.** Additive on the wire: every existing field of
`identitiesResult` and `myIdentityResult` keeps its name, type and meaning, and
new optional fields carry `omitempty`. `provenance` is the one always-present new
object. An MCP client that ignores unknown fields is unaffected. Rolling back the
image leaves the five columns in place and unread, which is harmless — unlike the
`idx_local_bridge_devices_idem_live` change documented in `db.go`, nothing here is
forward-only. The service deploys `strategy: Recreate` with a single replica
(recorded in the `local_bridge_devices` schema comment), so no mixed-version pod
pair ever sees a half-migrated schema.

**Compile-time breaks.** `telegram.Login` / `telegram.LoginQR` /
`oauth.LoginFunc` change shape, and `Store.GetLoginIdentity` is removed. Callers
are `internal/oauth/enable_access.go:204`, `cmd/login/main.go:105,147`,
`internal/mcp/tools.go:953`, plus the fake `loginFn` implementations in
`internal/oauth`'s tests. All are in-repo; there is no external consumer.

**Resource impact.** `ListIdentities` gains four scalar columns and two
correlated sub-queries per row over tables it already reads. On a roster of this
size the difference is unmeasurable; if the roster ever grows, the sub-queries hit
`idx_telegram_accounts_user_active` and `oauth_refresh_tokens(user_id)`
respectively. `CaptureTelegramIdentity` adds one `UPDATE` per sign-in, on a path
that already does several.

**Risks and mitigations.**

- *Risk:* the `telegram.Login` signature change silently drops a value at one of
  the updated call sites. *Mitigation:* a struct return makes every field named at
  every call site, and the existing `enable_access` tests exercise the login path
  end to end through the fake `loginFn`.
- *Risk:* capture stamps `identity_captured_at` on a login that later turns out to
  be the wrong account. *Mitigation:* the capture call is placed after
  `enable_access.go`'s `wantTgID` comparison and after `SaveSession` returns
  successfully, so an aborted or mismatched flow never reaches it.
- *Risk:* the SQLite and Postgres backfill statements diverge in behaviour.
  *Mitigation:* one statement text for both dialects (no `INTERVAL`, no
  `datetime()`), plus the paired SQLite/`TEST_DATABASE_URL` tests described in
  `tasks.md`.
- *Risk:* a new PII field reaches centralized logs. *Mitigation:* the
  `sensitiveKeys` additions plus a test asserting that a `slog` record carrying
  those keys is redacted.
- *Risk:* provenance is rendered inconsistently by the admin and self-service
  tools. *Mitigation:* one `attrProvenance` helper and one `IdentityRow`
  projection shared by `ListIdentities` and `GetIdentity`.
