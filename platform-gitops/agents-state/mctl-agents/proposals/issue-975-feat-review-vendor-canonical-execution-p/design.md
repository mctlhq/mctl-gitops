# Design: issue-975-feat-review-vendor-canonical-execution-p

## Current state

- mctl-agents has no implementation of the `execution_attempt_v1` derivation. `grep` for
  `execution_attempt`, `attempt_canonical`, `lineage_canonical` and `at_`/`ln_` derivations under
  `orchestrator/` finds nothing. `attempt_id` / `lineage_root` appear only as opaque strings in
  `orchestrator/review_receipts.py` (`ReviewRequest.authoring_attempt_ids`,
  `authoring_lineage_root`, receipt fields `attempt_id` / `lineage_root`, lines ~517-675). ADR 025
  (`docs/adr/025-independent-review-receipts.md` lines 76-90) uses them for independence checks.
- Execution ids: `orchestrator/review_receipts.py:116` `_EXECUTION_ID_RE =
  (?:we_[0-9a-f]{16,64}|ex-[0-9a-f]{16})` does not accept the hyphenated `we_<uuid>` form. That is
  the separately tracked sibling fix. `orchestrator/policy_checkpoint.py:802`
  `_STORE_EXECUTION_RE = we_[A-Za-z0-9][A-Za-z0-9-]{0,127}` does accept it. This proposal does not
  touch either regex.
- Canonical JSON in this repo: `orchestrator/context_snapshot.py:129` `_canonical_json` uses
  `json.dumps(sort_keys=True, separators=(",", ":"), allow_nan=False)`. Its default
  `ensure_ascii=True` is the same rule the mctl-api contract specifies (`cj`). The contract's
  inputs are plain lists of strings, so `sort_keys` makes no difference.
- Precedents for cross-repo vectors:
  - `tests/test_review_parity_vectors.py` + `tests/fixtures/review/review_receipt_vectors.json`:
    mctl-agents is the producer (Tier A generates, `--write` regenerates, a byte-identity test
    guards drift).
  - `tests/test_commerce_dispatch_vector.py` + `tests/fixtures/commerce/dispatch_authorization_v1.json`:
    mctl-api is the producer, the file is copied in verbatim, and the docstring records the upstream
    source and version.
  - `tests/test_commerce.py` / `tests/test_action_approvals.py` pin `sha256:` digests as module
    constants.
  This issue is the second shape (mctl-api produces the file), with a whole-file digest pin added.
- CI: `.github/workflows/pr-validation.yml:230` runs `uv run --locked pytest -q`, and `pyproject.toml`
  `testpaths = ["tests"]`. A new `tests/test_*.py` file is picked up automatically. The repo has no
  `.gitattributes` and no `.pre-commit-config.yaml`, so nothing rewrites line endings or trailing
  newlines of a vendored file.

Deployed state checked:
- `gh pr view 915 -R mctlhq/mctl-api`: state MERGED, mergedAt 2026-11-02T09:12:14Z. It adds
  `docs/execution-provenance.md`, `internal/executionprovenance/provenance.go` and
  `internal/executionprovenance/testdata/execution_attempt_vectors.json`.
- `gh issue view 896 -R mctlhq/mctl-api`: CLOSED.
- `gh api repos/mctlhq/mctl-api/contents/docs/execution-provenance.md?ref=main`: publishes the
  contract (`cj`, `engine_run`, `at_`/`ln_` + first 32 hex of SHA-256) and the pinned digest
  `9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c`.
- `gh api .../internal/executionprovenance/testdata/execution_attempt_vectors.json?ref=main | sha256sum`:
  `9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c`, the published value. The
  file has `contract_version: "execution_attempt_v1"` and 9 vectors: temporal/argo/a2a plain,
  `#` suffix stripping (3 cases), non-ASCII, astral plus escapes, and "hyphenated uuid root"
  `we_123e4567-e89b-12d3-a456-426614174000`. Each vector has fields `name, engine, engine_ref,
  root_execution_id, attempt_canonical, attempt_id, lineage_canonical, lineage_root`.
- `gh api .../internal/executionprovenance/provenance.go?ref=main`: Go reference
  (`ContractVersion`, `EngineRun` splits at the first `#`, `AttemptID`, `LineageRoot`,
  `CanonicalStrings` mirrors `json.dumps(..., ensure_ascii=True)` including surrogate pairs).
- mctl MCP tools / `$MCTL_GITOPS_ROOT` service values: not consulted. This change is test-only plus
  a pure library module, and it alters no deployed service, tenant, env var or runtime behaviour.

## Proposed solution

### 1. Vendored file

`tests/fixtures/execution_provenance/execution_attempt_vectors.json` is a byte-exact copy of the
mctl-api file. Fetch it with
`gh api repos/mctlhq/mctl-api/contents/internal/executionprovenance/testdata/execution_attempt_vectors.json?ref=<merge-sha> -H "Accept: application/vnd.github.raw" > ...`,
not with an editor or a JSON re-serialiser. Before committing, verify it with `sha256sum`.

### 2. `orchestrator/execution_provenance.py` (pure, stdlib only)

```python
CONTRACT_VERSION = "execution_attempt_v1"
ATTEMPT_ID_RE = re.compile(r"at_[0-9a-f]{32}")
LINEAGE_ROOT_RE = re.compile(r"ln_[0-9a-f]{32}")

def _cj(items: list[str]) -> bytes:  # docs/execution-provenance.md `cj`
    return json.dumps(items, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")

def engine_run(engine_ref: str) -> str: return engine_ref.split("#", 1)[0]
def attempt_canonical(engine, engine_ref) -> bytes: return _cj([CONTRACT_VERSION, "attempt", engine, engine_run(engine_ref)])
def lineage_canonical(root_execution_id) -> bytes: return _cj([CONTRACT_VERSION, "lineage", root_execution_id])
def attempt_id(engine, engine_ref) -> str: return "at_" + sha256(attempt_canonical(...)).hexdigest()[:32]
def lineage_root(root_execution_id) -> str: return "ln_" + sha256(lineage_canonical(...)).hexdigest()[:32]
```

