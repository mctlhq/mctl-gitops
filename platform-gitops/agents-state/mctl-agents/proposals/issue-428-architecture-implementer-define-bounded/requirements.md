# Implementer-phase ImplementationCompletion handoff contract (PR 1: contract and emission)

**This DevLoop implements PR 1 only. PR 2 and PR 3 are separate follow-up work items and
must not be implemented in this attempt.**

- PR 1 (this attempt): tasks 1, 2, 3, 4 and 7, tests T1-T4 and T7. The schema module,
  `completion_from_result`, emission and `.status.yaml` projection, primary / fallback
  authority, the `RefusalMarker.remaining` extension, and ADR 021.
- PR 2 (shepherd shadow consumption, task 5, T5): tracked in
  https://github.com/mctlhq/mctl-agents/issues/679. Own DevLoop after PR 1 merges.
- PR 3 (Temporal observe-only, task 6, T6): tracked in
  https://github.com/mctlhq/mctl-agents/issues/680. Own DevLoop after PR 1 merges.
- Task 8 (mctl-gitops optional prior-state input artifact): tracked in
  https://github.com/mctlhq/mctl-gitops/issues/1947, done outside this DevLoop.

## Context

The Tier 2 implementer (`orchestrator/run_implementer.py`) ends one attempt in one of
three ways. It flips `.status.yaml` to `implemented` with a `pr:` URL. Or it writes
`needs-triage` / `blocked` / `rate_limited`, or hands the proposal back to `accepted`. Or,
in shepherd review-feedback mode, it exits with one of the sentinel codes 0, 42-54
(`EXIT_NO_FOLLOWUP_COMMITS` ... `EXIT_POLICY_UNDECIDED`) plus an optional `--refusal-out`
JSON. Temporal reads only Argo's node graph (`orchestrator/temporal/implement_outcome.py`)
and the shepherd folds exit codes into `FollowupSubprocessError.kind`. None of these is a
single, versioned statement of the form: "attempt X, step S of Argo run R, under claim Y at
epoch Z, against proposal content D, produced head H; it ran these checks with these
results; this is what remains and why it stopped." So today "a PR exists" stands in for
"implementation complete".

This proposal defines one typed, sealed, versioned **ImplementationCompletion** record per
implementer attempt step, a deterministic rule for which record is authoritative when the
CWFT's `implement` and `implement-fallback` steps both run inside one Argo workflow, and
the emission of that record by the current one-shot implementer. It describes how the
existing implement / review-remediation phase ended. It is an implementer-phase completion
contract: not a review verdict, not an approval, and not a new lifecycle owner or a nested
DevLoop.

In v1alpha1, `complete` means exactly: "the attempt pushed a head that passed the
orchestrator gates" (`commits_present`, `chart_major_guard`, `push_succeeded`,
`claim_valid_at_push`). It does NOT mean "the approved scope is implemented": no check yet
compares the result against the approved `tasks.md`. Task-coverage verification is named
follow-up F1.

This revision changes only the delivery scope (owner review of proposal 5b586922e). The
technical design accepted in that review is unchanged.

## User stories

- AS an operator I WANT the stop reason, remaining work and verification summary of an
  attempt in `.status.yaml` SO THAT I do not reconstruct intent from pod logs.
- AS an operator I WANT a failing `implement-fallback` (typically a harness failure on the
  second account) never to hide the primary step's real outcome SO THAT triage starts from
  the actual cause.
