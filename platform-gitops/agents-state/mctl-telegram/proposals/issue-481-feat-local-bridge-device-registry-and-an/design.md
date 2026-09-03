# Design: issue-481-feat-local-bridge-device-registry-and-an

## Current state

- **Schema and migrations** live entirely in `internal/db/db.go`.
  `Migrate(ctx, dbConn, ttlExemptTelegramIDs...)` (`db.go:69-260`) probes the
  dialect with a Postgres-only catalog query, runs `pgSchema()` or
  `sqliteSchema()` (both `CREATE TABLE IF NOT EXISTS` statement lists,
  `db.go:264-493`), then applies a sequence of idempotent
  `addColumnIfMissing` calls for columns added after the initial schema
  (`db.go:281-401`). A separate `migrateAgent(ctx, dbConn, pg)`
  (`internal/db/agent_schema.go:23-34`) is called at the end of `Migrate`
  and owns its own `agentSchemaPG()`/`agentSchemaSQLite()` table lists plus
  its own follow-up `addColumnIfMissing` calls — this is the repo's
  established pattern for adding a self-contained domain's tables without
  growing the core `Migrate` function indefinitely.
- **Store methods** are grouped by domain into files under `internal/db/`:
  `worker_token_revocations.go` (`RevokeWorkerToken`,
  `RevokeWorkerTokensForTelegramID`, `IsWorkerTokenRevoked`,
  `ListWorkerTokenRevocations`) is the closest existing analogue to what
  this issue asks for — register/insert, lookup, revoke, idempotent retry,
  all as `(s *Store) MethodName(ctx, ...) (...)` methods on the shared
  `Store` struct (`internal/db/store.go:19-32`, wrapping `*sql.DB` plus a
  cached `isPostgres` dialect probe used for dialect-specific SQL such as
  `ON CONFLICT ... WHERE ... DO NOTHING` on Postgres vs `INSERT OR IGNORE`
  on SQLite).
- **`localjwt.Claims`** (`internal/auth/localjwt/issuer.go:31-61`) is a flat
  struct marshaled directly to the JWT body by `Mint`
  (`issuer.go:85-120`) and unmarshaled directly from the payload by
  `Verify` (`issuer.go:124-156`). Every optional claim added after the
  original set (`OriginalIssuedAt`, `Jti`) follows the same recipe: a new
  `json:"...,omitempty"` field, a doc comment explaining who sets it and
  why older tokens simply omit it, and no change to the marshal/unmarshal
  code path itself (`encoding/json` already skips absent fields on decode
  and omits zero values with `omitempty` on encode). `Mint` does not
  special-case any of these fields; it only overwrites `Issuer`,
  `IssuedAt`, `ExpiresAt`, and marshals `AudienceRaw` from `Audience`.
  `Verify` checks signature, issuer, expiry, and audience shape, then
  returns the decoded `Claims` unmodified otherwise.
- **Local Bridge today** (`internal/bridge/DESIGN.md`) has exactly one
  daemon-identifying concept: `telegram_accounts.mode` (`'hosted'|'local'`)
  plus an in-memory singleton-per-user registration in `Hub`
  (`internal/bridge/hub.go`). `telegram_accounts.bridge_token_hash` exists
  in both schemas (`db.go:315,406`) and is migrated via
  `addColumnIfMissing` but is dead: nothing writes or reads it
  (`DESIGN.md`, "Correctness gaps" item 3). There is no row anywhere that
  represents one daemon installation independent of the account.

## Proposed solution

