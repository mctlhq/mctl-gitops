# Design: issue-1059-feat-bridge-v1alpha2-contract-for-typed

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
  no `workflow_id` field, even though the issue says it does (see Open questions).
- **Fixtures and tests.** `docs/spikes/1043/fixtures/*.json` contains 2 valid and
  6 invalid fixtures. `tests/test_spike_1043_contracts.py` validates them with
  `jsonschema.Draft202012Validator` and the format checker, through a `CASES` table of
  (fixture, schema, valid, expected error path substring). It also asserts
  `jsonschema==4.26.0` is locked in `uv.lock` and declared in `pyproject.toml`'s dev group,
  and rejects credential-shaped strings (JWT, `Bearer `, `MCTL_TOKEN=`) in fixtures.
- **Memo.** `docs/spikes/1043-cross-namespace-dispatch.md` (STATUS `API_BRIDGE_SELECTED`)
  defines the bridge flow: mctl-api outbox, provider claim/result with leases, and an
  `aar_` consume for mutations. It also says the schemas are "proposals consumed by no
  service". Since then, mctlhq/mctl-api#968 vendors them (per the issue).
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
- The vendored copy in mctlhq/mctl-api#968 and the #1045 change were not observable from
  this clone (see Open questions).

## Proposed solution

Add a new, additive contract directory. Nothing under `docs/spikes/1043/` is touched, so
mctl-api's sha256 pin of v1alpha1 keeps matching.

```
docs/contracts/bridge/v1alpha2/
  README.md                      # scope, field tables, digest rule, vendoring/pinning rule
  read-command.schema.json       # $id https://mctl.ai/schemas/bridge/v1alpha2/read-command.schema.json
  read-result.schema.json        # $id https://mctl.ai/schemas/bridge/v1alpha2/read-result.schema.json
  fixtures/
    read-command.history.valid.json
    read-command.preview.valid.json
    read-command.basket.valid.json
    read-command.with-order-ref.json        # invalid
    read-command.with-execution-id.json     # invalid
    read-command.with-workflow-id.json      # invalid
    read-command.kind-prepare.json          # invalid
    read-command.params-wrong-kind.json     # invalid (preview params on read_history)
    read-result.history.valid.json
    read-result.preview.valid.json
    read-result.basket.valid.json
    read-result.failed.valid.json           # outcome failed_retryable, no payload
    read-result.failed-with-payload.json    # invalid
    read-result.too-many-items.json         # invalid (maxItems)
    read-result.oversize.json               # schema-valid, rejected by size cap
    read-result.digest-mismatch.json        # schema-valid, rejected by digest check
    read-result.extra-field.json            # invalid (customer_email)
  vectors/
    jcs-digest.json
  SHA256SUMS                     # sha256 of every file above, for consumer pinning
tools/jcs.py                     # stdlib-only RFC 8785 canonicalizer + digest
tools/bridge_contract.py         # reference validator + CLI (validate, digest, sums)
tests/test_bridge_v1alpha2_contract.py
```

### Why a separate `docs/contracts/` home

`docs/spikes/` holds spike evidence. The issue makes this repo the canonical schema
source, so v1alpha2 goes under a stable, non-spike path. v1alpha1 stays where it is,
because moving it would break the existing pin. The README states that v1alpha1's
canonical location remains `docs/spikes/1043/`.

### read-command.schema.json

`schema_version` const `bridge.mctl.ai/v1alpha2`, `additionalProperties: false`.

| Field | Constraint |
|---|---|
| `command_id` | `^cmd_[A-Za-z0-9]{26}$` (same as v1alpha1) |
| `request_id` | `^rdq_[A-Za-z0-9]{26}$`, the idempotency key of the read |
| `kind` | enum `read_history`, `read_preview`, `read_basket` |
| `attempt` | integer 1..100 |
| `tenant_ref` / `principal_ref` / `connection_ref` | v1alpha1 patterns (`tnr_`, `prr_`, `gcn_`) |
| `install_revision_ref` | `^irv_[A-Za-z0-9]{16,40}$` |
| `issuer` | const `mctl-api` |
| `audience` | `^provider:[a-z0-9-]{1,32}$` |
| `nonce` | `^[A-Za-z0-9_-]{22}$` |
| `issued_at`, `expires_at` | date-time, maxLength 40 |
| `ttl_seconds` | integer 1..300. Reads are short-lived, so this is tighter than v1alpha1's 900 |
| `lease_token` | optional, v1alpha1 pattern |
| `params` | object, per kind (below) |

