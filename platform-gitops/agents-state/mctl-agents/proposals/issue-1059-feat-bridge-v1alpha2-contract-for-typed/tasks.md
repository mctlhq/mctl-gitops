# Tasks: issue-1059-feat-bridge-v1alpha2-contract-for-typed

- [ ] 1. Record the v1alpha1 baseline: compute the sha256 of every file under
  `docs/spikes/1043/` (both schemas and the 8 fixtures) and hard-code them in the new test
  as `V1ALPHA1_SHA256`. Do not modify any of those files. — DoD: the constant matches the
  files on the merge base, and `tests/test_spike_1043_contracts.py` is unchanged and green.
- [ ] 2. Add `tools/jcs.py`, a stdlib-only RFC 8785 canonicalizer: `canonicalize(value) ->
  bytes`, `canonicalize_text(text) -> bytes` (parses with a duplicate-key-rejecting
  `object_pairs_hook`), and `digest(value) -> "sha256:<hex>"`. It sorts keys by UTF-16
  code units, uses the RFC 8785 string escaping, uses ES number serialization, and rejects
  NaN, Infinity, lone surrogates and integers outside +/-2^53. Add a module docstring
  stating it is bridge-contract-only and that `orchestrator/context_snapshot.canonical_json`
  is a different, unchanged rule. — DoD: imports nothing outside the stdlib; ruff clean.
- [ ] 3. Add `docs/contracts/bridge/v1alpha2/vectors/jcs-digest.json` (depends on 2). It
  holds `{name, input, canonical, digest}` entries where `input` is raw JSON text,
  covering key reordering, unicode (raw, escaped-input, non-BMP, the UTF-16 vs code-point
  key-order case), control-character escaping, numbers (`0`, `-0`, `1.0`, `1e20`, `1e21`,
  `1e-7`, `0.000001`, `123.456`, `-1.5e-10`, `9007199254740991`, the RFC 8785 Appendix B
  samples) and nested arrays and objects (including empty ones), plus the RFC 8785
  section 3.2.4 example. — DoD: at least 20 vectors. The expected values are cross-checked
  against an independent JCS implementation (Go `gowebpki/jcs` or the cyberphone
  reference), and the README records the tool and version used.
- [ ] 4. Add `docs/contracts/bridge/v1alpha2/read-command.schema.json`: JSON Schema
  2020-12, `schema_version` const `bridge.mctl.ai/v1alpha2`, `kind` in
  `read_history|read_preview|read_basket`, the required read fields from design.md, an
  explicit `not/anyOf` forbidding `execution_id`, `work_item_id`, `order_ref`,
  `workflow_id`, `approval_ref` and `intent_hash`, `ttl_seconds` 1..300, and per-kind
  `params` via `allOf`/`if`/`then` with `$defs` `params_read_history|preview|basket`.
  — DoD: passes `Draft202012Validator.check_schema`; every string is bounded or
  pattern-limited; `additionalProperties: false` at every object level.
- [ ] 5. Add `docs/contracts/bridge/v1alpha2/read-result.schema.json` (depends on 4):
  required envelope fields echoing tenant, principal, connection and install revision
  refs; `provider_effect` const `none`; `outcome` without `approval_refused`; the
  `error_code` enum including `payload_too_large`; `payload` and `payload_digest`
  required if and only if `outcome` is `succeeded`; per-kind payload `$defs` with
  integer-only money fields, bounded arrays and strings, and no personal-data fields.
  — DoD: passes `check_schema`; same boundedness rules as task 4.
- [ ] 6. Add `tools/bridge_contract.py` (depends on 2, 4, 5): `check_read_command(doc)` and
  `check_read_result(doc)` return a list of error strings. Result checking runs schema
  validation, then the size cap (JCS bytes of `payload` <= 65536), then the digest check
  (`payload_digest == jcs.digest(payload)`). A CLI `python tools/bridge_contract.py
  {validate <kind> <file>|digest <file>|sums}` prints `SHA256SUMS` content. jsonschema is
  imported here only (dev dependency, already locked at 4.26.0). — DoD: the CLI exits
  non-zero on any error; no network or provider access.