- AS a future consumer (shepherd in #679, Temporal in #680, mctl-api / FinOps) I WANT each
  completion bound to the Argo run, step, attempt, execution and claim identities and
  available as a validated JSON file SO THAT I can classify outcomes without parsing model
  text or exit-code tables.
- AS a platform owner I WANT the contract to be unable to express approval, review-clean,
  merge, release or ownership change SO THAT the implementer cannot self-certify past its
  phase.

## Acceptance criteria (EARS)

Scope
- WHILE this DevLoop attempt runs THE SYSTEM SHALL change only the PR 1 surfaces:
  `orchestrator/implementation_completion.py` (new), `orchestrator/run_implementer.py`,
  `docs/adr/021-implementation-completion-contract.md` (new) and their tests.
- THE SYSTEM SHALL NOT, in this attempt, modify `orchestrator/run_shepherd.py`,
  `orchestrator/temporal/**`, `ExecutionRecord`, or any mctl-gitops file.

Schema
- THE SYSTEM SHALL provide `orchestrator/implementation_completion.py`, defining
  `ImplementationCompletion` with `api_version: completion.mctl.ai/v1alpha1` and
  `kind: ImplementationCompletion`: a frozen dataclass with a canonical JSON form, a
  `sha256:` `content_hash`, a derived `completion_id` (`ic-` + 16 hex characters), and a
  `from_dict` that rejects unknown keys and unsupported api versions.
- THE SYSTEM SHALL restrict `outcome` to the closed set `complete`, `incomplete`,
  `bounded_refusal`, `budget_exhausted`, `deterministic_failure`, `harness_failure`.
- THE SYSTEM SHALL require these bindings on every record:
  - `subject`: service, slug, optional `work_item_id`;
  - `attempt`: `attempt_id`, `run_id` (the Argo workflow name, `WORKFLOW_NAME`), `step`
    (`primary` | `fallback`, from `IS_FALLBACK`), `phase` (`implement` |
    `review-remediation`), and the optional `execution_id` (`we_`), `context_id` (`ex-`),
    `claim_id`, `owner_epoch`;
  - `source`: repository, base ref and SHA, branch, head SHA or null;
  - `proposal`: `proposal_digest` (computed by `proposal_state.proposal_content_digest`,
    the same framing as `approval.content_digest`), plus an optional
    `review_bundle_digest`;
  - `verification` (at most 32), `remaining_work` (at most 32), `stop_reason` (closed
    code set plus optional bounded detail), `evidence_refs` (`{evidence_id, kind}` only).
- THE SYSTEM SHALL include `run_id` and `step` in the content hash, so the primary and
  fallback records of one Argo run always have different `completion_id`s, whether or not
  their `attempt_id`s coincide.
- THE SYSTEM SHALL bound each verification record to `check_id`, `result` (`pass` |
  `fail` | `unknown` | `not_run`), `classification` (closed set), `required: bool` and an
  optional `evidence_ref`, with no free-form stdout/stderr field.
- THE SYSTEM SHALL treat exactly `commits_present`, `chart_major_guard`, `push_succeeded`
  and `claim_valid_at_push` as `required` in v1alpha1. Ledger-observed agent commands SHALL
  be recorded as non-required.
- IF a record has `outcome == complete` AND any required check is not `pass`, OR
  `remaining_work` is non-empty, OR `source.head_sha` is null, THEN THE SYSTEM SHALL reject
  it with `ImplementationCompletionError`.
- IF a record has `outcome == incomplete` AND `remaining_work` is empty, THEN THE SYSTEM
  SHALL reject it.
- THE SYSTEM SHALL use the stop-reason code `gates_passed` (not `scope_done`) for
  `complete`, and the module docstring and ADR 021 SHALL state that `complete` means "the
  attempt pushed a head that passed the orchestrator gates", not "the approved scope is
  implemented".
- THE SYSTEM SHALL bound every string leaf and SHALL redact `stop_reason.detail` and
  `remaining_work[].summary` through `orchestrator/redaction.py` before sealing.
- THE SYSTEM SHALL NOT define any field that expresses approval, review verdict, merge,
  release, ownership transfer, claim extension or budget extension. `from_dict` SHALL
  reject such keys as unknown.

Emission
- WHEN `_implement_one` or `_review_feedback_one` returns or raises on any arm after the
  claim is acquired, THE SYSTEM SHALL build exactly one `ImplementationCompletion` for
  that step, mapped by one pure function, `completion_from_result`.
- WHEN the implementer writes `implemented`, `needs-triage`, `rate_limited`, or a budget /
  policy hand-back to `.status.yaml`, THE SYSTEM SHALL also write a bounded `completion:`
  projection (authoritative record summary plus an optional summary of the other step).
  The projection SHALL hold no verification details or runtime telemetry.
- WHEN `--completion-out PATH` is given, THE SYSTEM SHALL write the full sealed record as
  JSON to PATH (best effort, bounded). The exit code SHALL remain the fallback signal.
- THE SYSTEM SHALL keep every existing exit code, `--refusal-out` payload and
  `.status.yaml` status transition unchanged.
- IF the attempt exits before the claim is acquired (pre-start per #418,
  `ensure_auth_for_sdk` failure, token-2-unset shell exit) THEN THE SYSTEM SHALL emit no
  completion.
- WHEN `.implementer-refusal.json` carries the new optional bounded `remaining` list on an
  otherwise successful push, THE SYSTEM SHALL emit `outcome: incomplete`. A marker without
  `remaining` SHALL behave exactly as today.

Primary / fallback authority
- WHEN the fallback step seals a record AND the primary step's handoff from the same
  `run_id` is readable, THE SYSTEM SHALL select the authoritative record with
  `select_authoritative(primary, fallback)`:
  - IF the fallback outcome is `complete` THEN the fallback record is authoritative and
    the primary record is kept as a `superseded` summary;
  - OTHERWISE the primary record stays authoritative and the fallback record is kept as a
    `fallback` summary. A fallback record SHALL never replace a primary record unless it
    is `complete`.
- IF the fallback step never reaches the claim THEN THE SYSTEM SHALL emit nothing for it
  and the primary's handoff artifact SHALL remain the one committed.
- IF the fallback step cannot read any primary handoff (for example because the
  mctl-gitops#1947 input artifact is not yet deployed) THEN THE SYSTEM SHALL project its
  own record with `primary_observed: false`. The owner has accepted this interim state.
- THE SYSTEM SHALL pin this with tests for primary-fails then fallback-fails (primary
  authoritative) and primary-fails then fallback-succeeds (fallback authoritative), each
  with `WORKFLOW_UID` set and unset.

Replay / retry / staleness
- THE SYSTEM SHALL exclude `created_at` from the content hash, so a re-sealed identical
  record has the same `completion_id`.
- WHEN a completion is projected into a `.status.yaml` that already holds a `completion`
  with the same `(run_id, step, attempt_id)`, THE SYSTEM SHALL leave it unchanged (same
  `completion_id`) or refuse and log (different `completion_id`). It SHALL never replace a
  non-`complete` outcome with `complete` under the same `(run_id, step, attempt_id)`.
- IF the attempt's claim check (`_check_claim_or_raise`) fails at emission, or
  `_status_is_still_ours` is false, THEN THE SYSTEM SHALL NOT project the completion into
  `.status.yaml`. It MAY still emit it to `--completion-out` as `harness_failure` with
  stop reason `fenced` or `claim_refused`.
- IF a prior handoff read by the fallback carries a different `run_id`, or `step` other
  than `primary`, THEN THE SYSTEM SHALL treat it as absent.

Documentation
- THE SYSTEM SHALL add `docs/adr/021-implementation-completion-contract.md`. It SHALL state
  that this is an implementer-phase completion contract, not an independent review
  verdict, not approval and not another DevLoop; give the outcome mapping table; state the
  primary / fallback authority rule; state the v1alpha1 meaning of `complete`; record
  task-coverage verification as follow-up F1; and list the consumer integrations as
  follow-ups (#679, #680, mctl-gitops#1947).

## Out of scope

- **PR 2, shepherd shadow consumption (task 5, T5):** mctlhq/mctl-agents#679. Separate
  DevLoop after PR 1 merges. Not implemented in this attempt.
- **PR 3, Temporal observe-only (`read_proposal_completion`, `ExecutionRecord` fields,
  `implement-completion` patch; task 6, T6):** mctlhq/mctl-agents#680. Separate DevLoop
  after PR 1 merges. Not implemented in this attempt.
- **Task 8, mctl-gitops optional prior-state input artifact:** mctlhq/mctl-gitops#1947.
  Done outside this DevLoop.
- Whether the implement CWFT should set `WORKFLOW_UID` (owner: separate decision, not
  needed here).
- Any new lifecycle owner, nested DevLoop, inner agent loop, or new retry / timeout /
  admission mechanism. #395, #418, #423 and ADR-010 semantics are reused as they are.
- Task-coverage verification (comparing the pushed head with the approved `tasks.md`).
  Named follow-up F1.
- Changing how Claude, Agy or required CI gate a PR, or the shepherd's merge decision.
- Changing the CWFT's step order or the rule that the fallback's `.status.yaml` status
  transition is the one committed when it writes one.
- mctl-api storage columns or read models for the new fields.
- Durable evidence storage (ADR 018 Tier B).
- Letting the implementer agent author the record.

## Open questions

- `incomplete` is reachable only via the new optional `remaining` list in
  `.implementer-refusal.json`. The design proceeds with that extension; confirm it is the
  intended sole source of `incomplete` in v1alpha1.
- `proposal_digest` reuses `proposal_content_digest`, which the implementer already checks
  against `approval.content_digest` before starting (`approval_digest_problem`, #658). So
  the record binds to approved content in practice. Whether the record should also carry
  the recorded `approval.content_digest` as a separate field is left for a later version.
- The owner's answers on `primary_observed: false` (acceptable) and `WORKFLOW_UID` (separate
  decision) are recorded above and no longer open.
