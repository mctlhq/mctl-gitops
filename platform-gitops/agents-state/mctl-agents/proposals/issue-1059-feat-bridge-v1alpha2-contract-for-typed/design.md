# Design: issue-1059-feat-bridge-v1alpha2-contract-for-typed

## Amendment 2026-11-09 (c), round 2 of the AMEND PR

Re-review of mctl-gitops#2550 head `dc1fe6e5`. mctl-api references re-checked at
`ceac9ed`. The cross-slice seams of the Glovo M1 slices (approval-basket source, write
payload shape) are owned by mctl-api#957 design §6d; this contract supplies the shapes
they name. Where this section and older text disagree, this section wins; the older
passages are edited.

| Finding | Change |
|---|---|
| F1 (an empty basket or an all-unavailable preview cannot be a successful read) | `payload_read_preview` and `payload_read_basket` get a required boolean `empty`. `approval_basket` is required iff `empty` is false and forbidden iff it is true; `display` is then 0 items. The approval basket keeps `lines` minItems 1, so an empty basket can never be fingerprinted or approved. Valid fixtures for an empty basket and an all-unavailable preview; invalid fixtures for `empty: true` with a basket and `empty: false` without one. Crosswalk: #957 `empty: true` (#957 §6d.3), and prepare refuses it with `invalid_request`/`basket_empty` |
| F2 (`pho_` refs and cursors are not scoped to the binding) | New normative section "Provider MUST": `history_order_ref` and `cursor` resolve only within the command's `connection_ref` and `principal_ref`; an unknown or foreign value is `failed_terminal` with `provider_rejected`, never data. Consumer duty 10: mctl-api accepts a `pho_` or a cursor only if a prior history read for the same tenant, principal and connection returned it |
| F3 (no must-reject vector for duplicate keys that differ only in escaping) | Keys are compared after JSON unescaping (normative). `must-reject.json` adds `{"a":1,"\u0061":2}` at top level, and an escaped duplicate of `quantity` inside a basket line. Any `\u` escape in an object key is rejected as well, since every contract key is plain ASCII |
| F4 (the versioned claim envelope is required but undefined) | New `claim-response.schema.json` and README field table (§Claim response). The envelope version is independent of each command's `schema_version`; a provider that declares only v1alpha1 gets the v1alpha1 envelope byte for byte (`internal/api/handlers_bridge.go:200`). Fixtures for both |
| P3 F5 (date-time is format-only, a Go/Python parity gap) | Explicit RFC 3339 UTC patterns on `issued_at`, `expires_at` and `completed_at`; `placed_on` `^\d{4}-\d{2}-\d{2}$`; invalid fixture with a bad date-time |
| P3 F6 (stale passages) | The memo and "not observable" passages in Current state now state the verified PROVENANCE match; the `jcs-digest.json` categories are listed inline |
| P3 F7 (size numbers) | Preview `display` aligned to 0..30 and `unavailable_items` 0..30, disjoint from the basket lines; fees and discount bounded. Re-measured: preview 8,273 B, basket read 7,127 B, approval basket 3,135 B, history 10,673 B. The 12,288-byte payload cap is defense in depth that only a schema bypass can reach; over-cap is `invalid_document` at the mctl-api route and `payload_too_large` in the reference validator |
| P3 F8 (#986 vendors names this contract does not produce) | `SHA256SUMS` is the exact list a consumer vendors; mctl-api#986 vendors that list and nothing else |
| OPEN-1059-1 (write payload) | Narrowed: the shape is fixed by mctl-api#957 §6d.3 (the `place_order_fake` payload is exactly an approval basket, no wrapper). Still open: which issue and version adds the write-command schema |

## Amendment 2026-11-09 (b)

Resolves the independent review of approval digest
`sha256:b682bd046bf6cb9bc4a5ad341afd2c1c58216d363ecfab8d7adfe1731a9458b0`
(mctl-agents#1059 comment 6745621467: 3 P1, 5 P2, 7 P3). Each finding was re-checked:
`bridgeMaxBody = 16 << 10` (mctl-api `internal/api/handlers_bridge.go:42`, read at
`:216`), the hard-coded v1alpha1 claim envelope (`:200`), the "never accepted from the
provider" rule (`internal/bridge/schema.go:124-126`), and the v1alpha1 sha256 pins in
mctl-api `internal/bridge/schema/PROVENANCE`, which equal mctl-agents `origin/main`
`docs/spikes/1043/` byte for byte. The worst-case sizes below were measured with a JCS
serializer over maximal values. This section replaces the older text; nothing that
contradicts it survives.

| Review finding | Fix in this proposal |
|---|---|
| P1-1 65536-byte payload cap is 4x the 16 KiB result route limit | The cap now follows the transport. The whole result body is at most **16384** bytes (= `bridgeMaxBody`), and the JCS payload at most **12288** bytes. The bounds were tightened so the worst case fits: history 10,673 B, basket 7,109 B, preview 5,605 B, envelope without payload 910 B. `item_name` is printable ASCII with no JSON-escaped character, so bytes equal characters. Fixtures sit at exactly the cap and one byte over (§Size cap). The transport limit is not raised |
| P1-2 the read payload cannot be the `aar_` fingerprint (volatile fields, unordered/duplicate lines, no fees/total/store) | A separate **approval basket** projection, `approval-basket.schema.json`: store ref, currency, lines sorted by unique `item_code` (an unsorted or duplicate list is rejected), quantity, integer unit price, every fee, discount and total. It has no display, availability or time fields. `basket_fingerprint = "sha256:" + hex(sha256(JCS(approval_basket)))` is the **single** fingerprint that `aar_` binds, that mctl-api computes at preview, prepare and dispatch, and that the mctl-api#989 fence recomputes from the command payload. The vectors include must-reject cases. #988's `mctl-basket/v1` is replaced (§Approval basket) |
| P1-3 params/payloads do not fit the #957 routes | Derived from #957 row by row (§Crosswalk). History entries use their own prefix `pho_` (never `ordr_`), `limit` 1..20, opaque `cursor`/`next_cursor`, and per-order lines. Preview takes `{history_order_ref}` and returns the approval basket, display lines and `unavailable_items`. Basket returns `store_name`, the approval basket and display lines |
| P2-1 stored bytes unspecified; `1.0`/`1e2` pass `"type":"integer"` | Normative: consumers store exactly `JCS(payload)` (TEXT/BYTEA, never JSONB) and re-verify `sha256(stored) == payload_digest` when serving. An integer field must be a JSON integer token. A token with `.`, `e` or `E`, or a boolean, is rejected by a raw-bytes pre-check. Fixture `quantity: 1.0` |
| P2-2 parser-differential rejections are Python-only | `vectors/must-reject.json` holds raw-text cases: duplicate keys at top level and nested, lone high and low surrogates, `1e400`, `NaN`, 2^53+1, `1.0` and `1e2` in integer positions, and `true` for an integer. Every consumer, Go included, MUST run a raw-bytes validator before schema validation and reject these identically. `check_read_result` takes bytes. The >2^53 rule is labelled an I-JSON profile rule on top of RFC 8785 |
| P2-3 consumer duties missing; the binding echo contradicts v1alpha1 | The result no longer carries `tenant_ref`, `principal_ref`, `connection_ref` or `install_revision_ref`: bindings come only from the consumer's own command row. A normative "Consumer MUST" list is added (§Consumer duties) |
| P2-4 no version negotiation or evolution rule | Each claimed command carries its own `schema_version`. The claim response is versioned. mctl-api leases read kinds only to providers whose server-side config declares v1alpha2. A provider drops an unknown version without side effects, and mctl-api expires it. Any schema byte change is a new version and a new `$id` (§Versioning) |
| P2-5 no `required` lists, so `{}` is valid | Every payload, line and order field is required unless named optional. `minItems: 1` where an empty list has no meaning. One missing-field invalid fixture per kind |
| P3-1 unbounded free text | `item_name` and `store_name` match `^[A-Za-z0-9 .,'()-]{1,60}$`. `error_detail` is printable ASCII, at most 128 bytes |
| P3-2 full timestamps | `placed_on` is a date only; the basket has no time field |
| P3-3 `workflow_id`/#1045 open question | Closed. #1045 is merged, and the v1alpha1 files match mctl-api's PROVENANCE (command `b857f62b…6dae1`, result `c91bb86e…9354f`). T1 pins those two values plus the 8 fixtures. `workflow_id` stays forbidden as defence in depth |
| P3-4 wrong RFC section reference | Vectors cite RFC 8785 §3.2.2 (sample object) and §3.2.3 (sorting example) separately |
| P3-5 Python `bool` is an `int` | `tools/jcs.py` tests `bool` before `int`. Vectors `[true,false,null]` and `{"a":true}` |
| P3-6 `cancel_requested` absent | Stated: reads cannot be cancelled by the provider protocol. Expiry, or a consumer-side cancel before the claim, is the only stop |
| P3-7 ref prefixes unconfirmed | Confirmed against mctl-api in this PR: `rdq_`, `irv_`, `pho_` and `pst_` are unused in mctl-api `ceac9ed`. `bsk_` is dropped (the basket read takes no ref). #957's `gpv_` preview id stays mctl-api-side |

Skipped findings: none.


## Current state

- **v1alpha1 contract.** `docs/spikes/1043/command.schema.json` (`$id`
  `https://mctl.ai/schemas/bridge/v1alpha1/command.schema.json`) and
  `docs/spikes/1043/result.schema.json`. Both are JSON Schema 2020-12 with
  `additionalProperties: false`. The command requires `execution_id` (`^we_...`),
  `work_item_id` (`^wi_...`), `order_ref` (`^ordr_...`), `intent_hash`, and has
  `kind` in `quote | place_order_fake | cancel_order_fake | read_status`. An `allOf/if`
  requires `approval_ref` for the two mutating kinds. Its `payload` is a small fixed
  object (`item_codes`, `quantity_total`, `note`). The result requires `execution_id`,
  `lease_token`, `worker_identity`, `outcome`, `provider_effect`, and carries only an
  optional `result_ref` (`^res_...`). There is no data payload. The command schema has
  no `workflow_id` field, even though the issue says it does (closed in the amendment, P3).
- **Fixtures and tests.** `docs/spikes/1043/fixtures/*.json` contains 2 valid and
  6 invalid fixtures. `tests/test_spike_1043_contracts.py` validates them with
  `jsonschema.Draft202012Validator` and the format checker, through a `CASES` table of
  (fixture, schema, valid, expected error path substring). It also asserts
  `jsonschema==4.26.0` is locked in `uv.lock` and declared in `pyproject.toml`'s dev group,
  and rejects credential-shaped strings (JWT, `Bearer `, `MCTL_TOKEN=`) in fixtures.
- **Memo.** `docs/spikes/1043-cross-namespace-dispatch.md` (STATUS `API_BRIDGE_SELECTED`)
  defines the bridge flow: mctl-api outbox, provider claim/result with leases, and an
  `aar_` consume for mutations. It also says the schemas are "proposals consumed by no
  service". That is no longer true: mctl-api vendors them, and its
  `internal/bridge/schema/PROVENANCE` sha256 pins equal `docs/spikes/1043/` byte for
  byte (verified at mctl-api `ceac9ed`, amendment (b)).
- **Canonical JSON in this repo is not JCS.** `orchestrator/context_snapshot.py`
  `_canonical_json` / `canonical_json` uses `json.dumps(sort_keys=True,
  separators=(",", ":"), allow_nan=False)`, which keeps `ensure_ascii=True`. Running it on
  a value containing `é` and an emoji gives the escapes `\u00e9\ud83d\ude00`
  (verified locally with `json.dumps`), but RFC 8785 requires the raw UTF-8 characters.
  It also sorts keys by code point rather than by UTF-16 code units, and it formats floats
  with Python `repr` rather than ECMAScript number serialization (for example Python
  emits `1e-07` where ES emits `1e-7`). That function hashes context
  snapshots, capabilities and assurance artifacts, so it must not change. Bridge v1alpha2
  needs its own JCS implementation. No JCS library (`rfc8785`, `canonicaljson`) is in
  `uv.lock`.
- **Packaging.** The `Dockerfile` copies only `orchestrator/`, `config/` and `agents/` into
  the image, so `docs/` and `tools/` are repo-only. `tools/` has no `__init__.py`; tests
  already import from it (`tests/test_agent_isolation_audit.py`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT` / `/workdir/mctl-gitops/platform-gitops/services/`: listed the
  tenants (`admins`, `karabu`, `labs`, `namax66`). There is no `mctl-api` service
  directory under `services/` in this checkout, so mctl-api's deployed config could not
  be observed here. `services/labs/mctl-telegram/values.yaml` mentions "bridge" only for
  the unrelated bot-start bridge (`BOT_START_BRIDGE_TOKEN`). No deployed configuration
  refers to the command bridge or a `ReadBridge`.
- No mctl MCP tool calls were made. The contract is data-only and changes no deployed
  service, so no runtime state is relevant to it.
- The vendored copy in mctl-api (`internal/bridge/schema/PROVENANCE` at `ceac9ed`) and
  the merged #1045 change were checked in amendment (b): the pins match.

## Proposed solution

Add a new, additive contract directory. Nothing under `docs/spikes/1043/` is touched, so
mctl-api's sha256 pin of v1alpha1 keeps matching.

```
docs/contracts/bridge/v1alpha2/
  README.md                      # scope, field tables, crosswalk, consumer and provider MUSTs, versioning, vendoring
  claim-response.schema.json     # $id https://mctl.ai/schemas/bridge/v1alpha2/claim-response.schema.json
  read-command.schema.json       # $id https://mctl.ai/schemas/bridge/v1alpha2/read-command.schema.json
  read-result.schema.json        # $id https://mctl.ai/schemas/bridge/v1alpha2/read-result.schema.json
  approval-basket.schema.json    # $id https://mctl.ai/schemas/bridge/v1alpha2/approval-basket.schema.json
  fixtures/
    read-command.{history,preview,basket}.valid.json
    read-command.with-{order-ref,execution-id,workflow-id}.json      # invalid
    read-command.kind-prepare.json, read-command.params-wrong-kind.json  # invalid
    read-result.{history,preview,basket}.valid.json
    read-result.failed.valid.json                 # no payload
    read-result.failed-with-payload.json          # invalid
    read-result.{history,preview,basket}.missing-field.json   # invalid, one per kind
    read-result.with-binding-echo.json            # invalid (tenant_ref from the provider)
    read-result.quantity-float.json               # invalid (quantity 1.0, raw-bytes check)
    read-result.extra-field.json                  # invalid (customer_email)
    read-result.at-cap.json                       # valid, body exactly 16384 bytes
    read-result.over-cap.json                     # schema-valid, rejected (16385 bytes)
    read-result.digest-mismatch.json              # schema-valid, rejected
    read-result.{preview,basket}.empty.valid.json              # empty: true, no approval basket
    read-result.preview.all-unavailable.valid.json             # empty: true, unavailable_items only
    read-result.{empty-with-basket,nonempty-without-basket}.json  # invalid
    read-result.bad-date-time.json                             # invalid (completed_at not RFC 3339 UTC)
    claim-response.{v1alpha1-only,v1alpha2}.valid.json
    claim-response.{extra-field,too-many}.json                 # invalid
    approval-basket.valid.json
    approval-basket.{unsorted,duplicate-item,total-mismatch,display-field}.json  # invalid
  vectors/
    jcs-digest.json              # positive JCS vectors
    basket-fingerprint.json      # approval basket -> canonical bytes -> fingerprint
    must-reject.json             # raw-text inputs every consumer must reject
  SHA256SUMS
tools/jcs.py                     # stdlib-only RFC 8785 canonicalizer + raw-bytes pre-check
tools/bridge_contract.py         # reference validator over raw bytes + CLI
tests/test_bridge_v1alpha2_contract.py
```

### read-command.schema.json

`schema_version` const `bridge.mctl.ai/v1alpha2`, `additionalProperties: false`, every
field below required unless marked optional.

| Field | Constraint |
|---|---|
| `command_id` | `^cmd_[A-Za-z0-9]{26}$` |
| `request_id` | `^rdq_[A-Za-z0-9]{26}$`, the read's idempotency key |
| `kind` | `read_history`, `read_preview`, `read_basket` |
| `attempt` | integer 1..100 |
| `tenant_ref`, `principal_ref`, `connection_ref` | v1alpha1 patterns (`tnr_`, `prr_`, `gcn_`) |
| `install_revision_ref` | `^irv_[A-Za-z0-9]{16,40}$` |
| `issuer` | const `mctl-api` |
| `audience` | `^provider:[a-z0-9-]{1,32}$` |
| `nonce` | `^[A-Za-z0-9_-]{22}$` |
| `issued_at`, `expires_at` | date-time and pattern `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,9})?Z$` (RFC 3339 UTC; Python does not enforce `format`) |
| `ttl_seconds` | integer 1..300 |
| `lease_token` | optional, v1alpha1 pattern |
| `params` | object, per kind |

The command gives the provider the refs it needs to act. The result never returns them.
Order and workflow fields are rejected by `additionalProperties: false` and by an
explicit `not/anyOf` over `execution_id`, `work_item_id`, `order_ref`, `workflow_id`,
`approval_ref` and `intent_hash`. There is no `cancel_requested`: the provider protocol
cannot cancel a read. Expiry, or a consumer-side cancel before the claim, is the only
stop.

Per-kind params (`allOf`/`if`/`then`, each `additionalProperties: false`):
- `params_read_history`: `limit` integer 1..20 (required), `cursor`
  `^[A-Za-z0-9_-]{1,64}$` (optional, opaque, provider-issued).
- `params_read_preview`: `history_order_ref` `^pho_[A-Za-z0-9]{16,40}$` (required).
- `params_read_basket`: no fields (`{}`; the principal's current basket).

### read-result.schema.json

`schema_version` const `bridge.mctl.ai/v1alpha2`, `additionalProperties: false`.

Required: `command_id`, `request_id`, `kind`, `lease_token`, `attempt`,
`worker_identity`, `outcome`, `provider_effect`, `completed_at`. `completed_at` has the
same RFC 3339 UTC pattern as `issued_at`; `lease_token` and `worker_identity` keep their
v1alpha1 patterns; `attempt` is an integer 1..100. There is **no**
`tenant_ref`, `principal_ref`, `connection_ref` or `install_revision_ref`: bindings are
private to the consumer, as in v1alpha1 (`internal/bridge/schema.go:124-126` in
mctl-api).

- `outcome`: `succeeded | failed_retryable | failed_terminal | cancelled`.
- `provider_effect`: const `none`.
- `error_code`: `none | stale_lease | expired | provider_unavailable | provider_rejected |
  payload_too_large | internal`. `error_detail`: printable ASCII, at most 128 bytes.
- `payload` and `payload_digest` (`^sha256:[0-9a-f]{64}$`) are both required when
  `outcome` is `succeeded`, and both forbidden otherwise.
- Shared shapes:
  - `item_code` `^FAKE-[A-Z0-9-]{1,32}$`;
  - `display_name` `^[A-Za-z0-9 .,'()-]{1,60}$` (no character JSON escapes, so bytes
    equal characters);
  - `currency` `^[A-Z]{3}$`;
  - every money and count field is an integer, as a JSON integer token (§Numbers).
- `payload_read_history` (required: `orders`; optional: `next_cursor`): `orders` 0..20 of
  `{history_order_ref` `pho_`, `placed_on` `^\d{4}-\d{2}-\d{2}$`, `status` `delivered|cancelled|in_progress`,
  `total_minor` 0..10000000, `currency`, `line_count` 1..100, `lines` 1..5 of
  `{item_code, quantity 1..100}`}`. Only the first five lines are carried; `line_count`
  says how many there are. The preview gives the full basket.
- `payload_read_preview` (required: `empty`, `display`, `unavailable_items`;
  `approval_basket` required iff `empty` is false and forbidden iff it is true):
  `display` 0..30 of `{item_code, item_name}`, `unavailable_items` 0..30 of
  `item_code`, disjoint from the basket's lines. `empty: true` (every item unavailable,
  or nothing to re-order) carries `display: []`.
- `payload_read_basket` (required: `empty`, `display`; `approval_basket` iff `empty` is
  false; optional: `store_name`): `display` 0..30 of `{item_code, item_name}`.
  `empty: true` (the current basket has no lines) carries `display: []`.
- An empty read is a valid, successful read. It can be shown; it has no approval basket,
  so it can never be fingerprinted, prepared or approved (mctl-api#957 §6d.3 refuses
  prepare with `basket_empty`).
- Every `display` entry's `item_code` must appear in the basket's lines; the validator
  checks it.

### Approval basket (`approval-basket.schema.json`)

The approval basket is the canonical projection of what a human approves. It is
separate from the read payload. A read payload *embeds* it, and the digest of the
payload stays a transport-integrity digest only.

| Field | Constraint |
|---|---|
| `v` | const `mctl-approval-basket/v1` (version tag inside the hashed bytes) |
| `store_ref` | `^pst_[A-Za-z0-9]{16,40}$`, the provider's stable store id |
| `currency` | `^[A-Z]{3}$` |
| `lines` | 1..30 of `{item_code, quantity 1..100, unit_price_minor 0..1000000}` |
| `subtotal_minor` | integer, `= sum(quantity * unit_price_minor)` |
| `delivery_fee_minor`, `service_fee_minor`, `discount_minor` | integers 0..10000000 |
| `total_minor` | integer, `= subtotal + delivery_fee + service_fee - discount`, >= 0 |

All fields are required, with `additionalProperties: false`. The basket holds no name,
availability flag, timestamp or basket id. Rules that JSON Schema cannot express are
checked by the reference validator, and consumers MUST check them too:
- `lines` are sorted ascending by `item_code` (byte order, which equals UTF-16 order for
  this ASCII pattern), and `item_code` is unique. Producers emit them sorted. Consumers
  reject unsorted lists and never re-sort them.
- The two arithmetic identities hold.

`basket_fingerprint = "sha256:" + lowercase hex(SHA-256(JCS(approval_basket)))`.

This is the **single** M1 basket fingerprint:
- mctl-api computes it from the preview's approval basket (mctl-api#957) and binds it to
  the order (#988) and the `aar_` (#989);
- #985 compares it at dispatch;
- the #989 write fence recomputes it from the command payload;
- mctl-agents#1044 carries and compares it.

A provider-supplied value is only ever compared. Because prices, fees and totals are
inside, any price change changes the fingerprint and invalidates the approval.
`vectors/basket-fingerprint.json` pins `{name, input_text, canonical, fingerprint}` for:
a minimal basket; a 30-line basket; the same basket with the input keys permuted (same
fingerprint); one unit price changed by 1 (different fingerprint); the delivery fee
changed (different fingerprint). Its `must_reject` cases are: unsorted lines, a duplicate
`item_code`, a wrong subtotal, a wrong total, an extra `item_name` field, and
`quantity: 1.0`.

The command payload of a Glovo `place_order_fake` write is not part of this read
contract, but its shape is fixed (mctl-api#957 §6d.3, amended (c)): the payload **is**
an approval basket, exactly this schema, with no wrapper object and no other top-level
field, so the #989 fence parses it whole. Which issue and version adds that write
command schema is OPEN-1059-1.

### Crosswalk to mctl-api#957

| #957 tool / field | v1alpha2 source |
|---|---|
| `history {limit<=20, cursor?}` | `params_read_history {limit, cursor?}` |
| history item ref | `history_order_ref` (`pho_`; never `ordr_`, which is mctl's own order index) |
| history `next_cursor?` | `payload_read_history.next_cursor` |
| history item summary | `placed_on`, `status`, `total_minor`, `currency`, `line_count`, `lines` |
| `POST /previews {order_ref}` | `params_read_preview {history_order_ref}`. The #957 wire field stays `order_ref` (the facade is unchanged); #957 is amended so its value is the `pho_` history ref, which mctl-api copies into `history_order_ref` |
| preview `items` | `approval_basket.lines` joined with `display` (empty list when `empty` is true) |
| preview / basket `empty` | `empty` (#957 §6d.3: shown, never prepared) |
| preview `unavailable_items` | `unavailable_items` |
| preview `fingerprint` | computed by mctl-api: `basket_fingerprint(approval_basket)` |
| preview `preview_id`, `expires_at` | minted by mctl-api (`gpv_`), not from the provider |
| basket `store_name?` | `store_name` |
| basket items | `approval_basket.lines` joined with `display` |
| basket `totals_label` | formatted by mctl-api from `subtotal_minor`, the fees, `discount_minor`, `total_minor` and `currency` |

### Size cap

The transport decides the cap. mctl-api reads at most `bridgeMaxBody = 16384` bytes per
result body (`handlers_bridge.go:42`). The contract therefore requires:
- the whole result body is at most **16384** bytes;
- `JCS(payload)` is at most **12288** bytes.

Worst cases were measured with every field at its maximum (40-character refs, 32-character
item codes, 60-character names, maximum integers):

| Payload | Worst case |
|---|---|
| history, 20 orders x 5 lines | 10,673 B |
| basket read, 30 lines with names and a 60-character store name | 7,127 B (re-measured (c)) |
| preview, 30 lines with names and 30 unavailable | 8,273 B (re-measured (c)) |
| approval basket alone, 30 lines | 3,135 B |
| result envelope without payload | 910 B |

None of the allowed characters is escaped by JSON, so the measurement is exact. No
schema-valid payload reaches the 12,288-byte payload cap: the cap is defense in depth
against a schema bypass. Fixtures sit at exactly 16384 bytes and at 16385 bytes for the
body. Over-cap is `invalid_document` at the mctl-api route and `payload_too_large` in
the reference validator. The transport limit is not raised.

### Numbers, raw bytes and parser differentials

- Integer fields MUST be JSON integer tokens: `-?(0|[1-9][0-9]*)`. A token with `.`, `e`
  or `E` (`1.0`, `1e2`), or `true`/`false` in an integer position, is rejected. JSON
  Schema `"type":"integer"` alone accepts `1.0`, so the reference validator checks the
  raw tokens first.
- Every consumer, Go included, runs a raw-bytes pre-check before schema validation. It
  rejects duplicate keys at any depth, compared **after JSON unescaping** (so `"a"` and
  `"\u0061"` are the same key), any `\u` escape inside an object key (every contract
  key is plain ASCII), lone surrogate escapes (high or low), `NaN`,
  `Infinity`, `1e400`, and integers outside ±(2^53-1). The last rule is an I-JSON profile
  rule on top of RFC 8785, which would itself serialise such a value.
  `vectors/must-reject.json` holds these as raw text, including
  `{"a":1,"\u0061":2}` at top level and a basket line with `"quantity"` and
  `"\u0071uantity"`, and both the Python reference and
  each Go consumer's CI MUST reject every entry. Go's `encoding/json` accepts duplicate
  keys and replaces lone surrogates, so a Go consumer needs its own token-level check.
- `tools/bridge_contract.py check_read_result(raw: bytes)` and `check_read_command(raw:
  bytes)` take bytes, not parsed documents.

### Digest and stored bytes

- `payload_digest = "sha256:" + hex(sha256(JCS(payload)))` is transport integrity for the
  read payload only. The envelope's lease and attempt fields change across retries, so
  they are not digested.
- A consumer stores exactly `JCS(payload)` as TEXT or BYTEA, never as JSONB. When it
  serves the payload, it recomputes `sha256(stored)` and compares it with the stored
  digest without re-parsing, and fails closed on a mismatch.
- `tools/jcs.py` (stdlib only):
  - Objects: keys are sorted by UTF-16 code units, and duplicates are rejected.
  - Strings: RFC 8785 §3.2.2.2 escaping, and lone surrogates are rejected.
  - Numbers: ES serialization. NaN and Infinity are rejected, and so is any value
    outside ±(2^53-1).
  - `bool` is tested before `int`.
  - Functions: `canonicalize(value)`, `canonicalize_text(text)`, `digest(value)` and
    `precheck(raw)`.
- `vectors/jcs-digest.json` covers: key sorting by UTF-16 code units (including a
  supplementary-plane key), control-character escapes, DEL (U+007F, unescaped), the ES
  number thresholds `1e21`, `1e20` and `1e-7`, `-0` (serialised `0`), nested objects
  and arrays, empty object and array, and `true`/`false`/`null`. It adds
  `[true,false,null]` and `{"a":true}`, and cites RFC 8785 §3.2.2 (sample object) and
  §3.2.3 (sorting example) as separate vectors. The values are cross-checked against an
  independent Go implementation, recorded in the README.

### Consumer duties (normative README section, "Consumer MUST")

A consumer (mctl-api #986/#957/#988/#989) MUST:
1. take tenant, principal, connection and install-revision bindings only from its own
   stored command row. The result carries none, and a result that adds any is invalid;
2. require `result.kind == stored command kind`, and require `command_id` and
   `request_id` to match. The lease and attempt must be current;
3. reject a result that arrives after the command's `expires_at`;
4. run the raw-bytes pre-check, then the schema, then the size cap. It MUST recompute
   `payload_digest` and never trust it;
5. store only `JCS(payload)`, and re-verify the digest on every serve;
6. re-check at serve time, in the mctl-api#957 handler: the binding, the TTL, connection
   revocation, the install revision and the `glovo:read` scope;
7. never persist `lease_token` (v1alpha1 redacts it as well);
8. never write a raw payload to an outbox, signal, audit row, log or Temporal history;
9. compute `basket_fingerprint` itself from the approval basket, and only compare any
   fingerprint received from elsewhere;
10. accept a `pho_` history ref or a `cursor` in a read command only if a prior history
    read for the same tenant, principal and connection returned it (defense in depth for
    the provider duty below).

### Provider duties (normative README section, "Provider MUST")

A provider (mctl-telegram#1262 and any later one) MUST:
1. resolve `history_order_ref` and `cursor` only within the command's `connection_ref`
   and `principal_ref`. A ref or cursor it did not issue to that binding, or one it
   cannot resolve, is `outcome: failed_terminal` with `error_code: provider_rejected`,
   never data from another binding;
2. issue `pho_` refs and cursors that are opaque and unguessable, and never reuse one
   across bindings;
3. emit approval-basket lines sorted and unique, and never put a value it did not read
   from the bound account into a payload.

### Claim response (`claim-response.schema.json`)

The claim response envelope has its own version, independent of each command's
`schema_version`.

| Field | Constraint |
|---|---|
| `schema_version` | `bridge.mctl.ai/v1alpha1` for a provider that declares only v1alpha1; `bridge.mctl.ai/claim/v1alpha2` for a provider that declares v1alpha2 |
| `commands` | array 0..10 (mctl-api `MaxClaimBatch = 10`, `internal/bridge/store.go:61`, `:572-573`); each item is a command whose own `schema_version` is one the provider declared |

`additionalProperties: false`. For a provider that declares only v1alpha1, mctl-api
sends the v1alpha1 envelope unchanged, byte for byte what
`internal/api/handlers_bridge.go:200` writes today, and only v1alpha1 commands in it.
Fixtures: `claim-response.v1alpha1-only.valid.json`, `claim-response.v1alpha2.valid.json`
(one v1alpha1 and one v1alpha2 command), an extra field and 11 commands (invalid). Who
implements the envelope switch in mctl-api stays OPEN-1059-2; its shape is fixed here.

### Versioning

- Each claimed command carries its own `schema_version`. The claim response envelope
  states the claim protocol version (§Claim response), and lists commands of any version
  the provider declared.
- mctl-api MUST NOT lease a v1alpha2 command to a provider whose server-side config
  (`BridgeProviderConfig`) does not declare `bridge.mctl.ai/v1alpha2`. The provider is
  never trusted to filter.
- A provider that receives an unknown `schema_version` drops it without side effects.
  mctl-api expires the command as `expired`.
- Any byte change to a schema is a new `schema_version` and a new `$id`. A pinned version
  is immutable, and nothing is "additive within a version". Fixture: a v1alpha2 command
  inside a v1alpha1 claim envelope is rejected by a v1alpha1 consumer.

### Vendoring

The README specifies one-way vendoring. Consumers copy `docs/contracts/bridge/v1alpha2/`
verbatim and pin each file by the sha256 in `SHA256SUMS`. `SHA256SUMS` is the exact
list of files a consumer vendors (mctl-api#986 vendors that list and nothing else). They never edit the vendored
copy, and any change starts here. A test regenerates `SHA256SUMS` in memory and compares
it with the committed file.

## Alternatives

1. **Extend v1alpha1 in place (add read kinds, make order fields conditional).** Dropped.
   It changes the bytes mctl-api#968 pinned, it violates "v1alpha1 unchanged", and
   turning required fields into conditional ones weakens the write contract.
2. **A single v1alpha2 `command.schema.json` covering writes and reads via `oneOf`.**
   Dropped for now. It duplicates the v1alpha1 write shape under a new version for no
   consumer benefit, doubles the review surface, and `oneOf` error messages are poor. Reads
   and writes take different paths anyway (reads go through `ReadBridge` in-process with
   no Temporal signal), so separate read-only schemas match the architecture. A later
   version can unify them if needed.
3. **Reuse `orchestrator/context_snapshot.canonical_json` for the digest.** Dropped. It is
   not RFC 8785: it escapes non-ASCII, sorts by code point and uses Python float
   formatting. Go consumers would not reproduce it with a standard JCS library, and
   changing it would invalidate every existing snapshot and capability hash. A third-party
   JCS package (`rfc8785` on PyPI) was also considered. It was dropped to keep the lock
   unchanged and the reference small and auditable; the vectors make the choice
   verifiable either way.
4. **Use the read payload digest as the approval fingerprint.** Rejected (review P1-2):
   volatile display and time fields, unordered and duplicate lines, and no fees or total.
5. **Raise the mctl-api result body limit to fit a 64 KiB payload.** Rejected (review
   P1-1): the bounds were tightened instead. The measured worst case fits in 16 KiB.

## Platform impact

- **Migrations:** none. New files only; no runtime code, no image change (`docs/` and
  `tools/` are not copied into the image), no gitops change, no Temporal or authorization
  change.
- **Backward compatibility:** v1alpha1 files are untouched, and the existing
  `tests/test_spike_1043_contracts.py` stays as-is. A new test asserts that the v1alpha1
  files' sha256 values equal those recorded at the time this lands, which guards the
  "unchanged" promise.
- **Resource impact:** a few dozen small JSON files and one extra test module (well under
  a second).
- **Risks and mitigations:**
  - *Go/Python JCS disagreement.* Mitigated by golden vectors with RFC 8785 sample
    values, and by keeping payloads integer-only.
  - *Contract does not fit #986, #957 or the provider slice.* Mitigated by the #957
    crosswalk, the consumer-duty list and the digest-bound owner approval. Any change is
    a new schema version.
  - *Ref prefix collision with existing mctl-api ids.* Checked: `rdq_`, `irv_`, `pho_` and
    `pst_` do not occur in mctl-api `ceac9ed`.
  - *A second canonical-JSON rule in the repo* (the ADR 009 "disagreeing hash convention"
    risk noted in `context_snapshot.hash_bytes`). Mitigated by scoping: `tools/jcs.py`
    is documented as bridge-contract-only, and context snapshots keep their rule.

## Open questions

See requirements.md (OPEN-1059-1 .. OPEN-1059-3).
