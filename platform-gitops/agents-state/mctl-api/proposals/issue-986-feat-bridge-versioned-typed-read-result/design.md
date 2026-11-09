# Design: issue-986-feat-bridge-versioned-typed-read-result

## Current state

- `internal/bridge/schema.go` embeds `schema/command.schema.json`,
  `schema/result.schema.json` and `schema/PROVENANCE`. These are vendored
  unchanged from mctl-agents PR #1045, merge
  `14645f93fd4eb425a3ac5adeae497209431b8342`. `compileSchemas()` compiles only
  these two v1alpha1 URLs, and `SchemaVersion = "bridge.mctl.ai/v1alpha1"`.
  `TestVendoredSchemasMatchProvenance` (`schema_test.go`) pins the sha256 of
  both files.
- `result.schema.json` uses `additionalProperties: false` and has an optional
  `result_ref` (`^res_[A-Za-z0-9]{16,40}$`). It has no payload field.
  `command.schema.json` closes `kind` to `quote | place_order_fake |
  cancel_order_fake | read_status`, and its `payload` is a small bounded object.
- `ParseResult` validates and strictly decodes into `Result`. `Result.Digest()`
  is sha256 over the struct-ordered JSON. `redacted()` stores a
  `storedResult` without `lease_token` in `bridge_commands.result`.
- `internal/bridge/store.go`:
  - `bridgeSchema` is DDL applied at startup ("purely additive"). It creates
    `bridge_commands`, with private bindings `tenant`, `owner_principal_id`,
    `tenant_ref`, `principal_ref`, `connection_ref` and `install_revision`, and
    a `bridge_commands_kind_chk` CHECK on the four v1alpha1 kinds. It also
    creates `bridge_command_transitions`, `bridge_signal_outbox` and
    `bridge_write_permits`.
  - `SubmitResult` / `submitTx`:
    1. Lock the row with `lockOwned` (foreign provider or tenant answers
       `command_not_found`).
    2. Check bindings and the lease token.
    3. On replay of the same digest, answer `replayed: true`; on a different
       digest, refuse with `result_conflict`.
    4. Run the consistency checks and the CAS `UPDATE`.
    5. Insert the signal-outbox row and the transition in one transaction.
  - `ReadOutcome` returns status, effect and the stored result. `expireTx` and
    `ExpireDue` drive the background `Expirer` (`expiry.go`).
- `internal/bridge/permit.go`: `IssueWritePermit` returns `ErrNotMutating` for
  any kind other than `place_order_fake` / `cancel_order_fake`, so reads can
  never get a permit.
- `internal/bridge/errors.go` defines the closed code set (`command_not_found`,
  `command_expired`, `binding_mismatch`, `result_conflict`,
  `result_inconsistent`, `invalid_document`, ...). `internal/api/handlers_bridge.go`
  `bridgeStatus` maps these codes to HTTP statuses. `bridgeMaxBody = 16 << 10`.
  `auditBridge` records ids, digests and codes only. `BridgeService` exposes
  `Claim`, `SubmitResult` and `IssueWritePermit`.
- `internal/api/router.go:876-890`: the `/api/v1/bridge` routes are mounted only
  when `opts.BridgeEnabled` is true, behind `requireBridgeProvider` and a rate
  limit. `bridgeProviderGate` confines provider principals to the bridge
  prefix.
- `internal/api/glovo_audience_gate.go`: `glovoAudienceRoutes` is empty today,
  so a Glovo-audience token is refused everywhere. A route added here is the
  only way such a token reaches mctl-api. `internal/auth/oidc.go` reserves
  `GlovoWorkerUserID`, which nothing issues.
- Nothing in mctl-api outside tests calls `Store.Enqueue` or `ReadOutcome` yet.
  The control orchestration side is not wired in this repo.
- No `gcn_` connection registry exists in mctl-api. `connection_ref` and
  `install_revision` appear only as bridge row bindings, so there is no source
  of truth for "revoked connection" in this repo.
- `docs/bridge.md` documents the wire, routes, codes, gates and rollback. It
  states that the bridge is dark (`MCTL_BRIDGE_ENABLED` unset) and fake-only.

