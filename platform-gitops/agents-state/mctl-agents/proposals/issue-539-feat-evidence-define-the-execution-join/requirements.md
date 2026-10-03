# Execution-join contract for `we_` and `ex-` in the evidence envelope (ADR 018 amendment)

## Context

The Tier A evidence contract (mctlhq/mctl-agents#520, ADR 018,
`orchestrator/execution_evidence.py`, `evidence.mctl.ai/v1alpha1`) joins an
envelope to exactly one execution through `ExecutionJoin.execution_id`, and
`_check_execution_join` (`orchestrator/execution_evidence.py:869-874`) accepts
only the canonical work execution prefix `we_` (`EXECUTION_ID_PREFIX`,
mirroring `orchestrator/work_context/snapshots.py:39`). In practice only
issue-investigator runs ever hold a `we_`. Every governed *mutation* in this
repository is identified by the ADR 011 runtime `ExecutionContext` id `ex-`
instead: `policy_checkpoint.current_identity()` returns
`ExecutionIdentity(execution_id=ctx.context_id, ...)`
(`orchestrator/policy_checkpoint.py:641`), every `ActionRequest` and therefore
every `Decision` is stamped with that `ex-` value
(`policy_checkpoint.py:678-682`), and `action_approvals.ActionIntent.execution_id`
— the first field of the `intent_hash` mctl-api binds an `aar_` approval to
(`orchestrator/action_approvals.py:98-111`, `:416-419`) — is that same `ex-`
value. `orchestrator/usage_ledger.py:59-66` already documents the resulting
ambiguity in prose: its `execution_id` field "is the work-context store's
`we_…` when the run has a store execution (today only the investigator) …
Otherwise it is the runner's ExecutionContext `context_id` (`ex-…`, ADR 011)"
— one untagged field carrying two identifier shapes, mirrored by mctl-api's
`model_usage_records.execution_id`.

The consequence is that the contract cannot express evidence for the
executions #199 most needs to cover: implementer runs, shepherd runs including
the gated merge from #519/#524, `POLICY_DECISION` records, and `aar_`
approvals. This proposal decides and encodes the join in mctl-agents and
amends ADR 018, so that mctlhq/mctl-api#409 (Tier B storage and retrieval) can
build against a settled shape instead of inventing one inside the storage
layer. The chosen model is the issue's **model (B)**: two distinct, typed
fields on `ExecutionJoin` — `execution_id` (`we_` only) and a new
`runtime_execution_id` (`ex-` only) — with a derived, typed primary retrieval
reference and no overloading in either direction.

## User stories

- AS the Tier B implementer of mctl-api#409 I WANT one settled, typed
  execution-join shape with a named primary retrieval identity SO THAT I can
  design storage keys and a retrieval route without deciding the identity
  contract inside the storage layer.
- AS a platform governance reviewer I WANT evidence envelopes to exist for
  implementer and shepherd runs, which carry only an `ex-` runtime identity,
  SO THAT the runs that perform governed mutations are covered by #199 rather
  than silently excluded.
- AS an auditor reconstructing a governed merge I WANT deterministic linkage
  from a `POLICY_DECISION` and an `aar_` approval back to the envelope SO THAT
  I can prove which policy decision and which human approval applied to which
  mutation.
- AS a maintainer of `orchestrator/execution_evidence.py` I WANT a validator
  that rejects an `ex-` in a `we_` field and a `we_` in an `ex-` field SO THAT
  the two identifier namespaces can never silently merge the way
  `usage_ledger.execution_id` already has.
- AS the owner of already-sealed `v1alpha1` envelopes I WANT the amendment to
  be hash-neutral SO THAT existing fixtures keep their `content_hash` and
  `ev-` id and Tier B does not have to support two document shapes.

## Acceptance criteria (EARS)

### Schema

- WHEN `ExecutionJoin.from_dict` parses a mapping THE SYSTEM SHALL accept
  exactly the keys `execution_id`, `work_item_id`, `trace_id` and
  `runtime_execution_id`, and SHALL raise `ExecutionEvidenceError` naming any
  other key, via the existing `_reject_unknown_keys` call.