1. **New table `local_bridge_devices`, added directly in `db.go`** (per the
   issue's explicit scope), following the exact shape of the existing
   tables in `sqliteSchema()`/`pgSchema()` rather than a new
   `migrateAgent`-style side file — the issue asks for it "in
   `internal/db/db.go`, in both `sqliteSchema()` and `pgSchema()`", and the
   table is small and tightly coupled to `telegram_accounts`/`users`, unlike
   the sprawling agent domain that justified its own file.

   Columns (SQLite / Postgres types mirrored the way every other table in
   this file does):
   - `id` (`INTEGER PRIMARY KEY AUTOINCREMENT` / `BIGSERIAL PRIMARY KEY`)
   - `user_id` (`INTEGER`/`BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE`)
     — same ownership pattern as `telegram_accounts.user_id`.
   - `device_id` (`TEXT NOT NULL`) — the public, server-generated
     identifier (UUID-shaped string minted by the `Store` method, not
     client-supplied; see Open questions in requirements.md). This is the
     value a later sub-issue would place in `localjwt.Claims.DeviceID`.
   - `device_label` (`TEXT`) — optional human-readable name (e.g. hostname),
     nullable, populated by a later sub-issue's registration endpoint.
   - `idempotency_key` (`TEXT`) — optional caller-supplied key so a retried
     registration call (network timeout, daemon restart mid-request) can be
     recognized and answered with the existing row instead of creating a
     duplicate, mirroring how `oauth_refresh_tokens`/`worker_token_revocations`
     use a unique index plus `ON CONFLICT ... DO NOTHING` /
     `INSERT OR IGNORE` for the same idempotent-insert shape.
   - `registered_at` (`DATETIME`/`TIMESTAMPTZ NOT NULL DEFAULT
     CURRENT_TIMESTAMP`/`NOW()`).
   - `last_seen_at` (`DATETIME`/`TIMESTAMPTZ`, nullable) — updated by the
     last-seen `Store` method; left `NULL` until first use.
   - `revoked_at` (`DATETIME`/`TIMESTAMPTZ`, nullable).
   - `revoked_reason` (`TEXT`, nullable) — mirrors
     `worker_token_revocations.reason` / `oauth_refresh_tokens.revoked_reason`.

   Indexes:
   - `CREATE UNIQUE INDEX IF NOT EXISTS idx_local_bridge_devices_device_id ON
     local_bridge_devices(device_id)` — a device id must resolve to exactly
     one row.
   - `CREATE UNIQUE INDEX IF NOT EXISTS
     idx_local_bridge_devices_idempotency_key ON
     local_bridge_devices(idempotency_key) WHERE idempotency_key IS NOT
     NULL` — partial unique index, same technique as
     `idx_worker_token_revocations_jti`, so rows that never supplied a key
     do not collide with each other.
   - `CREATE INDEX IF NOT EXISTS idx_local_bridge_devices_user ON
     local_bridge_devices(user_id) WHERE revoked_at IS NULL` — mirrors
     `idx_telegram_accounts_user_active`, for a later "list my active
     devices" lookup.

   The table is created inside `sqliteSchema()`/`pgSchema()` via
   `CREATE TABLE IF NOT EXISTS`, so on a fresh database it appears with the
   rest of the schema in one pass, and on an existing database with no such
   table `Migrate` creates it on the next deploy — no `addColumnIfMissing`
   scaffolding is needed for the initial table itself (that mechanism is
   only for columns added to a table that already exists elsewhere).

2. **`Store` methods, new file `internal/db/local_bridge_devices.go`**
   (mirroring the one-domain-per-file convention of
   `worker_token_revocations.go`, `refresh_tokens.go`, `agent_actions.go`):
   - `RegisterDevice(ctx, userID int64, label, idempotencyKey string) (deviceID string, err error)`
     — generates a device id (`crypto/rand`-backed UUID-shaped string,
     matching how the repo already avoids adding a UUID library dependency
     elsewhere... verified: no `github.com/google/uuid` import exists
     today, so this proposal generates an id with `crypto/rand` +
     hex/base32 encoding rather than introducing a new dependency), inserts
     the row, and on an idempotency-key conflict re-reads and returns the
     existing row's `device_id` instead of erroring — same idempotent-insert
     shape as `RevokeWorkerToken`'s `ON CONFLICT ... DO NOTHING` /
     `INSERT OR IGNORE` pair, followed by a `SELECT` when the caller needs
     the row back (`RevokeWorkerToken` does not need to; this method does,
     so it performs the follow-up `SELECT` inside the same method after the
     conditional insert).
   - `GetDevice(ctx, deviceID string) (*Device, error)` — returns a `Device`
     struct (id, user id, device id, label, timestamps, revoked state) or a
     sentinel `ErrDeviceNotFound` for no rows, matching the
     `errors.New`/wrapped-error style used throughout `store.go`.
   - `RevokeDevice(ctx, deviceID, reason string) error` — sets
     `revoked_at = now (UTC, Go clock)`/`revoked_reason`; same
     "explicit Go clock rather than column DEFAULT" rationale as
     `RevokeWorkerToken` documents, since a later sub-issue may want to
     compare `revoked_at` against a token's `iat`/`orig_iat` the same way
     `IsWorkerTokenRevoked` does. Idempotent: revoking an already-revoked
     device is a no-op, not an error (mirrors `RevokeWorkerToken`'s
     "re-revoking the same jti is a no-op" contract).
   - `TouchDeviceLastSeen(ctx, deviceID string) error` — `UPDATE ... SET
     last_seen_at = now WHERE device_id = $1`. A no-op update (0 rows
     affected) on an unknown or revoked device is not treated as an error
     at this layer — callers that care about existence use `GetDevice`
     first; this keeps the method a cheap, fire-and-forget heartbeat
     primitive for a future daemon keep-alive path.

   None of these four methods are called from anywhere yet — no wiring into
   `internal/bridge`, `internal/mcp/tools.go`, or `cmd/local`. They exist
   so the follow-up sub-issues have a stable `Store` surface to build on.

3. **`localjwt.Claims.DeviceID`**: add
   `DeviceID string \`json:"device_id,omitempty"\`` to the `Claims` struct
   in `issuer.go`, next to `Jti`, with a doc comment stating that it is
   optional, unset by every caller today, and that `Mint`/`Verify` require
   no changes because `encoding/json` already omits it when empty and
   ignores it when absent on decode. No caller in `internal/oauth`,
   `internal/agentapi`, `internal/bridge/tokenhandler.go`,
   `internal/workertoken`, or `internal/mcp/tools.go` is touched — they all
   construct `Claims{...}` literals today and continue to leave `DeviceID`
   at its zero value, which is exactly the "optional at every layer"
   constraint the issue states.

## Alternatives

1. **Reuse `telegram_accounts.bridge_token_hash` instead of a new table.**
   Rejected: that column is scoped to one hash per account (one live
   daemon), while the issue's device *registry* framing (and the
   4-sub-issue split implying multiple/rotatable device credentials down
   the line) needs a one-to-many `users`-to-`devices` shape. Repurposing a
   dead single-value column would also entangle this additive change with
   the pre-existing `bridge_token_hash` correctness gap noted in
   `DESIGN.md`, which is explicitly out of scope here.