- [ ] 7. Add the fixtures under `docs/contracts/bridge/v1alpha2/fixtures/` listed in
  design.md (depends on 4, 5, 6). Valid results carry `payload_digest` values computed
  with `tools/jcs.py`. `read-result.oversize.json` is schema-valid but over 65536 JCS
  bytes. `read-result.digest-mismatch.json` is schema-valid with a wrong digest. All
  values are synthetic (`FAKE-` codes, `Synthetic` names, zero-ish refs as in v1alpha1).
  — DoD: every fixture behaves as named in task T2.
- [ ] 8. Add `docs/contracts/bridge/v1alpha2/README.md` and `SHA256SUMS` (depends on 3-7).
  The README covers scope (reads only; `prepare` stays a write per mctl-api#957 D5; no
  Temporal signal; no public `/read-results/{ref}` route), field tables, the digest rule,
  the size cap as a MUST, the statement that v1alpha1 remains canonical at
  `docs/spikes/1043/` and stays accepted, and one-way vendoring pinned by `SHA256SUMS`.
  — DoD: `SHA256SUMS` equals the output of `tools/bridge_contract.py sums`.
- [ ] 9. Add `tests/test_bridge_v1alpha2_contract.py` covering T1-T7 (depends on 1-8).
  — DoD: `uv run pytest tests/test_bridge_v1alpha2_contract.py tests/test_spike_1043_contracts.py`
  is green, and the full suite stays green.
- [ ] 10. After merge, comment on mctlhq/mctl-api#986, mctlhq/mctl-api#990 and
  mctlhq/mctl-telegram#1262 with the merge commit and the `SHA256SUMS` content, so that the
  implementation slices vendor the approved bytes. — DoD: links posted. No consumer repo
  changes are made here.

## Tests

- [ ] T1. v1alpha1 unchanged: the sha256 of every file under `docs/spikes/1043/` equals
  `V1ALPHA1_SHA256`, and every v1alpha1 fixture validates, or fails, against the v1alpha1
  schemas exactly as in `tests/test_spike_1043_contracts.py` `CASES`.
- [ ] T2. Parametrized fixture table (the same pattern as `CASES` in
  `test_spike_1043_contracts.py`): the 3 valid read commands and 4 valid read results
  pass. `with-order-ref`, `with-execution-id`, `with-workflow-id`, `kind-prepare`,
  `params-wrong-kind`, `failed-with-payload`, `too-many-items` and `extra-field` fail,
  each with the expected path substring. `oversize` passes the schema but
  `check_read_result` reports `payload_too_large`. `digest-mismatch` passes the schema
  but `check_read_result` reports a digest mismatch.
- [ ] T3. Each of `execution_id`, `work_item_id`, `order_ref`, `workflow_id`,
  `approval_ref` and `intent_hash`, injected into each valid read command, is rejected.
- [ ] T4. A v1alpha1 command or result validated against the v1alpha2 schemas is rejected
  on `schema_version`, and the reverse is also rejected (the versions do not cross-validate).
- [ ] T5. Every vector in `vectors/jcs-digest.json` yields the exact `canonical` bytes
  and `digest` from `tools/jcs.canonicalize_text`. Coverage asserts at least one vector
  per category (key-order, unicode, numbers, nested-arrays). Negative cases: NaN,
  Infinity, a duplicate key, a lone surrogate and 2^53+1 raise.
- [ ] T6. `SHA256SUMS` matches the current file bytes, and every valid result fixture's
  `payload_digest` equals `jcs.digest(payload)`.
- [ ] T7. Synthetic-data guard: no JWT, `Bearer ` or `MCTL_TOKEN=` strings, no `@` email
  shapes, and no phone-number shapes in any v1alpha2 fixture or vector (extends
  `test_no_credential_shaped_values`).

## Rollback

Revert the single PR. It only adds `docs/contracts/bridge/v1alpha2/`, `tools/jcs.py`,
`tools/bridge_contract.py` and `tests/test_bridge_v1alpha2_contract.py`. No runtime code,
image, gitops, Temporal or authorization state changes, and v1alpha1 is untouched, so the
revert has no side effects. If a consumer has already vendored v1alpha2, it keeps its
pinned copy until its own slice is reverted. v1alpha1 remains the accepted contract
throughout.