Order and workflow fields are rejected twice. `additionalProperties: false` rejects any
unknown key. In addition, an explicit
`"not": {"anyOf": [{"required": ["execution_id"]}, {"required": ["work_item_id"]},
{"required": ["order_ref"]}, {"required": ["workflow_id"]}, {"required":
["approval_ref"]}, {"required": ["intent_hash"]}]}` gives a deterministic, named failure
that consumer tests can assert on.

Per-kind params use `allOf` of `if: {properties: {kind: {const: K}}}` /
`then: {properties: {params: {$ref: "#/$defs/params_K"}}}`, with every `params_K` set to
`additionalProperties: false`:
- `params_read_history`: `limit` integer 1..50 (required), `before` date-time (optional).
- `params_read_preview`: `item_codes` array 1..20 of `^FAKE-[A-Z0-9-]{1,32}$` (required),
  `quantity_total` integer 1..100 (required).
- `params_read_basket`: `basket_ref` `^bsk_[A-Za-z0-9]{16,40}$` (optional; absent means
  the principal's current basket).

### read-result.schema.json

`schema_version` const `bridge.mctl.ai/v1alpha2`, `additionalProperties: false`.

Required: `command_id`, `request_id`, `kind`, `tenant_ref`, `principal_ref`,
`connection_ref`, `install_revision_ref` (echoed so that mctl-api can re-check the binding
against the claimed command), `lease_token`, `attempt`, `worker_identity`, `outcome`,
`provider_effect`, `completed_at`.

- `outcome`: `succeeded | failed_retryable | failed_terminal | cancelled`.
  `approval_refused` is absent because reads need no `aar_`.
- `provider_effect`: const `none`. A read never has a provider effect, and the schema
  makes that a contract guarantee.
- `error_code`: `none | stale_lease | expired | provider_unavailable | provider_rejected |
  payload_too_large | internal`. `error_detail` maxLength 256.
- `payload` and `payload_digest` (`^sha256:[0-9a-f]{64}$`): both are required when
  `outcome` is `succeeded`, and both are forbidden otherwise (`if/then/else` with
  `not: {anyOf: [required payload, required payload_digest]}`).
- Per-kind payloads (`$defs`, all `additionalProperties: false`). Money is integer minor
  units and there are no floats in payloads, which avoids cross-language float formatting
  differences in practice even though JCS defines them:
  - `payload_read_history`: `orders` array maxItems 50 of {`order_ref` `ordr_`,
    `placed_at` date-time, `status` enum `delivered|cancelled|in_progress`, `item_count`
    0..100, `total_minor` 0..10000000, `currency` `^[A-Z]{3}$`}, plus `truncated` boolean.
  - `payload_read_preview`: `lines` array maxItems 20 of {`item_code` FAKE pattern,
    `item_name` maxLength 80, `quantity` 1..100, `unit_price_minor` 0..1000000,
    `available` boolean}, plus `subtotal_minor`, `delivery_fee_minor` and `currency`.
  - `payload_read_basket`: `basket_ref`, `lines` (same line shape, maxItems 50),
    `subtotal_minor`, `currency`, `updated_at`.
- Synthetic-data limits: free-text fields (`item_name`, `error_detail`) are bounded, and
  there are no fields for addresses, names of people, emails or phone numbers. Fixtures
  use `FAKE-` item codes and `Synthetic ...` names.

### Size cap

JSON Schema cannot bound serialized size. Field bounds cap the payload at roughly
50 lines x ~200 bytes. On top of that, the contract states a normative cap: the
JCS-canonical bytes of `payload` are at most **65536** bytes. The cap is enforced by
`tools/bridge_contract.py check_read_result` and documented in the README as a MUST for
consumers (mctl-api rejects with `payload_too_large`).

### Digest

`payload_digest = "sha256:" + hex(sha256(JCS(payload)))`. Only `payload` is digested, not
the envelope, because consumers store and re-serve the payload bytes. The envelope's
lease and attempt fields legitimately change across retries.

`tools/jcs.py` is a stdlib-only RFC 8785 implementation:
- Objects: keys sorted by their UTF-16 code-unit sequence
  (`key.encode("utf-16-be")`). Duplicate keys are rejected at parse time
  (`json.loads(..., object_pairs_hook=...)`).
- Strings: RFC 8785 section 3.2.2.2 escaping. Only `"`, `\`, and control characters
  U+0000..U+001F are escaped, using `\b \t \n \f \r` and otherwise `\u00xx` lowercase.
  All other characters are emitted raw in UTF-8. Lone surrogates are rejected.
- Numbers: integers in the IEEE-754 safe range are serialized as-is. Floats use
  ECMAScript `Number.prototype.toString` serialization, derived from Python's shortest
  round-trip `repr`, re-formatted to ES rules: exponent form only when the decimal
  exponent is >= 21 or <= -7, exponent written without leading zeros and with an explicit
  sign (`1e-7`, `1e+21`), `-0` becomes `0`. NaN and Infinity are
  rejected. Integers outside +/-2^53 are rejected, matching I-JSON.
- `canonicalize(value) -> bytes`, `canonicalize_text(json_text) -> bytes`,
  `digest(value) -> str`.

`vectors/jcs-digest.json` is an array of `{name, input, canonical, digest}`. `input` is
the raw JSON **text**, so number spellings like `1.0E2` and escape spellings survive
untouched. `canonical` is the exact expected output string. Cases:
- key reordering: `{"b":1,"a":2}` and the same with nested objects.
- unicode: raw `é`, a non-BMP emoji (U+1F600), the escaped input spelling `\u00e9`, and keys U+1F600 vs
  U+FB01. The emoji's UTF-16 sort order differs from its code-point order, so this
  case catches a code-point sort.
- control-character escaping: `\u001f`, `\n`, `\u007f` (not escaped).
- numbers: `0`, `-0`, `1.0`, `1e21`, `1e20`, `1e-7`, `0.000001`, `123.456`,
  `-1.5e-10`, `9007199254740991`, and the RFC 8785 Appendix B sample values.
- nested arrays: `[[1,[2,[3]]],{"z":[{"b":1,"a":0}]}]`, the empty array and the empty
  object.
- the RFC 8785 section 3.2.4 example object.

The expected outputs are taken from RFC 8785 where it specifies them. The rest are
generated once and cross-checked against an independent implementation (the Go
`github.com/gowebpki/jcs` or the `cyberphone/json-canonicalization` reference). The
cross-check is recorded in the README, and the vector file is pinned in `SHA256SUMS`.
Go consumers run the same file in their own CI, which the issue requires for mctl-api and
mctl-telegram.

### Vendoring

The README specifies one-way vendoring. Consumers copy `docs/contracts/bridge/v1alpha2/`
verbatim and pin each file by the sha256 in `SHA256SUMS`. They never edit the vendored
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
  - *Contract does not fit #986 or the provider slice.* Mitigated by the required
    independent review and digest-bound owner approval before those slices start. Any
    additive field goes through a new reviewed revision here.
  - *Ref prefix collision with existing mctl-api ids* (`irv_`, `rdq_`, `bsk_`). Listed as
    an open question for the mctl-api reviewer.
  - *A second canonical-JSON rule in the repo* (the ADR 009 "disagreeing hash convention"
    risk noted in `context_snapshot.hash_bytes`). Mitigated by scoping: `tools/jcs.py`
    is documented as bridge-contract-only, and context snapshots keep their rule.

## Open questions

- v1alpha1 location and `workflow_id`: the issue cites #1045 and a `workflow_id`
  requirement, but this clone has v1alpha1 at `docs/spikes/1043/` with no `workflow_id`.
  The proposal targets the files visible here.
- Ref prefixes `irv_`, `rdq_`, `bsk_` are proposals to be confirmed by mctl-api.
- The 65536-byte cap and the per-kind field sets are proposals. The issue gives no
  numbers or fields.
- The mctl-api deployed config could not be observed in the gitops checkout (no
  `services/*/mctl-api`). This is not needed for a data-only contract, but it is recorded
  as a gap.
