# Tasks: issue-975-feat-review-vendor-canonical-execution-p

- [ ] 1. Vendor `internal/executionprovenance/testdata/execution_attempt_vectors.json` from mctl-api
  at the PR #915 merge commit into
  `tests/fixtures/execution_provenance/execution_attempt_vectors.json` with `gh api ... -H "Accept:
  application/vnd.github.raw"`, never through an editor or a JSON re-serialiser. — DoD: `sha256sum`
  of the file prints `9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c`, and the
  merge commit SHA used is recorded for task 3.
- [ ] 2. Add `.gitattributes` with `tests/fixtures/execution_provenance/*.json -text` (depends on 1).
  — DoD: git performs no line-ending conversion on the vendored file, and the digest is unchanged
  after checkout.
- [ ] 3. Add the pure module `orchestrator/execution_provenance.py`: `CONTRACT_VERSION`,
  `ATTEMPT_ID_RE`, `LINEAGE_ROOT_RE`, `engine_run`, `attempt_canonical`, `lineage_canonical`,
  `attempt_id`, `lineage_root`, using `json.dumps(..., separators=(",", ":"), ensure_ascii=True)`
  per mctl-api `docs/execution-provenance.md`. Only stdlib imports. — DoD: ruff and mypy pass, and
  the module docstring cites mctl-api#896 / `docs/execution-provenance.md`.
- [ ] 4. Add `tests/test_execution_provenance_vectors.py` (depends on 1, 3). It contains the
  `PINNED = (contract_version, sha256)` tuple, the `HYPHENATED_WE` regex, and
  `verify_vendored(raw, pinned=PINNED)` with checks in order: digest, contract_version, schema
  non-empty and string fields, per-vector recomputation of the canonical strings and ids,
  hyphenated root present. The docstring records upstream repo, path, merge commit and the
  re-vendor procedure. — DoD: `uv run --locked pytest -q tests/test_execution_provenance_vectors.py`
  passes, and every test in "Tests" below exists.
- [ ] 5. Mutation-proof check by hand (depends on 4): temporarily delete the digest comparison from
  `verify_vendored` and confirm that `test_one_byte_change_with_valid_ids_is_refused` fails, then
  restore it. Separately, change one byte of the vendored file and confirm that the suite fails.
  — DoD: both observations are recorded in the PR description.
- [ ] 6. Cross-link (depends on 4): mention the vendored file and the pinned digest in ADR 025's
  references, or in a short note under `docs/` next to the review-receipt docs. — DoD: a reader of
  ADR 025 can find where `attempt_id` / `lineage_root` are proven to match mctl-api.

## Tests

- [ ] T1. `test_vendored_file_is_canonical`: the real vendored bytes pass `verify_vendored`.
- [ ] T2. `test_every_vector_recomputes[<name>]` (parametrised): for each of the 9 vectors,
  recomputed `attempt_canonical`, `attempt_id`, `lineage_canonical` and `lineage_root` equal the
  recorded values, and the ids match `at_[0-9a-f]{32}` / `ln_[0-9a-f]{32}`.
- [ ] T3. `test_hyphenated_we_root_present`: at least one `root_execution_id` matches
  `we_<8>-<4>-<4>-<4>-<12>` hex. The current file has `we_123e4567-e89b-12d3-a456-426614174000`.
- [ ] T4. `test_one_byte_change_with_valid_ids_is_refused`: a whitespace-only mutation of the
  vendored bytes (every id still valid) is refused with the digest message. This test fails if the
  digest comparison is removed.
- [ ] T5. `test_wrong_derived_id_is_refused`: one flipped hex char in an `attempt_id`, re-pinned to
  the mutated digest, is refused by the recomputation check and the message names the vector.
- [ ] T6. `test_contract_version_bump_is_refused`: `contract_version` rewritten to
  `execution_attempt_v2` with a re-pinned digest is refused with the re-vendor message.
- [ ] T7. `test_empty_vectors_is_refused` and `test_missing_hyphenated_root_is_refused`.
- [ ] T8. `test_module_is_pure`: an `ast` scan of `orchestrator/execution_provenance.py` allows only
  `__future__`, `hashlib`, `json` and `re` imports.
- [ ] T9. Full suite `uv run --locked pytest -q`, `ruff check` and `mypy` stay green.

## Rollback

All changes are additive and imported by no runtime path. To roll back, revert the PR, which
removes the fixture, `orchestrator/execution_provenance.py`, the test file and the `.gitattributes`
line. No data, deployment or gitops state needs to be undone. If only the pin is wrong (for
example after an upstream re-vendor), re-vendor the file and update `PINNED` in one commit. Never
edit the vendored JSON by hand.
