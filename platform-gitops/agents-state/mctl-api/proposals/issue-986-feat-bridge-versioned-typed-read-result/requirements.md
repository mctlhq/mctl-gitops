# Bridge v1alpha2 typed read results: mctl-api store/serve slice

## Context

Glovo M1 needs typed, bounded read results (order history, preview, basket) to travel
from the provider adapter to mctl-api without raw user data entering Temporal history,
signals or logs. The merged #957 contract makes `ReadBridge` an in-process interface
whose transport is this slice.

Amended 2026-11-09 (b) per owner decision B: the canonical v1alpha2 read contract
(schemas, fixtures, RFC 8785 digest vectors) is **mctlhq/mctl-agents#1059**, which lands
first. This issue is the mctl-api store/serve slice only. design.md has the finding ->
fix table.

Fake provider only. Nothing is enabled by this slice: #957 wires the client behind its
own closed gate, and hold mctl-gitops#2457 stays ON.

## User stories

- AS the #957 Glovo handlers I WANT an in-process `Read(history|preview|basket)` call
  that returns verified, typed bytes SO THAT the facade gets data without a public route,
  a Temporal signal or a second authorization model.
- AS a provider adapter I WANT to submit a v1alpha2 read result on the existing bridge
  result route SO THAT reads reuse the bridge's lease, binding and idempotency machinery.
- AS a tenant owner I WANT a read result to be served only to my own principal, while my
  connection is live and within a short TTL SO THAT a revoked connection or another
  principal can never see my data.
- AS a platform operator I WANT v1alpha1 untouched and every schema change idempotent SO
  THAT existing commands keep working and a restart never fails or locks a table.

## Acceptance criteria (EARS)

Contract
- THE SYSTEM SHALL vendor the mctl-agents#1059 v1alpha2 schemas, fixtures and digest
  vectors byte for byte, pinned by sha256 in a `PROVENANCE` file, and SHALL NOT author or
  modify them.
- IF #1059 is not merged THEN the implementation task SHALL NOT start.
- THE SYSTEM SHALL keep v1alpha1 schemas, kinds, projections and digests unchanged.
- THE SYSTEM SHALL support exactly the read kinds `read_history`, `read_preview` and
  `read_basket`. It SHALL NOT add a read kind for prepare; prepare is the #957 write.

Starting and waiting for a read
- WHEN #957 calls `ReadClient.Read` THE SYSTEM SHALL enqueue one read-kind command in
  process, carrying the #1059 read binding set and a server-minted `request_id`, and
  SHALL wait for its result on the store with a bounded deadline.
- THE SYSTEM SHALL write no `bridge_signal_outbox` row, no `workflow_id`, and no
  `order_ref`, `execution_id` or `work_item_id` for a read-kind command.
- IF the deadline passes THEN THE SYSTEM SHALL cancel the command and return
  `ErrReadUnavailable`.
- THE SYSTEM SHALL add no HTTP route, no MCP tool, no `glovoAudienceRoutes` entry and no
  Temporal workflow or signal.

Submission
- WHEN a provider submits a result whose `schema_version` differs from the command's
  stored `wire_version` THE SYSTEM SHALL refuse with `binding_mismatch`.
- WHEN a read result succeeds THE SYSTEM SHALL validate the payload against the #1059
  per-kind schema, canonicalize it with RFC 8785, enforce the #1059 size cap (12288 canonical bytes
  inside a body of at most 16384), verify `payload_digest`, take every binding from the
  stored command row, and store the canonical bytes with a
  server-minted `res_` in the same transaction as the result CAS.
- WHEN a result body arrives THE SYSTEM SHALL run the #1059 raw-bytes pre-check before
  parsing, and SHALL reject every entry of the vendored `must-reject.json`.
- IF a read result carries `tenant_ref`, `principal_ref`, `connection_ref` or
  `install_revision_ref` THEN THE SYSTEM SHALL refuse it as `invalid_document`.
- THE SYSTEM SHALL never persist the result's `lease_token`.
- THE SYSTEM SHALL lease a read-kind command only to a provider whose server-side config
  declares `bridge.mctl.ai/v1alpha2`, and SHALL version the claim response.
- IF a read-kind result carries a provider effect other than `none`, or a non-read kind
  carries a read payload THEN THE SYSTEM SHALL refuse with `invalid_document` (the
  vendored schema fails first; amended (c)).
- IF a read result's `request_id` differs from the stored one THEN THE SYSTEM SHALL
  refuse with `binding_mismatch`.
- THE SYSTEM SHALL store `''` in `workflow_id`, `run_id`, `execution_id`,
  `work_item_id` and `order_ref` of a read command, relax no NOT NULL, and SHALL write
  no `bridge_signal_outbox` row when a read command completes or expires. (amended (c))
- WHEN the same result is replayed THE SYSTEM SHALL return the same `res_`; a different
  digest SHALL be `result_conflict`.

Fetch (in process only)
- WHEN `FetchReadResult` is called THE SYSTEM SHALL return the bytes only if the row's
  tenant and owner principal match, the caller holds `glovo:read`, the row is not
  expired or erased, the connection and the decimal install revision match the request (round 3: the
  stored revision is the decimal #959 one; the `irv_` is wire-only), and the #959 live
  connection read reports the connection active at that revision.
- IF the row is missing or belongs to another tenant or owner THEN THE SYSTEM SHALL
  return one indistinguishable not-found sentinel.
- IF `sha256(stored bytes)` differs from the stored digest THEN THE SYSTEM SHALL fail
  closed with `ErrReadUnavailable` and log an integrity failure without the bytes.
- IF the connection checker errors THEN THE SYSTEM SHALL return `ErrReadUnavailable`.
  Its default implementation SHALL deny.

Schema
- WHEN the process starts on a database that already has the v1alpha2 changes THE
  SYSTEM SHALL apply nothing, fail nothing and take no ACCESS EXCLUSIVE lock.
- THE SYSTEM SHALL keep every non-read command subject to the old non-null workflow,
  order and execution columns through a kind-conditional CHECK.

Retention and hygiene
- THE SYSTEM SHALL erase stored bytes at `expires_at` (TTL default 300 s, clamped
  1..300 s; amended (c)) and delete the row 24 h later.
- THE SYSTEM SHALL log and audit only ids, kinds, sizes and digests, never payload bytes.
- THE SYSTEM SHALL accept only the bounded synthetic shapes defined by #1059 (`FAKE-`
  item codes, no person, address, email or phone fields).

## Out of scope

- Authoring the v1alpha2 contract (mctl-agents#1059).
- The #957 handlers, `glovo:read` issuance, the Glovo wire code mapping, and the
  `ReadBridge` adapter (#957 A12).
- The provider side in mctl-telegram (#1262 extension, OPEN-986-2).
- Basket fingerprint computation (#957/#988, over the #1059 approval basket).
- Any real Glovo access.

## Open questions

- OPEN-986-1. Read kind names, ref prefixes (`rdq_`, `irv_`, `pho_`, `pst_`) and the cap
  (12288 / 16384 bytes) are set by the #1059 amendment in this PR; this slice follows
  whatever #1059 merges.
- OPEN-986-2. The mctl-telegram provider must vendor the same #1059 files. That is an
  extension of mctl-telegram#1262, not tracked here.
- OPEN-986-3. Closed 2026-11-09 (c): `irv_` is the `install_revision` kind of #988
  `glovo.join_refs`, minted by #957 read routes (#957 design §2a). Round 3: wire-only; the
  decimal revision is what is stored and compared (#957 design §5).
