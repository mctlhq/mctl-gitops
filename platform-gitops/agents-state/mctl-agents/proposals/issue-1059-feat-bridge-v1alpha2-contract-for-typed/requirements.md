# Bridge v1alpha2: additive contract for typed read commands and results

## Context

The mctl-api command bridge contract v1alpha1 (`docs/spikes/1043/command.schema.json` and
`result.schema.json`, `schema_version` `bridge.mctl.ai/v1alpha1`) cannot carry reads.
Every command must include `execution_id` (`we_`), `work_item_id` (`wi_`) and `order_ref`
(`ordr_`), but history, preview and basket reads happen before any order or `we_` exists.
The result has no payload, only an optional opaque `result_ref`. The independent review of
mctlhq/mctl-api#986 found that #986 tried to define the read contract inside mctl-api. On
2026-11-09 the owner decided that the contract is defined first, in its canonical home in
this repo, and that each consumer repo then gets its own implementation slice.

This proposal adds bridge **v1alpha2** as an additive, data-only contract: JSON Schemas for
read commands and read results, golden fixtures, and RFC 8785 (JCS) digest test vectors. It
also adds a stdlib-only Python JCS reference implementation that the vectors are checked
against. Go consumers (mctl-api, mctl-telegram) vendor the same files, pinned by sha256, and
must pass the same vectors. v1alpha1 stays byte-for-byte unchanged and remains the contract
for every write except the Glovo `place_order_fake` (round 7, the one v1alpha2 write, defined here
in `command-place-order-fake.schema.json`) and for `read_status`.

## User stories