Deployed state checked:
- `mctl_list_services(team=admins)` (ArgoCD complete=true) lists
  mctl-agents-worker*, mctl-design, mctl-docs, mctl-support, mctl-web and
  umami. mctl-api is not a catalogue tenant service, so its runtime env
  (whether `MCTL_BRIDGE_ENABLED` is set) could not be observed through this
  tool.
- `$MCTL_GITOPS_ROOT/services/` has tenants `admins`, `karabu`, `labs` and
  `namax66`. `grep -r MCTL_BRIDGE` over `services/` found no match, and no
  `mctl-api` service directory exists there. mctl-api's own deployment config
  lives outside the paths available to this run, so it was not observed.
  `docs/bridge.md` states the bridge is dark by default. This proposal changes
  nothing about enablement either way.

## Proposed solution

### 1. Contract: v1alpha2 as an additive superset (vendored)

The canonical files are authored in mctl-agents (the source of #1045/#1044),
and this repo vendors them by sha256 into a new directory,
`internal/bridge/schema/v1alpha2/`:

- `command.schema.json`. This is v1alpha1 with three changes:
  - `schema_version` const is `bridge.mctl.ai/v1alpha2`;
  - `kind` also allows `read_history`, `read_preview`, `read_basket` and
    `read_prepare`;
  - the `allOf` approval rule is unchanged, so read kinds never carry or need
    `approval_ref`.
- `result.schema.json`. This is v1alpha1 plus an optional `read_result`, which
  refers to `read-result.schema.json`.
- `read-result.schema.json`. It requires `{kind, digest, size_bytes, data}`,
  with `oneOf` per kind on `data`. Every `data` requires
  `"provenance": {"const": "synthetic"}` and uses `additionalProperties: false`,
  bounded `maxItems` and `maxLength`, and integer minor-unit amounts. Indicative
  shapes, to be fixed in the mctl-agents review:
  - history: `orders[≤20]{order_ref, placed_at, status, total_minor, currency, item_count}`
  - preview: `items[≤20]{item_code, name≤64, unit_price_minor, available}`
  - basket: `lines[≤20]{item_code, quantity, line_total_minor}, total_minor, currency`
  - prepare: `{draft_ref, line_count, total_minor, currency, valid_until}`
- `PROVENANCE` (v1alpha2) gives the repo, PR, merge commit and the three
  sha256 values.

The v1alpha1 files and their `PROVENANCE` are not touched.
`compileSchemas()` compiles both URL sets. `ParseResult` reads only
`schema_version` first, then validates against the matching schema. `Result`
gains `ReadResult *ReadResult \`json:"read_result,omitempty"\``. Because the
field is `omitempty`, `Digest()` of a v1alpha1 result stays byte-identical,
and a golden test pins it.

### 2. Storage (additive DDL in `bridgeSchema`)

```sql
ALTER TABLE bridge_commands ADD COLUMN IF NOT EXISTS wire_version TEXT NOT NULL DEFAULT 'bridge.mctl.ai/v1alpha1';
ALTER TABLE bridge_commands DROP CONSTRAINT IF EXISTS bridge_commands_kind_chk;
ALTER TABLE bridge_commands ADD CONSTRAINT bridge_commands_kind_chk CHECK (operation_kind IN
  ('quote','read_status','place_order_fake','cancel_order_fake','read_history','read_preview','read_basket','read_prepare'));
-- read kinds must be v1alpha2; v1alpha1 kinds keep whatever they were enqueued with
ALTER TABLE bridge_commands ADD CONSTRAINT bridge_commands_read_wire_chk CHECK
  (operation_kind NOT IN ('read_history','read_preview','read_basket','read_prepare') OR wire_version = 'bridge.mctl.ai/v1alpha2');

CREATE TABLE IF NOT EXISTS bridge_read_results (
    result_ref         TEXT        PRIMARY KEY,          -- server-minted res_
    command_id         TEXT        NOT NULL UNIQUE,      -- one read row per command
    read_kind          TEXT        NOT NULL,
    tenant             TEXT        NOT NULL,
    owner_principal_id TEXT        NOT NULL,
    tenant_ref         TEXT        NOT NULL,
    principal_ref      TEXT        NOT NULL,
    connection_ref     TEXT        NOT NULL,
    install_revision   TEXT        NOT NULL,
    data               JSONB,                            -- NULL after expiry erase
    data_digest        TEXT        NOT NULL,
    size_bytes         INTEGER     NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at         TIMESTAMPTZ NOT NULL,
    erased_at          TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS bridge_read_results_expiry ON bridge_read_results (expires_at) WHERE data IS NOT NULL;
```

The constraint re-creation runs idempotently at startup inside the existing
`bridgeSchema` apply. The CHECK is widened, never narrowed, so existing rows
always satisfy it. The binding columns are copied from the locked
`bridge_commands` row and are never taken from the provider body.

### 3. Submission path (`submitTx`)

These steps are added after the existing lease, replay and consistency checks
and before the CAS:

1. `res.SchemaVersion` must equal `row.WireVersion`; otherwise
   `ErrBindingMismatch`.
2. A read kind requires the following; any violation is `ErrResultInconsistent`:
   - `provider_effect = none`;
   - no provider-chosen `result_ref`;
   - when `outcome=succeeded`, `read_result` present with
     `read_result.kind == row.Kind`;
   - no `read_result` on a non-read kind.
3. Canonicalize `read_result.data` (re-marshal the decoded typed struct) and
   check two things:
   - `len <= MaxReadDataBytes` (8 KiB), otherwise `ErrInvalidDocument`;
   - `sha256` equals the declared `digest`, otherwise `ErrBindingMismatch`.
4. Mint a `res_` ref with `randAlnum`, as in the existing ID helpers. Insert the
   `bridge_read_results` row in the same transaction, with `expires_at = now() +
   ReadTTL`.
5. `redacted()` stores `read_result` as a reference only:
   `{kind, digest, size_bytes, result_ref}`. The data is never written to
   `bridge_commands.result`. The signal outbox keeps carrying `command_id` and
   `result_digest` only. `Result.Digest()` still covers the full parsed body, so
   a replay with different data is `result_conflict`.
6. `SubmitOutcome` gains `ResultRef`. The handler returns it, and
   `auditBridge` logs `result_ref`, `read_digest` and `size_bytes`, never the
   data.

A replay of the same digest returns the existing row's ref (looked up by
`command_id`). Concurrent submitters serialize on `lockOwned`'s
`FOR UPDATE`, and `command_id UNIQUE` is a second barrier.