The module has no I/O, no network and no import from other `orchestrator` modules. That mirrors
mctl-api's `purity_test.go` and lets later consumers (mctl-api#917 ingest, mctl-agents#905 live
acceptance) reuse one Python derivation. Non-string inputs raise `TypeError`. The module adds no
input validation beyond that; validation of the `we_` shape belongs to the sibling regex fix.

### 3. `tests/test_execution_provenance_vectors.py`

The module docstring records the upstream repository, path, PR #915 merge commit and the rule
"never edit; re-vendor from mctl-api". Module constants:

```python
VENDORED = Path(__file__).parent / "fixtures/execution_provenance/execution_attempt_vectors.json"
PINNED = ("execution_attempt_v1", "9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c")
HYPHENATED_WE = re.compile(r"we_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
```

The contract version and digest are pinned as one tuple. A version bump cannot reuse the old digest
by accident, and changing either one is a single, visible edit.

One verification routine, `verify_vendored(raw: bytes, pinned=PINNED) -> None`, raises
`AssertionError` with a specific message. It checks, in this order:

1. `sha256(raw).hexdigest() == pinned[1]`, otherwise "vendored bytes diverge from mctl-api (got X,
   pinned Y); re-vendor, never edit".
2. Parses JSON. `contract_version` must equal `pinned[0]` and `execution_provenance.CONTRACT_VERSION`,
   otherwise "contract_version changed: re-vendor from mctl-api and pin the new digest published in
   docs/execution-provenance.md".
3. `vectors` must be a non-empty list. Every required field must be present and be a `str`.
4. Per vector: `attempt_canonical(engine, engine_ref).decode() == v["attempt_canonical"]`, the same
   for lineage, `attempt_id(...) == v["attempt_id"]`, `lineage_root(...) == v["lineage_root"]`, and
   both ids match `ATTEMPT_ID_RE` / `LINEAGE_ROOT_RE`. Failure messages name `v["name"]` and the field.
5. At least one `root_execution_id` fully matches `HYPHENATED_WE`.

Checks 2-5 run even after the digest has passed. Every check is independently necessary.

Tests:
- `test_vendored_file_is_canonical`: `verify_vendored(VENDORED.read_bytes())`.
- `test_every_vector_recomputes` (parametrised over vector names for readable failures) runs
  check 4 per vector.
- `test_hyphenated_we_root_present`.
- Mutation-proof tests. Each builds a mutated copy in memory and asserts that `verify_vendored`
  raises, with `pytest.raises(AssertionError, match=...)`:
  - `test_one_byte_change_with_valid_ids_is_refused`: append `b"\n"`, or replace the 2-space indent
    of one line with 3 spaces. JSON parsing and every derived id still pass, so only the digest
    check can refuse, and the match targets the digest message. If someone deletes the digest
    comparison from `verify_vendored`, this test fails. That is the issue's "removing the digest
    comparison makes the test fail" proof.
  - `test_wrong_derived_id_is_refused`: flip one hex char of an `attempt_id`, and pass a `pinned`
    whose digest is that of the mutated bytes. This isolates check 4 from the digest check.
  - `test_contract_version_bump_is_refused`: rewrite `contract_version` to `execution_attempt_v2`
    with the matching re-pinned digest. Check 2 must refuse it.
  - `test_empty_vectors_is_refused` / `test_missing_hyphenated_root_is_refused`: same technique.
- `test_module_is_pure`: parse `orchestrator/execution_provenance.py` with `ast` and assert that it
  imports only `hashlib`, `json`, `re` and `__future__`.

## Alternatives

1. **Generate the vectors in mctl-agents (like `review_receipt_vectors.json`, `--write` mode).**
   Dropped. Here mctl-api is the canonical producer, and regeneration on the mctl-agents side would
   turn a parity check into a self-consistency check. The issue requires the exact upstream bytes.
2. **Fetch the file from mctl-api at test or CI time.** Dropped. Tests would depend on the network
   and on GitHub credentials, and an upstream change would break mctl-agents CI without a
   reviewed re-vendor. The issue asks that a version change "requires an explicit re-vendor".
3. **Compare derived ids only, with no whole-file digest.** Dropped. The issue's first acceptance
   criterion is that a byte change with all ids still matching must fail. Only a digest of the raw
   bytes catches whitespace, key-order or added-field drift.
4. **Keep the derivation inside the test file only.** Viable and noted under Open questions. It was
   not chosen because the two downstream consumers would otherwise grow a second copy.

## Platform impact

- Migrations: none. No runtime path imports the new module yet, and no deployed service, image
  behaviour, tenant or gitops value changes.
- Backward compatibility: purely additive (one fixture, one module, one test file).
- Resources: negligible test time (a few hashes over a ~5 KB file).
- Risks and mitigations:
  - *Editor or tool normalising the vendored file* (trailing newline, CRLF, re-indent). The digest
    test fails immediately, and the docstring explains how to re-vendor. Adding a `.gitattributes`
    entry `tests/fixtures/execution_provenance/*.json -text` is a cheap guard and is part of the
    tasks.
  - *Upstream bumps `contract_version`.* The pinned version check fails with an explicit re-vendor
    instruction. mctl-agents keeps the old pin until someone re-vendors on purpose.
  - *Ruff or mypy complaints* about the new module and tests: follow the existing `pyproject.toml`
    rules (line-length 120, py312).
