# Design: issue-986-feat-bridge-versioned-typed-read-result

## Amendment 2026-11-09 (b)

Resolves the independent review of digest
`sha256:f8935e57eb1164201307d742878624c2562817d76b99e15c75cec57633d379ab` (mctl-api#986,
2 P1, 5 P2, 6 P3) and records owner decisions B and A of 2026-11-09 (b). Code references
were re-checked at mctl-api `origin/main` `ceac9ed`. This proposal was rewritten; no
older passage survives that contradicts this section.

**Owner decision B.** The read contract moves to **mctlhq/mctl-agents#1059** (bridge
`v1alpha2`: canonical schemas, golden fixtures, RFC 8785 digest vectors), which gets its
own proposal, review and approval and lands **before** this slice is implemented. This
issue becomes the mctl-api **store/serve slice**: ReadBridge in process, no public
retrieval route, reads are history, preview and basket only (prepare stays a #957
write), no Temporal signal for reads, raw bytes stored and re-verified on fetch, binding,
TTL, revocation and `glovo:read` re-checked in process for the #957 handlers, idempotent
schema changes, and the connection check wired to #957's named mechanism. `v1alpha1`
stays unchanged.

**Owner decision A.** The connection store (#959) is in the same physical database as
the bridge, so the connection check is a live read with no cross-database window.

| Review finding | Fix in this proposal |
|---|---|
| P1-1 nobody starts a read; the v1alpha2 command keeps `order_ref`/`we_`/`wi_`/`workflow_id`; reads write a signal-outbox row | The in-process `bridge.ReadClient` (§3) enqueues read commands and waits on the store with a deadline. Read commands carry the #1059 read binding set (no order, `we_`, `wi_` or workflow fields); `bridgeSchema` relaxes those NOT NULLs only for read kinds via a kind-conditional CHECK. Read kinds write no `bridge_signal_outbox` row and need no `workflow_id` (§4). Task 4 implements the `ReadClient`; #957 A12 wires it behind its `ReadBridge` interface |
| P1-2 public `GET /api/v1/glovo/read-results/{ref}` and a `glovoAudienceRoutes` entry bypass #957's checks | Dropped. No route and no `glovoAudienceRoutes` change. `Store.FetchReadResult` is in process only and is called by the `ReadClient` on behalf of #957's handlers after their own checks; it re-checks binding, TTL, revocation and `glovo:read` as defence in depth (§5). T15 asserts no route is added |
| P2-1 `read_prepare` contradicts the merged contract | Dropped. Read kinds are `read_history`, `read_preview`, `read_basket` (names from #1059). Prepare is the #957 `/orders:prepare` write, which consumes the preview/basket read; open question 3 is closed by #957 D5 |
| P2-2 digest over Go struct order; JSONB re-orders keys | The digest is sha256 over the RFC 8785 (JCS) canonical form, defined by #1059 with vendored test vectors. mctl-api stores the canonical bytes as `BYTEA`, recomputes `sha256(stored) == data_digest` on every fetch and fails closed on a mismatch. Round-trip test T9 |
| P2-3 contract-first split half there; fixtures local | The contract slice is mctl-agents#1059. This slice vendors its schemas, fixtures and digest vectors by sha256 (task 1); T2/T3 use the vendored fixtures only. The provider-side vendoring is an extension of mctl-telegram#1262 (OPEN-986-2) |
| P2-4 `ADD CONSTRAINT bridge_commands_read_wire_chk` fails on the second boot; drop/re-add takes ACCESS EXCLUSIVE every boot | Every schema change is guarded by a catalog check in one `DO` block (`pg_constraint`, `pg_attribute`), constraints are added `NOT VALID` and validated once, and nothing is dropped and re-added on a normal boot (§4). Task 3 DoD and T16 apply the schema twice and on a populated v1alpha1 database |
| P2-5 connection checker undecided | `ConnectionChecker` is the #959 live connection read on the same database, the mechanism #957 names (`glovo.Connections.Current(tenant, principal)`, #957 design §3). The fail-closed default stays; task 5 wires it |
| P3 `SubmitResult` hard-refuses non-v1alpha1 (`store.go:745`), `validate()` (`store.go:229-256`), `projection()` (`store.go:334`) | Tasks 2-4 name all three |
| P3 checker-unavailable sentinel falls through `bridgeStatus` (`handlers_bridge.go:95-113`) | No HTTP route uses it any more; the sentinel stays in process and #957 maps it. `bridgeStatus` gains an explicit case anyway so a future caller cannot fall through to 409 |
| P3 `provenance: "synthetic"` is self-declared | Bounded field shapes come from #1059 (item codes in the `FAKE-n` catalogue pattern, no name/address/phone/person fields, coarse timestamps); mctl-api validates against the vendored schema |
| P3 rows kept forever after the data is erased | Hard delete 24 h after `expires_at` in the same sweep |
| P3 digest in the query string | Gone with the route |
| P3 rollback order | Cancel or expire open read-kind commands **before** the code revert |
| Alignment with the #1059 review (mctl-agents#1059 comment 6745621467), same PR | The cap is the transport's: body ≤ 16384 B (`bridgeMaxBody`), `JCS(payload)` ≤ 12288 B (§5). The result carries no binding refs: bindings come only from the stored command row, and a result that adds any is invalid. Raw-bytes pre-check before parsing (§5 step 3). `lease_token` is never persisted. Read kinds are leased only to v1alpha2-capable providers, and the claim response is versioned (§2). The approval-basket fingerprint is #1059's, computed by #957/#988, not here |

Skipped P3s: none.

## Current state

- `internal/bridge/schema.go` embeds the v1alpha1 `command.schema.json`,
  `result.schema.json` and `PROVENANCE`, vendored from mctl-agents#1045 and pinned by
  `TestVendoredSchemasMatchProvenance`. `SchemaVersion = "bridge.mctl.ai/v1alpha1"`.
- The v1alpha1 command requires `execution_id`, `work_item_id` and `order_ref`;
  `validate()` checks them and `workflow_id` (`store.go:229-256`); `bridge_commands.
  workflow_id` is `NOT NULL` (`store.go:73`). `kind` is closed to `quote`,
  `place_order_fake`, `cancel_order_fake`, `read_status`. The result has only an
  optional `result_ref`.
- `SubmitResult` refuses any `schema_version` other than v1alpha1 (`store.go:745`).
  `submitTx` writes a `bridge_signal_outbox` row to the command's `workflow_id` for every
  completed command (`store.go:800-801`). `projection()` hard-codes `SchemaVersion`
  (`store.go:334`).
- `bridgeSchema` is applied at every start (`store.go:66-67`, `:374`).
- `IssueWritePermit` returns `ErrNotMutating` for non-mutating kinds (`permit.go:98`).
- `bridgeStatus` maps bridge codes (`handlers_bridge.go:95-113`);
  `bridge_unavailable` is written only by `bridgeReady` (`:137`). `bridgeMaxBody` is
  16 KiB (`:42`).
- `glovoAudienceRoutes` is empty (`glovo_audience_gate.go:29-32`); #961 owns the facade
  entries.
- #957 (merged design, ae9101d6) makes `ReadBridge` an in-process interface,
  `Read(ctx, GlovoReadRequest) (GlovoReadResult, error)`, kinds `history|preview|basket`,
  whose transport implementation is this slice (#957 design §5).

## Proposed solution

### 1. Contract (vendored from mctl-agents#1059)
- Task 1 vendors, byte for byte, the #1059 v1alpha2 `command.schema.json`,
  `result.schema.json`, the per-kind read-result schemas, the valid and invalid fixtures
  and the RFC 8785 digest vectors into `internal/bridge/schema/v1alpha2/` with a
  `PROVENANCE` file (repo, PR, merge commit, sha256 per file). It does not author or edit
  any of them. If #1059 is not merged, the task stops.
- Read kinds: `read_history`, `read_preview`, `read_basket` (final names from #1059).
  Read commands carry the #1059 read binding set (tenant, principal, connection and
  install-revision refs (`irv_`), the read idempotency key `request_id` (`rdq_`) and per-kind
  `params`) and no `order_ref`,
  `execution_id`, `work_item_id` or workflow fields.
- The single M1 basket fingerprint is defined in #1059 over the **approval basket**
  projection (`approval-basket.schema.json`) that the preview and basket payloads embed.
  This slice does not compute it. It only stores and serves the read result; #957 and
  #988 compute the fingerprint from the embedded approval basket. `payload_digest` is
  transport integrity only.
- v1alpha1 files, digests, projections and result digests are not touched.

### 2. Code changes for versioning (`schema.go`, `store.go`)
- `compileSchemas()` compiles both URL sets; `ParseResult` reads `schema_version` first
  and validates against the matching schema.
- `SubmitResult` (`store.go:745`) accepts `v1alpha2` only for a command whose stored
  `wire_version` is v1alpha2, else `binding_mismatch`.
- `validate()` (`store.go:229-256`) gets a read-kind branch: read binding set required,
  order/`we_`/`wi_`/workflow fields forbidden.
- `projection()` (`store.go:334`) emits the stored `wire_version` and, for read kinds,
  the #1059 read projection.
- Versioning (#1059 §Versioning):
  - `BridgeProviderConfig` gains a server-side `SupportedVersions` list, default
    `[v1alpha1]`;
  - `Claim` leases a read-kind (v1alpha2) command only to a provider whose list contains
    `bridge.mctl.ai/v1alpha2`, and never trusts a provider-side filter;
  - the claim response (`handlers_bridge.go:200`, today a hard-coded v1alpha1 envelope)
    gets an envelope version, and each command keeps its own `schema_version`;
  - a read command no capable provider claims before `expires_at` expires as `expired`.
  Whether this lands here or in a separate slice is OPEN-1059-2; this proposal plans it
  here (task 2).

### 3. In-process read client (`internal/bridge/readclient.go`)

```go
type ReadRequest struct {
    Kind ReadKind // history | preview | basket
    Tenant, OwnerPrincipalID string        // private
    TenantRef, PrincipalRef, ConnectionRef string // tnr_, prr_, gcn_
    InstallRevision string
    Scopes []string                         // from the verified subject token, for the glovo:read re-check
    Params json.RawMessage                  // bounded, validated against the #1059 command schema
    Deadline time.Time
}
type ReadResult struct{ Kind ReadKind; ResultRef, Digest string; Data []byte /* canonical bytes */ ; ExpiresAt time.Time }
func (c *ReadClient) Read(ctx context.Context, r ReadRequest) (*ReadResult, error)
```

`Read`:
1. In one transaction on the bridge pool: `EnqueueRead` inserts a read-kind command with
   a server-minted `request_id` (`rdq_`, the idempotency key) and no workflow. Commit.
2. Wait on the store until the command completes, with the request deadline (bounded
   poll with backoff; default 10 s, never longer than the #957 handler deadline). On
   deadline: `Store.Cancel` the command and return `ErrReadUnavailable`.
3. Call `Store.FetchReadResult` (§5) with the caller's tenant, principal, connection,
   install revision and scopes, and return the canonical bytes.

Only #957's handlers call `ReadClient.Read`, through #957's `ReadBridge` interface
(#957 task A12 owns the few-line adapter). No HTTP route, MCP tool, Temporal workflow or
signal is involved.

### 4. Storage (`bridgeSchema`, idempotent)

All changes run in one `DO $$ … $$` block whose steps each test the catalog first, so a
second and every later boot is a no-op and takes no ACCESS EXCLUSIVE lock:
- add `wire_version TEXT NOT NULL DEFAULT 'bridge.mctl.ai/v1alpha1'` and
  `read_request_id TEXT` (holds the #1059 `request_id`; `ADD COLUMN IF NOT EXISTS`);
- drop NOT NULL on `workflow_id`, `run_id`, `execution_id`, `work_item_id` and
  `order_ref` only if `pg_attribute.attnotnull` is still true;
- add, only if absent in `pg_constraint`, `NOT VALID`, then `VALIDATE CONSTRAINT` once
  in the same guarded step:
  - `bridge_commands_kind_v2_chk`: kind in the v1alpha1 kinds plus the three read kinds
    (the old `bridge_commands_kind_chk` is dropped in the same guarded step, which runs
    exactly once);
  - `bridge_commands_read_shape_chk`: a read kind has `wire_version` v1alpha2, a
    non-null `read_request_id` and null workflow/order/`we_`/`wi_`; every other kind has
    all of those non-null, which preserves the old guarantee for v1alpha1 rows;
- `CREATE UNIQUE INDEX IF NOT EXISTS bridge_commands_read_request ON bridge_commands
  (tenant, read_request_id) WHERE read_request_id IS NOT NULL`;
- table `bridge_read_results` (`CREATE TABLE IF NOT EXISTS`):
  `result_ref` (server-minted `res_`, PK), `command_id` UNIQUE, `read_kind`, `tenant`,
  `owner_principal_id`, `tenant_ref`, `principal_ref`, `connection_ref`,
  `install_revision`, `data BYTEA` (canonical bytes; NULL after erase), `data_digest`,
  `size_bytes`, `created_at`, `expires_at`, `erased_at`; index on `expires_at`.

`submitTx` for a read kind writes **no** `bridge_signal_outbox` row and no transition to
a workflow; it inserts the `bridge_read_results` row in the same transaction as the
result CAS. Raw data never enters `bridge_commands.result`, which keeps
`{kind, digest, size_bytes, result_ref}` only.

### 5. Submission and fetch rules
Submission (provider, existing `/api/v1/bridge/commands/{id}/result` route):
1. `schema_version` must equal the stored `wire_version`, else `binding_mismatch`.
2. Read kind: `provider_effect = none`, no provider-chosen `result_ref`, and on
   `outcome = succeeded` a `payload` of the command's kind (a payload on any other
   outcome, or on a non-read kind, is refused). Violations: `result_inconsistent`.
3. Run the #1059 raw-bytes pre-check on the body before any `json.Unmarshal`. It rejects
   duplicate keys, lone surrogates, `NaN`/`Infinity`, numbers outside ±(2^53-1) and any
   non-integer token in an integer position. Go's `encoding/json` accepts duplicate keys
   and replaces lone surrogates, so this is a token-level scanner, tested against the
   vendored `must-reject.json` (T7). Failure: `invalid_document`.
4. Validate the envelope against the #1059 `read-result.schema.json`, then canonicalize
   `payload` with RFC 8785 (the vendored #1059 vectors pin the implementation). Failing
   the per-kind schema, or a result that carries any binding ref: `invalid_document`.
   `JCS(payload)` over 12288 bytes: `payload_too_large` (the body itself is already capped
   at 16384 by `bridgeMaxBody`). `"sha256:"+hex(sha256(canonical)) != payload_digest`:
   `binding_mismatch`. Tenant, principal, connection and install revision come only from
   the stored command row; the result carries none of them. `result.kind` must equal the
   stored kind, and the result must arrive before the command's `expires_at`.
5. Store the canonical bytes, mint `res_`, set `expires_at = now() + ReadTTL`. The
   `lease_token` from the result is compared and never persisted, as in v1alpha1.
6. Replay of the same digest returns the same `res_`; a different digest is
   `result_conflict`.

`Store.FetchReadResult(ctx, ReadFetch{ResultRef, Tenant, PrincipalID, ConnectionRef,
InstallRevision, Scopes})`, in process only, checks in this order:

| Check | Sentinel |
|---|---|
| row missing, tenant or owner differs | `ErrCommandNotFound` (identical for all three) |
| `glovo:read` not in `Scopes` | `ErrReadNotAuthorized` |
| `expires_at <= now()` or `data IS NULL` | `ErrCommandExpired` |
| row's connection or install revision differs from the request | `ErrBindingMismatch` |
| `ConnectionChecker.Live(tenant, principal)`: no connection, revoked, expired, other revision | `ErrBindingMismatch` with the M1a state attached for #957's mapping |
| checker error | `ErrReadUnavailable` |
| `sha256(data) != data_digest` (constant-time compare) | `ErrReadUnavailable`, logged as an integrity failure |

`ConnectionChecker` is implemented by the #959 store's live connection read (same
database, owner decision A). Default `DenyConnectionChecker` returns
`ErrReadUnavailable`. #957 maps every sentinel through its §4 table (no bridge code
reaches the Glovo wire); `bridgeStatus` also gains explicit cases for the new sentinels
so they cannot fall through to 409 if ever exposed.

### 6. Expiry and retention
`EraseExpiredReads` sets `data=NULL, erased_at=now()` for expired rows and deletes rows
whose `expires_at` is more than 24 h ago, in bounded `FOR UPDATE SKIP LOCKED` batches
from the existing `Expirer` tick. Metric `mctl_api_bridge_read_results_erased_total`, no
tenant labels. `MCTL_BRIDGE_READ_RESULT_TTL`: default 600 s, clamped 1..900 s.

## Alternatives

1. Data through the Temporal signal or `ReadOutcome`. Rejected: raw user data in Temporal
   history (forbidden by the issue and #1044).
2. A public retrieval route. Rejected (review P1-2): it bypasses #957's kill switch,
   scope, team grant and preview persistence, and exposes bridge codes on the Glovo wire.
3. Authoring the schema here. Rejected (owner decision B): #1059 is the canonical source.
4. JSONB storage. Rejected (review P2-2): JSONB re-orders keys, so the digest cannot be
   re-verified.

## Platform impact

- Migrations: additive, guarded, idempotent (§4). Existing v1alpha1 rows satisfy the new
  CHECKs; the NOT NULL relaxation is compensated by the kind-conditional CHECK.
- Backward compatibility: v1alpha1 unchanged and golden-pinned. Providers receive
  v1alpha2 commands only for read kinds, which nobody enqueues until #957 wires the
  client.
- Security: no new route or audience; data reachable only in process after #957's checks
  plus this store's re-checks; providers cannot read data back.
- Resources: ≤ 12 KiB per read row (the #1059 `JCS(payload)` cap of 12288 bytes), erased within 900 s, deleted after
  24 h.
- Order: #1059 approved and merged -> this slice -> #957 A12 and the mctl-telegram
  provider read path -> #990 tests. Nothing is enabled by this slice.