- WHILE `ExecutionJoin.runtime_execution_id` is blank THE SYSTEM SHALL treat
  the envelope as carrying no runtime identity, never as carrying an empty
  one.
- WHEN `ExecutionEvidence.to_dict()` serializes an envelope whose
  `runtime_execution_id` is blank THE SYSTEM SHALL omit the
  `runtime_execution_id` key from the `execution` block entirely.

### Typed identity, no overloading

- IF `execution.execution_id` is non-blank and does not start with
  `EXECUTION_ID_PREFIX` (`we_`) THEN THE SYSTEM SHALL raise
  `ExecutionEvidenceError`.
- IF `execution.execution_id` is non-blank and starts with
  `RUNTIME_EXECUTION_ID_PREFIX` (`ex-`) THEN THE SYSTEM SHALL raise
  `ExecutionEvidenceError` with a message naming the correct field.
- IF `execution.runtime_execution_id` is non-blank and does not match
  `^ex-[0-9a-f]{16}$` — the exact shape `execution_identity.seal()` derives at
  `orchestrator/execution_identity.py:651` — THEN THE SYSTEM SHALL raise
  `ExecutionEvidenceError`.
- IF `execution.runtime_execution_id` is non-blank and starts with
  `EXECUTION_ID_PREFIX` (`we_`) THEN THE SYSTEM SHALL raise
  `ExecutionEvidenceError` with a message naming the correct field.
- WHILE both identities are present THE SYSTEM SHALL keep them in their own
  fields and SHALL NOT copy, merge, derive or reconcile one from the other.

### Primary retrieval identity

- WHEN a caller asks an `ExecutionJoin` for its primary execution reference
  THE SYSTEM SHALL return a typed pair `(kind, id)` where `kind` is a member
  of the closed set `EXECUTION_REF_KINDS` (`work`, `runtime`).
- WHILE `execution_id` is non-blank THE SYSTEM SHALL return
  `("work", execution_id)` regardless of whether `runtime_execution_id` is
  also set.
- WHILE `execution_id` is blank and `runtime_execution_id` is non-blank THE
  SYSTEM SHALL return `("runtime", runtime_execution_id)`.
- WHILE both fields are blank THE SYSTEM SHALL return `("", "")` and the
  `execution` block SHALL be treated as absent by `seal()`'s required-block
  check.
- WHILE an envelope is sealed THE SYSTEM SHALL keep its primary execution
  reference constant, because the reference is a derived property of two
  hashed fields and the envelope is immutable and content-addressed.

### Completeness for a runtime-only run

- WHEN `seal()` evaluates the required `execution` block THE SYSTEM SHALL
  treat the block as present if at least one of `execution_id` and
  `runtime_execution_id` is non-blank.
- IF both `execution_id` and `runtime_execution_id` are blank and no `Gap`
  with `block="execution"` and `required=True` is supplied THEN THE SYSTEM
  SHALL raise `ExecutionEvidenceError`.
- WHEN `seal()` is called for an implementer or shepherd run that carries only
  an `ex-` identity, with an outcome and at least one policy decision, THE
  SYSTEM SHALL produce a `COMPLETE` envelope without any gap.

### Hash stability and versioning

- WHILE `runtime_execution_id` is blank THE SYSTEM SHALL compute
  `content_hash` over an `execution` block byte-identical to the one it
  computed before this amendment, so that every already-sealed `we_`-only
  envelope keeps its `content_hash` and its `ev-` id.
- WHEN `seal()` hashes an envelope THE SYSTEM SHALL omit a blank
  `runtime_execution_id` from the hashed payload, including the case where
  `_safe()` reduced a dropped leaf to the `_REDACTED_LEAF` empty string.
- WHEN `recompute_content_hash()` rebuilds the payload of any sealed envelope
  THE SYSTEM SHALL reproduce that envelope's `content_hash` exactly.
- WHILE this amendment is in force THE SYSTEM SHALL keep `api_version` at
  `evidence.mctl.ai/v1alpha1` and SHALL NOT add a second entry to
  `SUPPORTED_API_VERSIONS`.

### Documentation and conformance vectors

