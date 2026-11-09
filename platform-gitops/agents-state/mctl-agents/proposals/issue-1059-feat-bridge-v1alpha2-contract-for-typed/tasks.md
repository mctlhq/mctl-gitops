# Tasks: issue-1059-feat-bridge-v1alpha2-contract-for-typed

Amended 2026-11-09 (b); design.md has the finding -> fix table.

- [ ] 1. Record the v1alpha1 baseline as `V1ALPHA1_SHA256`: the command and result values
  from mctl-api `internal/bridge/schema/PROVENANCE` (`b857f62b…6dae1`, `c91bb86e…9354f`)
  plus the sha256 of every fixture under `docs/spikes/1043/`. Do not modify those files.
  — DoD: the constant matches the merge base and mctl-api's PROVENANCE.
- [ ] 2. `tools/jcs.py` (stdlib only): `precheck(raw: bytes)` scans tokens and rejects
  duplicate keys at any depth, lone surrogate escapes, `NaN`/`Infinity`, numbers outside
  ±(2^53-1), and returns the integer-token positions; `canonicalize`,
  `canonicalize_text`, `digest`. Keys sorted by UTF-16 code units, RFC 8785 §3.2.2.2
  string escaping, ES number serialization, `bool` tested before `int`. — DoD: ruff clean,
  no import outside the stdlib.
- [ ] 3. `vectors/jcs-digest.json` (depends on 2): the original categories plus
  `[true,false,null]`, `{"a":true}`, and RFC 8785 §3.2.2 and §3.2.3 as two separate
  vectors. — DoD: at least 22 vectors, cross-checked with an independent Go JCS
  implementation recorded in the README.
- [ ] 4. `vectors/must-reject.json` (depends on 2): raw-text entries with a reason each —
  duplicate key top-level and nested, lone high and low surrogate, `NaN`, `Infinity`,
  `1e400`, 2^53+1, -(2^53+1), `1.0` and `1e2` and `true` in an integer position.
  — DoD: every entry fails `precheck` or the integer-token check with its reason.
- [ ] 5. `approval-basket.schema.json` and `vectors/basket-fingerprint.json` (depends on
  2): all fields required, `additionalProperties: false`; vectors for a minimal basket, a
  30-line basket, permuted input keys (same fingerprint), one unit price +1 and the
  delivery fee changed (different fingerprint); `must_reject` for unsorted lines, a
  duplicate `item_code`, a wrong subtotal, a wrong total, an extra `item_name`, and
  `quantity: 1.0`. — DoD: `bridge_contract.check_approval_basket(raw)` reproduces every
  vector.
- [ ] 6. `read-command.schema.json`: design.md fields, the forbidden-field `not/anyOf`,
  per-kind params (history `{limit, cursor?}`, preview `{history_order_ref}`, basket
  `{}`). — DoD: `check_schema` passes; every object has `additionalProperties: false`
  and a `required` list.
- [ ] 7. `read-result.schema.json` (depends on 5, 6): no binding refs; `payload` and
  `payload_digest` iff `succeeded`; per-kind payloads embedding `approval_basket` by
  `$ref`; `required` everywhere; the name and `error_detail` patterns; `placed_on`
  `format: date`. — DoD: `{}` as a payload, and each payload missing one field, is
  invalid.
- [ ] 8. `tools/bridge_contract.py` (depends on 2-7): `check_read_command(raw: bytes)`,
  `check_read_result(raw: bytes)` and `check_approval_basket(raw: bytes)`. The order is
  precheck, integer tokens, schema, body cap 16384, `JCS(payload)` cap 12288, digest
  recompute, basket sort/uniqueness/arithmetic, display codes present in the basket. CLI
  `validate|digest|fingerprint|sums`. — DoD: non-zero exit on any error.
- [ ] 9. Fixtures of design.md (depends on 8), including `at-cap` (16384 B, valid) and
  `over-cap` (16385 B), the three missing-field fixtures, `with-binding-echo` and
  `quantity-float`. Generate the maximal fixtures with a script kept in `tools/`, so that
  the README's measured sizes are reproducible.
- [ ] 10. README (depends on 3-9): scope, field tables, §Crosswalk to mctl-api#957, the
  approval basket and fingerprint, size cap with the measured table, raw-bytes and
  number rules, stored bytes, "Consumer MUST" list, versioning, vendoring by
  `SHA256SUMS`, and the statement that `prepare` and writes are out of scope
  (OPEN-1059-1). Then `SHA256SUMS`.
- [ ] 11. `tests/test_bridge_v1alpha2_contract.py` covering T1-T10. — DoD: the new file and
  `tests/test_spike_1043_contracts.py` are green, and so is the full suite.
- [ ] 12. After merge, comment on mctl-api#986, #988, #989, #990 and mctl-telegram#1262
  with the merge commit and `SHA256SUMS`. No consumer repo changes here.

## Tests

- [ ] T1. v1alpha1 unchanged: every pinned hash matches, and every v1alpha1 fixture
  behaves as in `test_spike_1043_contracts.py` `CASES`.
- [ ] T2. Fixture table: valid fixtures pass; each invalid fixture fails with its expected
  reason; `at-cap` passes and `over-cap` gives `payload_too_large`; `digest-mismatch`
  gives a digest error; `with-binding-echo` fails; `quantity-float` fails in the
  integer-token check.
- [ ] T3. Each forbidden field injected into each valid read command is rejected.
- [ ] T4. v1alpha1 and v1alpha2 do not cross-validate in either direction; a v1alpha2
  command inside a v1alpha1 claim envelope is rejected by the v1alpha1 schema.
- [ ] T5. `jcs-digest.json` reproduces byte for byte; at least one vector per category.
- [ ] T6. Every `must-reject.json` entry is rejected by `check_read_result` and by
  `check_read_command` where it applies, with the recorded reason.
- [ ] T7. `basket-fingerprint.json`: every vector reproduces; permuted input gives the
  same fingerprint; price and fee changes give different fingerprints; every
  `must_reject` case is rejected.
- [ ] T8. Required fields: `{}` and each one-field-missing payload, line and basket fail.
- [ ] T9. `SHA256SUMS` matches, and every valid result fixture's `payload_digest` equals
  `jcs.digest(payload)`.
- [ ] T10. Synthetic-data guard: no JWT, `Bearer `, `MCTL_TOKEN=`, email or phone shapes in
  any fixture or vector.

## Rollback

Revert the single PR. It only adds `docs/contracts/bridge/v1alpha2/`, `tools/jcs.py`,
`tools/bridge_contract.py` and `tests/test_bridge_v1alpha2_contract.py`. No runtime code,
image, gitops, Temporal or authorization state changes, and v1alpha1 is untouched, so the
revert has no side effects. If a consumer has already vendored v1alpha2, it keeps its
pinned copy until its own slice is reverted. v1alpha1 remains the accepted contract
throughout.