`ReadOutcome` adds `read_ref`, `read_digest`, `read_kind` and `read_expires_at`
(ids and digests only). This is the only thing the control side, mctl-agents
#1044, consumes.

### 4. Retrieval path (new store method + route)

`Store.FetchReadResult(ctx, q ReadFetch)`, where `ReadFetch` is
`{ResultRef, Digest, Tenant, PrincipalID}`. It reads the row by `result_ref`
and checks, in this order:

| Check | Code |
|---|---|
| row missing, tenant differs, or owner differs | `command_not_found` (404, no disclosure) |
| `expires_at <= now()` or `data IS NULL` | `command_expired` (409) |
| `ConnectionChecker.Active(ctx, tenant, connection_ref, install_revision)` is false | `binding_mismatch` (409) |
| the checker errors | new sentinel mapped to `bridge_unavailable` (503), the existing handler code |
| `subtle.ConstantTimeCompare(digest, data_digest) != 1` | `binding_mismatch` (409) |

On success it returns the stored JSON bytes unchanged.

`ConnectionChecker` is a new interface in `internal/bridge`.
`DenyConnectionChecker`, which returns an "unavailable" error, is the default,
the same fail-closed pattern as the default `WriteFence`. A real implementation
is wired only when the owner of `gcn_` lifecycle is decided (see Open
questions). Tests use a fake.

HTTP: `GET /api/v1/glovo/read-results/{result_ref}?digest=sha256:...`, handler
`BridgeReadResult` in `handlers_bridge.go`.

- It is mounted only when `opts.BridgeEnabled` is true, so it answers 404 when
  disabled.
