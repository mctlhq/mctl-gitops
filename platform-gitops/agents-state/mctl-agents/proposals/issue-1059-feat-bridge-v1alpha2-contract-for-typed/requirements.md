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
must pass the same vectors. v1alpha1 stays byte-for-byte unchanged and remains the only
contract for writes and for `read_status`.

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

- WHEN the v1alpha2 contract lands THE SYSTEM SHALL keep every file under
  `docs/spikes/1043/` (the v1alpha1 schemas and fixtures) byte-identical, and every
  v1alpha1 fixture SHALL still validate, or fail, exactly as before.
- WHEN a read command whose `kind` is `read_history`, `read_preview` or `read_basket`
  carries `schema_version` `bridge.mctl.ai/v1alpha2` and every required read field
  (`command_id`, `kind`, `attempt`, `tenant_ref`, `principal_ref`, `connection_ref`,
  `install_revision_ref`, `request_id`, `issuer`, `audience`, `nonce`, `issued_at`,
  `expires_at`, `ttl_seconds`, `params`) THE SYSTEM SHALL validate it against
  `read-command.schema.json`.
- IF a v1alpha2 read command carries any of `execution_id`, `work_item_id`, `order_ref`,
  `workflow_id`, `approval_ref` or `intent_hash` THEN THE SYSTEM SHALL reject it.
- IF a v1alpha2 read command has `kind` `prepare`, `read_status`, `quote` or any kind
  outside the three read kinds THEN THE SYSTEM SHALL reject it.
- IF a read command's `params` do not match the per-kind params shape for its `kind`
  THEN THE SYSTEM SHALL reject it.
- WHEN a read result with `outcome` `succeeded` carries a `payload` matching the payload
  shape for its `kind` and a `payload_digest` THE SYSTEM SHALL validate it against
  `read-result.schema.json`.
- IF a read result's `outcome` is not `succeeded` THEN THE SYSTEM SHALL require that it
  carries no `payload` and no `payload_digest`.
- IF a read result payload exceeds a schema bound (array `maxItems`, string `maxLength`,
  integer range) THEN THE SYSTEM SHALL reject it through the schema.
- IF the JCS-canonical form of a read result `payload` is larger than 65536 bytes THEN THE
  SYSTEM SHALL reject it in the reference validator (`check_read_result`), even when every
  per-field bound passes.
- WHEN the digest of a payload is computed THE SYSTEM SHALL compute
  `"sha256:" + lowercase hex(SHA-256(JCS(payload)))`, where JCS is RFC 8785.
- IF a read result's `payload_digest` does not equal the digest recomputed from its
  `payload` THEN THE SYSTEM SHALL reject it in the reference validator.
- WHEN the golden digest vectors are run against the Python reference implementation THE
  SYSTEM SHALL produce, for every vector, the exact canonical bytes and digest stored in
  the vector file. The vectors SHALL cover key reordering, unicode (including non-BMP
  characters and UTF-16 code-unit key ordering), numbers (integers, negative zero,
  exponents, shortest round-trip doubles) and nested arrays and objects.
- WHILE the contract is a v1alpha2 artifact THE SYSTEM SHALL use only synthetic data in
  fixtures and vectors: no real provider identifiers, addresses, emails, phone numbers,
  tokens or credential-shaped strings.
- WHEN the contract files change THE SYSTEM SHALL fail the test suite unless
  `docs/contracts/bridge/v1alpha2/SHA256SUMS` matches the files, so that consumers can pin
  by sha256.

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
- Real provider access of any kind.
- Changing `orchestrator/context_snapshot.canonical_json`, which is a different, non-JCS
  canonical form used by context snapshots.

## Open questions

- The issue says the v1alpha1 command requires `workflow_id` and that the schemas were
  authored in #1045. In this clone, v1alpha1 lives at `docs/spikes/1043/` and its command
  schema has no `workflow_id` field. This proposal treats `docs/spikes/1043/` as the
  v1alpha1 source and still lists `workflow_id` among the forbidden read fields. If #1045
  moved or changed v1alpha1 on a branch not visible here, the "v1alpha1 unchanged" test
  must target that location instead.
- Ref prefixes for the new identifiers are not given by the issue. Proposed:
  `install_revision_ref` `^irv_[A-Za-z0-9]{16,40}$`, `request_id` `^rdq_[A-Za-z0-9]{26}$`,
  basket `basket_ref` `^bsk_[A-Za-z0-9]{16,40}$`. mctl-api's reviewer should confirm or
  replace them before approval.
- Per-kind params and payload fields are not specified by the issue beyond "typed and
  bounded". The proposed shapes (design.md) are synthetic and minimal. #986 and the
  provider slice may need more fields, which would be an additive v1alpha2 revision
  approved before landing.
- Size cap value: 65536 bytes of JCS-canonical payload is proposed. The issue sets no
  number.
- Whether read commands keep `lease_token` and `attempt` (lease-based claim, as in
  v1alpha1) or are single-shot in-process. This proposal keeps both, as optional
  `lease_token` on the command and required on the result, matching v1alpha1's lease
  model.