- AS the mctl-api `ReadBridge` implementer (mctlhq/mctl-api#986) I WANT a pinned, versioned
  schema for read commands and typed read results SO THAT I can store and serve reads
  without inventing the contract in mctl-api.
- AS the provider read-path implementer (extension of mctlhq/mctl-telegram#1262) I WANT
  bounded, typed result payloads per read kind SO THAT the provider worker can return data
  that mctl-api accepts unchanged.
- AS a consumer storing raw result bytes I WANT a canonical digest with shared golden vectors
  SO THAT Go and Python compute identical digests and the stored bytes can be re-verified
  when served.
- AS the platform owner I WANT the contract reviewed and approved, bound to its digest,
  before any implementation slice SO THAT the slices cannot drift from what was approved.

## Acceptance criteria (EARS)

Amended 2026-11-09 (b) and (c); design.md has the finding -> fix tables.

v1alpha1 and versioning
- WHEN the v1alpha2 contract lands THE SYSTEM SHALL keep every file under
  `docs/spikes/1043/` byte-identical, pinned in T1 by the mctl-api PROVENANCE sha256
  values (command `b857f62b…6dae1`, result `c91bb86e…9354f`) and the fixture hashes.
- THE SYSTEM SHALL treat any byte change to a pinned schema as a new `schema_version` and
  `$id`. Nothing is "additive within a version".
- THE README SHALL require that each claimed command carries its own `schema_version`,
  that the claim response states its protocol version, that mctl-api leases a v1alpha2
  command only to a provider whose server-side config declares v1alpha2, and that a
  provider drops an unknown version without side effects.
- THE SYSTEM SHALL define `claim-response.schema.json` (`schema_version`, `commands`
  0..10, `additionalProperties: false`), with an envelope version independent of each
  command's `schema_version`, and SHALL keep the v1alpha1 envelope byte-identical for a
  provider that declares only v1alpha1. (amended (c))
- THE SYSTEM SHALL define the Glovo `place_order_fake` write command field by field as a delta
  over the v1alpha1 command (design §Write command): `schema_version` v1alpha2, `kind` const,
  `approval_ref` required, the approval basket as `payload`, no `install_revision_ref`,
  `ttl_seconds` 1..900, the RFC 3339 UTC timestamp pattern, `cancel_requested` and `lease_token`
  as in v1alpha1. A missing required field, an extra top-level field and `install_revision_ref`
  SHALL each be rejected. (round 7)
- THE SYSTEM SHALL answer that command with the unchanged v1alpha1 `result.schema.json`; the
  read result schema SHALL reject it. (round 7)

Read command
- WHEN a read command has `schema_version` `bridge.mctl.ai/v1alpha2`, a `kind` of
  `read_history`, `read_preview` or `read_basket`, and every required field of design.md
  THE SYSTEM SHALL validate it against `read-command.schema.json`.
- IF it carries any of `execution_id`, `work_item_id`, `order_ref`, `workflow_id`,
  `approval_ref` or `intent_hash`, or another kind, or params that do not match its kind
  THEN THE SYSTEM SHALL reject it.
- THE SYSTEM SHALL use these per-kind params: history `{limit 1..20, cursor?}`, preview
  `{history_order_ref}` (`pho_`), basket `{}`.

Read result
- THE SYSTEM SHALL reject a read result that carries `tenant_ref`, `principal_ref`,
  `connection_ref` or `install_revision_ref`.
- IF `outcome` is `succeeded` THEN `payload` and `payload_digest` SHALL be required;
  otherwise both SHALL be forbidden.
- THE SYSTEM SHALL declare `required` on every payload, order, line and basket object, so
  that `{}` and any object missing a field are invalid.
- THE SYSTEM SHALL bound every string by pattern, with `item_name` and `store_name`
  `^[A-Za-z0-9 .,'()-]{1,60}$`, `error_detail` printable ASCII up to 128 bytes,
  `placed_on` `^[0-9]{4}-[0-9]{2}-[0-9]{2}$`, and `issued_at`, `expires_at` and `completed_at`
  an explicit RFC 3339 UTC pattern in addition to `format`.
- THE SYSTEM SHALL carry a required boolean `empty` in the preview and basket payloads;
  `approval_basket` SHALL be required iff `empty` is false and forbidden iff it is true,
  and an empty read SHALL be a valid successful read with `display: []`. (amended (c))
- THE README SHALL list the provider MUSTs of design.md: `history_order_ref` and
  `cursor` resolve only within the command's `connection_ref` and `principal_ref`, and
  an unknown or foreign value is `failed_terminal`/`provider_rejected`, never data.

Approval basket and fingerprint
- THE SYSTEM SHALL define `approval-basket.schema.json` with `v`, `store_ref`, `currency`,
  `lines` (`item_code`, `quantity`, `unit_price_minor`), `subtotal_minor`,
  `delivery_fee_minor`, `service_fee_minor`, `discount_minor` and `total_minor`, all
  required, and no display, availability or time field.
- THE SYSTEM SHALL write every schema `pattern` in the RE2/Python common subset (digits as `[0-9]`, no `\d`, no flags) and SHALL ship `vectors/pattern-parity.json`; IF a string with a trailing newline or non-ASCII digits is given for an anchored pattern THEN every consumer SHALL reject it.
- IF the lines are not sorted ascending by `item_code`, or an `item_code` repeats, or
  `subtotal_minor` or `total_minor` does not match the arithmetic of design.md THEN the
  reference validator SHALL reject the basket.
- THE SYSTEM SHALL define `basket_fingerprint` as
  `"sha256:" + hex(SHA-256(JCS(approval_basket)))`, the single M1 fingerprint, and SHALL
  ship `vectors/basket-fingerprint.json` with permuted-key, price-change and fee-change
  vectors and the must-reject cases of design.md.
- THE SYSTEM SHALL keep the read `payload_digest` a transport-integrity digest that is
  never used as an approval fingerprint.

Size
- IF a result body is larger than 16384 bytes, or `JCS(payload)` is larger than 12288
  bytes THEN the reference validator SHALL reject it with `payload_too_large`.
- THE README SHALL record the measured worst cases (history 10,673 B, basket read
  7,127 B, preview 8,273 B, approval basket 3,135 B, envelope 910 B) and state that no
  schema-valid payload reaches the 12,288-byte cap, which is defense in depth.

Raw bytes, numbers and digest
- THE SYSTEM SHALL validate results and commands from raw bytes. Before schema
  validation it SHALL reject duplicate keys at any depth, compared after JSON unescaping,
  any `\u` escape in an object key, lone surrogate escapes, `NaN`,
  `Infinity`, numbers outside ±(2^53-1), and any non-integer token (`1.0`, `1e2`, `true`)
  in an integer position.
- THE SYSTEM SHALL ship `vectors/must-reject.json` as raw text, and the README SHALL
  require every consumer, Go included, to reject every entry.
- THE SYSTEM SHALL compute `payload_digest = "sha256:" + hex(SHA-256(JCS(payload)))` with
  RFC 8785, testing `bool` before `int`. Every vector in `vectors/jcs-digest.json` SHALL
  reproduce byte for byte, cross-checked against an independent Go implementation.
- THE README SHALL require consumers to store exactly `JCS(payload)` (never JSONB) and to
  re-verify its digest on every serve.

Consumer duties
- THE README SHALL list the consumer MUSTs of design.md: bindings only from the
  consumer's own row, kind and id match, TTL, the raw-bytes pre-check, digest recompute,
  re-checks at serve time (binding, TTL, revocation, install revision, `glovo:read`),
  never persisting `lease_token`, no payload in outbox, signal, audit, log or Temporal
  history, computing the fingerprint itself, and accepting a `pho_` or cursor only if a
  prior history read for the same binding returned it.

Hygiene
- THE SYSTEM SHALL use only synthetic data in fixtures and vectors.
- WHEN the contract files change THE SYSTEM SHALL fail the tests unless `SHA256SUMS`
  matches the files.

## Out of scope

- Any mctl-api code: `ReadBridge`, the read outbox, storage, serving, re-checks of tenant,
  principal and connection binding, TTL, revocation and the `glovo:read` scope
  (mctlhq/mctl-api#986, #990).
- The provider read path in mctl-telegram (extension of mctlhq/mctl-telegram#1262).
- Any HTTP route. In particular there is no public `/read-results/{ref}` route; results
  are fetched in-process from mctlhq/mctl-api#957's handlers.
- Any Temporal workflow, signal, namespace or authorization change. Reads do not use a
  Temporal signal.
- `prepare`: it stays a write in mctl-api (mctlhq/mctl-api#957 D5) and is not a read kind.
- Changing v1alpha1, or moving `read_status` to v1alpha2.
- Any write command other than the Glovo `place_order_fake` command of
  `command-place-order-fake.schema.json` (round 6, G1; `cancel_order_fake` and `prepare`
  are not defined here).
- Real provider access of any kind.
- Changing `orchestrator/context_snapshot.canonical_json`, which is a different, non-JCS
  canonical form used by context snapshots.

## Open questions

Closed by the amendment: the `workflow_id`/#1045 question (P3-3), the ref prefixes
(P3-7), the per-kind fields (P1-3, §Crosswalk), the size cap (P1-1), and `lease_token`
(kept on the result, never persisted by a consumer).

- OPEN-1059-1 (closed, round 6 G1). This issue owns the write schema:
  `command-place-order-fake.schema.json`, whose `payload` is the approval basket by
  `$ref` (mctl-api#957 §6d.3), with two fixtures and one invalid fixture per wrong
  payload shape. mctl-api#986 §2a vendors it (round 7; #985 only enqueues it; mctl-api OPEN-985-8, OPEN-989-6 point here).
- OPEN-1059-2 (closed, round 7). mctl-api#986 §2a implements the versioned claim envelope, the declared
  versions in `BridgeProviderConfig` and the per-command wire version for the read kinds and for the
  v1alpha2 `place_order_fake`. The envelope's shape is fixed here (design §Claim response).
- OPEN-1059-3 (write half closed, round 7: mctl-telegram#1262 task 2b vendors the write command and
  claim-response schemas, parses the `claim/v1alpha2` envelope, executes the v1alpha2 `place_order_fake`
  fake-only and posts the v1alpha1 result; the read half stays open). mctl-telegram#1262 must vendor
  these files and pass `must-reject.json`
  with its Go parser; tracked on that issue. Widened (round 3): the same issue must also
  implement Provider MUST 1-3 (resolve a `pho_` or `cursor` only inside the command's
  connection; a foreign or unknown one is `failed_terminal/provider_rejected`) and carry a
  foreign-`pho_` and a foreign-cursor test against its read path. Consumer duty 10 is
  implemented and tested in mctl-api#957 (T7a), not here; this item is the provider half and
  stays open until #1262 lands it.
- OPEN-1059-4 (closed, round 8: the per-consumer table in design §Vendoring and one rule; the basket copy is mctl-api#988's; `claim-response.schema.json` is vendored by #986 and #1262; `pattern-parity.json` by #988; original recommendation follows; recommendation: replace the "exact list a consumer vendors" sentence with a per-consumer vendor table: consumer, files, location, who owns the single basket copy). The vendoring rule contradicts what #986 and #988 vendor; nobody vendors `claim-response.schema.json` (OPEN-986-4) and `pattern-parity.json` has no vendor. State the canonical basket location once (mctl-api#988 `internal/glovo/basket/contract/`), name who consumes the `claim/v1alpha2` string, and fix the matching sentences in #986 and #988.
- OPEN-1059-5 (round 6; recommendation: a normative README precheck rule list with one raw-text must-reject entry per rule). The raw-bytes pre-check lacks UTF-8 strictness, BOM, exactly one object root, no trailing bytes, no raw control characters in strings, a depth cap and `-0` handling, and `integer positions` is not defined (recommendation: schema-path based). Add the rules and entries to T6 and task 4.