- It is not under `/api/v1/bridge/`, so `bridgeProviderGate` refuses provider
  principals with 403.
- It is added to `glovoAudienceRoutes` for exactly `GET` and this path regex,
  so the Glovo-audience end-user token is its intended caller.
- The caller's tenant and principal come from `auth.UserFromContext`, never
  from the query.
- The response is `{result_ref, kind, digest, size_bytes, expires_at, data}`
  with `Cache-Control: no-store`.
- Audit records the ref, digest and code only.
- `BridgeService` gains `FetchReadResult`.

### 5. Expiry

A new `Store.EraseExpiredReads(ctx, limit)` runs
`UPDATE ... SET data=NULL, erased_at=now() ... FOR UPDATE SKIP LOCKED` in
bounded batches. The existing `Expirer` (`expiry.go`) calls it in each tick,
next to `ExpireDue`. A process-local metric,
`mctl_api_bridge_read_results_erased_total`, counts erased rows, in line with
the existing metrics and without tenant labels.

### 6. Config and docs

The read TTL is set by `MCTL_BRIDGE_READ_RESULT_TTL` (default 600 s, clamped to
1..900 s) in `cmd/api/main.go`. `docs/bridge.md` gains a "Read results
(v1alpha2)" section covering:

- the wire table;
- the new route and its codes;
- the statement that data never enters signals or logs;
- the explicit compatibility guarantee for v1alpha1;
- the rollback steps.

## Alternatives

1. Put the data in the result body itself and pass it on through the Temporal
   signal or `ReadOutcome`. This was rejected because raw user data would
   enter Temporal history and the control plane, which the issue forbids. It
   would also make `bridge_commands.result` a long-lived PII store.
2. Use a separate `glovo-read` protocol or route family for providers. This
   was rejected because the #957 amendment (mctl-gitops#2547) dropped it
   explicitly. It would also need a second provider auth surface and a second
   fence story.
3. Edit the v1alpha1 schemas in place (add `read_result` and the kinds). This
   was rejected because the vendored files are pinned byte for byte and must
   never be edited here. It would also silently change the meaning of a
   published version for existing consumers.
4. Let the provider choose `result_ref` (the v1alpha1 field). This was rejected
   for read kinds because a provider-chosen key invites collisions and probing
   across tenants. A server-minted ref keeps the provider unable to address any
   row it did not just create.

## Platform impact

- Migrations. The DDL is additive and idempotent at startup, consisting of a
  new column with a default, a new table and an index. The one widened CHECK
  is dropped and re-added in the same statement batch. All existing rows
  satisfy the widened constraint, and nothing is narrowed.
- Backward compatibility. v1alpha1 schema files, digests, projections and
  result digests are unchanged, and golden tests pin them. Existing v1alpha1
  providers never receive v1alpha2 commands unless a read kind is enqueued.
  The read kinds are new and not used by anyone today.
- Security.
  - Data is reachable only through mctl-api, after tenant, principal,
    connection, expiry and digest checks. Foreign and missing refs look
    identical (404).
  - Providers cannot read data back, because of the gate.
  - The write fence, `aar_` checks and `IssueWritePermit` logic are
    untouched, and read kinds stay `not_mutating`.
  - Fail-closed defaults apply: the bridge is disabled, and the connection
    checker refuses with 503.
- Resources. Each read row holds at most 8 KiB of data, it is erased after the
  TTL (at most 900 s), and the batch erase runs on the existing sweep. The load
  is negligible while the bridge is dark.
- Cross-repo ordering. The order is (1) canonical schema merged in mctl-agents,
  (2) this change, (3) mctl-telegram #1262 and mctl-agents #1044 consume it.
  This change is a hard dependency for P1 but does not enable anything by
  itself.
- Risks and mitigations:

  | Risk | Mitigation |
  |---|---|
  | The schema digest drifts from canonical | PROVENANCE test |
  | Data leaks into logs | handler and store tests assert absence of a sentinel string from audit, the slog buffer, the signal outbox row and `bridge_commands.result` |
  | No connection registry exists yet | fail-closed checker; recorded as an open question |
