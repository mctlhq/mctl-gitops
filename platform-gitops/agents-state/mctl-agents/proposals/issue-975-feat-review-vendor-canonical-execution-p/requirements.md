# Vendor canonical execution-provenance vectors with byte and digest parity test

## Context

mctl-api#896 (implemented by mctl-api PR #915, merged 2026-11-02T09:12:14Z) defines the
`execution_attempt_v1` contract: the canonical `attempt_id` (`at_` + 32 hex) and `lineage_root`
(`ln_` + 32 hex) of a work-item execution (`we_...`). The server derives and records them so the
independent-review gate (ADR 025, `docs/adr/025-independent-review-receipts.md`) never takes them
on a caller's word. The single canonical vector file is mctl-api
`internal/executionprovenance/testdata/execution_attempt_vectors.json`. mctl-api
`docs/execution-provenance.md` states that mctl-agents vendors the exact bytes and pins the SHA-256
`9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c`, and that changing the file is a
`contract_version` change.

This issue (task 12 of the approved mctl-api#896 proposal, part of mctlhq/.github#281) vendors
those bytes into mctl-agents. It adds a parity test that recomputes every vector in Python and pins
the digest of the whole file, so that Tier A (Python) and Tier B (Go) cannot drift apart without
a build failure. It is a hard prerequisite of autonomous worker ingest (mctl-api#917) and of
autonomous live acceptance (mctl-agents#905). The precondition the issue named ("do not implement
before mctl-api#896 is merged and the digest is published") is now met. The digest of the file on
mctl-api `main` was recomputed during this investigation and equals the published value.

## User stories

- AS a platform maintainer I WANT mctl-agents to carry a byte-exact copy of the canonical
  execution-provenance vectors SO THAT the Python and Go derivations of `attempt_id` and
  `lineage_root` are proven to agree.
- AS a reviewer of the review gate I WANT any edit to the vendored vectors, even one that leaves
  every derived id valid, to fail CI SO THAT the vendored file cannot quietly become a fork of the
  canonical one.
- AS the owner of a future `contract_version` bump in mctl-api I WANT mctl-agents to refuse the old
  pin explicitly SO THAT a re-vendor plus a new pinned digest is a deliberate, reviewed change.

## Acceptance criteria (EARS)

- THE SYSTEM SHALL contain `tests/fixtures/execution_provenance/execution_attempt_vectors.json`
  whose bytes are identical to mctl-api `internal/executionprovenance/testdata/execution_attempt_vectors.json`
  at the merge of mctl-api PR #915.
- THE SYSTEM SHALL provide a pure Python module `orchestrator/execution_provenance.py` that exposes
  `CONTRACT_VERSION = "execution_attempt_v1"`, `engine_run(engine_ref)`, `attempt_canonical(engine, engine_ref)`,
  `lineage_canonical(root_execution_id)`, `attempt_id(engine, engine_ref)` and `lineage_root(root_execution_id)`,
  following mctl-api `docs/execution-provenance.md`.
- WHEN the parity test runs THE SYSTEM SHALL compute the SHA-256 of the raw bytes of the vendored file
  and compare it with the pinned constant
  `9ab9cf04a5542004f5e851a0f32b87681249d3e6f7027386945ebe76a46ad24c`.
- WHEN the parity test runs THE SYSTEM SHALL, for every vector, recompute `attempt_canonical`,
  `attempt_id`, `lineage_canonical` and `lineage_root` from `engine`, `engine_ref` and
  `root_execution_id`, and compare each one with the recorded value.
- IF one byte of the vendored file differs from the pinned bytes THEN THE SYSTEM SHALL fail the test,
  including when every derived id still matches (for example a whitespace-only change).
- IF a recomputed canonical string or derived id differs from its recorded value THEN THE SYSTEM
  SHALL fail the test and name the vector and the field.
- IF the vendored file's `contract_version` differs from the pinned contract version, or from
  `orchestrator.execution_provenance.CONTRACT_VERSION`, THEN THE SYSTEM SHALL fail the test with a
  message stating that a re-vendor and a new pinned digest are required.
- WHEN the digest comparison is removed from the verification routine THE SYSTEM SHALL fail its own
  mutation-proof test, because that test feeds the routine a byte-mutated copy whose derived ids are
  all still valid and requires a refusal.
- THE SYSTEM SHALL fail the test unless the vendored vectors include at least one
  `root_execution_id` of the hyphenated form `we_<8>-<4>-<4>-<4>-<12>` hex.
- IF the vendored file has no vectors, or has a vector with a missing or non-string required field,
  THEN THE SYSTEM SHALL fail the test rather than pass vacuously.
- WHILE the file is vendored THE SYSTEM SHALL NOT regenerate or rewrite it from mctl-agents code: the
  only way to change it is a re-vendor from mctl-api.

## Out of scope

- The ADR 025 `we_<hyphenated-uuid>` regex compatibility fix in Tier A
  (`orchestrator/review_receipts.py` `_EXECUTION_ID_RE`) and Tier B. The issue tracks it separately.
- Reading the server's provenance record (`GET /api/v1/executions/{execution_id}/provenance`) and
  wiring `attempt_id` / `lineage_root` into review receipts or the review gate (mctl-api#917,
  mctl-agents#905).
- Resolving `root_execution_id` by walking `resumed_from_execution_id`. The vectors take the root
  as input, and the walk is a store concern in mctl-api.
- Any automation that fetches the file from mctl-api at test time or in CI.
- Changes to mctl-api.

## Open questions

- Location of the Python derivation: this proposal puts it in a small, pure production module
  (`orchestrator/execution_provenance.py`) so that later Python callers in mctl-agents (for
  example mctl-agents#905 live acceptance) can reuse one implementation instead of a second copy.
  mctl-api#917 is Go: it does not import this module and consumes only the contract and the
  canonical vectors. If reviewers want this issue to stay test-only, the same
  functions can live in the test file. The tests are unchanged either way.
- Fixture path: `tests/fixtures/execution_provenance/` follows the per-contract directories under
  `tests/fixtures/` (`review/`, `commerce/`, `workitem/`). The issue does not prescribe a path.
- Provenance pin: the proposal records the upstream source (repository, path, merge commit of
  PR #915) in the test module docstring. The exact merge commit SHA should be filled in at
  implementation time from `gh pr view 915 -R mctlhq/mctl-api --json mergeCommit`.