2. **Put the new table in its own `migrateAgent`-style file
   (`local_bridge_schema.go`) with its own `migrateLocalBridge` hook.**
   Considered for consistency with the agent domain's self-contained
   pattern. Dropped in favor of following the issue's literal instruction
   ("Add ... to `internal/db/db.go`, in both `sqliteSchema()` and
   `pgSchema()`") — the agent domain split exists because that domain is
   large (a dozen-plus tables); one table with a handful of columns fits
   the main schema lists without the extra indirection.
3. **Make `device_id` required on `Claims` and reject tokens without it.**
   Rejected outright by the issue's "additive, no existing code path
   changes meaning" and "nothing may start requiring it" constraints; a
   required claim would break every already-issued and every
   still-to-be-minted-by-unchanged-callers token the instant this deploys.
4. **Client-supplied `device_id` at registration time instead of
   server-generated.** Left as an open question rather than decided, since
   no registration endpoint exists yet in this issue; server-generation was
   chosen for the `Store` method proposed here because it mirrors how every
   other identifier-bearing table in this codebase (`oauth_refresh_tokens`,
   `worker_token_revocations`) generates or hashes its own identifier
   rather than trusting client input, and because it keeps this proposal's
   `RegisterDevice` usable in isolation (it does not need a request struct
   to accept a client id from).

## Platform impact

- **Migrations**: one new `CREATE TABLE IF NOT EXISTS` plus three
  `CREATE ... INDEX IF NOT EXISTS` statements added to both
  `sqliteSchema()` and `pgSchema()`. Runs inside the existing `Migrate`
  transa-less loop (`db.go:81-86`), same as every other table — no new
  migration mechanism, no lock beyond what individual `CREATE TABLE`/`CREATE
  INDEX` statements already take on each dialect.
- **Backward compatibility**: purely additive. No existing table, column,
  index, or claim changes shape or meaning. `local_bridge_devices` starts
  empty on every existing deployment and stays empty until a follow-up
  sub-issue adds a caller. The `device_id` JWT claim is `omitempty` and
  read by nobody in this issue, so every already-issued token (with no
  `device_id` in its payload) verifies identically before and after this
  change — this is pinned by the regression test in `## Tests` below.
- **Resource impact**: negligible. One empty table plus three small
  indexes; no new background job, no new HTTP route, no change to request
  latency (no existing code path reads or writes the new table or claim).
- **Risks and mitigations**:
  - *Risk*: a future sub-issue assumes `device_id` uniquely and permanently
    identifies a daemon installation, but this proposal does not define
    rotation semantics (what happens to `local_bridge_devices` rows when a
    device's credential is reissued). *Mitigation*: left as an explicit
    open question; the schema's `revoked_at`/`revoked_reason` plus the
    ability to `RegisterDevice` a fresh row keeps "revoke old, register new"
    available as one valid strategy without baking in a specific rotation
    policy prematurely.
  - *Risk*: SQLite's lack of `ALTER COLUMN`/constraint changes has bitten
    this file before (see the `github_login`/`session_encrypted` NOT NULL
    comments in `Migrate`). *Mitigation*: none of this proposal's columns
    are ever altered after creation — `revoked_at`/`revoked_reason`/
    `last_seen_at` are nullable from the start on both dialects, so no
    future `ALTER COLUMN DROP NOT NULL` dance is set up by this change.
  - *Risk*: forgetting the partial-unique-index `ON CONFLICT` target syntax
    on Postgres (documented pitfall in `RevokeWorkerToken`'s comment: a bare
    `ON CONFLICT (jti)` fails against a partial index). *Mitigation*: the
    design doc above and the task list explicitly call out repeating the
    `WHERE idempotency_key IS NOT NULL` predicate in the `ON CONFLICT`
    clause on Postgres, and the test plan requires exercising the
    idempotent-retry path against both dialects.