- WHEN ADR 018 is read THE SYSTEM SHALL present exactly one join model, the
  exact `ExecutionJoin` field table including `runtime_execution_id`, the
  named primary retrieval identity, and the recorded justification for staying
  within `v1alpha1` as an additive optional field.
- WHEN the test suite runs THE SYSTEM SHALL verify three committed golden
  vectors under `tests/fixtures/evidence/` — a `we_`-joined envelope, an
  `ex-`-only envelope and a both-identities envelope — each asserting its
  literal `content_hash`, its literal `ev-` id, `to_dict()` round-trip
  equality and `recompute_content_hash()` agreement.
- IF the cross-prefix rejection in `_check_execution_join` is removed THEN the
  test suite SHALL fail.

## Out of scope

- Any persistence, API route, storage schema, index or retrieval endpoint —
  that is mctl-api#409 (Tier B). This proposal writes no file and opens no
  socket, preserving ADR 018 sec. 5's boundary row.
- The evidence producer: sealing an envelope at the end of a governed workflow
  and POSTing it. That is a later #199 child. The module stays inert and
  additive — nothing in `run_issue_investigator.py`, `run_implementer.py`,
  `run_shepherd.py` or `orchestrator/temporal/workflows/dev_loop.py` imports
  it after this change.
- Minting or attaching a `we_` for implementer and shepherd runs. Model (B) is
  chosen precisely so that no new execution authority is introduced; if the
  work-item layer later attaches a `we_` to those runs it is a purely additive
  change to the *producer*, not to this contract.
- Changing approval semantics (`orchestrator/action_approvals.py`), policy
  checkpoint semantics (`orchestrator/policy_checkpoint.py`) or the ADR 011
  identity contract itself, beyond reading them.
- De-overloading `usage_ledger.py`'s `execution_id` field or mctl-api's
  `model_usage_records.execution_id` column. Recorded as a named follow-up.
- Any GitOps or public-repository evidence persistence. The #483 direction
  stays rejected.
- Adding a `we_`/`ex-` field to `UsageRef`, `SnapshotRef`, `ApprovalRef`,
  `PolicyDecisionRef` or `ExecutionRequestRef`. Linkage is expressed through
  the one `ExecutionJoin` block, not repeated per reference block.

## Open questions

1. **Should `to_log_dict()` expose the primary reference?** This proposal adds
   `primary_execution_kind` (a two-value closed slug) and deliberately not the
   id, to keep ADR 018's "counts and codes, never lists" trace surface. A
   reviewer may prefer adding neither, or adding both `kind` and `id` for
   correlation with #195 traces. Proceeding with kind-only.
2. **Is a `we_`-carrying envelope that also carries an `ex-` required to
   prove the two refer to the same run?** No proof is possible inside a
   payload-free contract: the linkage lives in the work-item layer, not in the
   envelope. The amendment therefore states that the producer is responsible
   for supplying a consistent pair and that the contract validates shape only.
   Proceeding with shape-only validation.
3. **`trace_id` shape.** `ExecutionJoin.trace_id` is unvalidated today, and the
   existing fixture uses a Temporal workflow id
   (`dev-loop-mctlhq-mctl-agents-264`) where ADR 011 specifies 32 lowercase hex
   for `ExecutionContext.trace_id`. This amendment does not tighten it,
   because doing so would invalidate the existing golden fixture. Recorded as a
   separate follow-up.
4. **Whether `ex-` should be exported as a named constant from
   `orchestrator/execution_identity.py`.** It is a bare literal at
   `execution_identity.py:651` and `:812` today, which makes a prefix-drift
   test (the T11 pattern) impossible. This proposal extracts
   `CONTEXT_ID_PREFIX = "ex-"` there and uses it at both sites — a pure,
   behaviour-preserving rename. A reviewer who wants zero edits outside the
   evidence module can drop that task and accept a literal-only drift test.
5. **Amendment style.** ADR 018 is still `Status: proposed`, and the
   `docs/adr/` directory already has three files numbered `011-*`, so minting a
   new number is unattractive. This proposal amends ADR 018 in place with an
   explicit amendment header and a new numbered section. Proceeding that way.
