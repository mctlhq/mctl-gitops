# Implementer-phase ImplementationCompletion handoff contract

## Context

The Tier 2 implementer (`orchestrator/run_implementer.py`) ends one attempt in one of
three ways. It flips `.status.yaml` to `implemented` with a `pr:` URL. Or it writes
`needs-triage` / `blocked` / `rate_limited`, or hands the proposal back to `accepted`. Or,
in shepherd review-feedback mode, it exits with one of the sentinel codes 0, 42-54
(`EXIT_NO_FOLLOWUP_COMMITS` ... `EXIT_POLICY_UNDECIDED`) plus an optional `--refusal-out`
JSON. Two further layers interpret those signals:
- Temporal reads only Argo's node graph (`orchestrator/temporal/implement_outcome.py`:
  `pre_start` / `execution` / `finalization` / `success`).
- The shepherd folds the exit codes into `transient` / `deterministic` / `harness` /
  `refused` / `fenced` (`run_shepherd.FollowupSubprocessError`).

None of these is a single, versioned statement of the form: "attempt X, step S of Argo run
R, under claim Y at epoch Z, against proposal content D, produced head H; it ran these
checks with these results; this is what remains and why it stopped." So today "a PR
exists" stands in for "implementation complete".

This proposal defines one typed, sealed, versioned **ImplementationCompletion** record per
implementer attempt step, and a deterministic rule for which record is authoritative when
the CWFT's `implement` and `implement-fallback` steps both run inside one Argo workflow. It
describes how the existing implement / review-remediation phase ended. It is not a review
verdict, not an approval, and not a new lifecycle owner or a nested DevLoop.

In v1alpha1, `complete` means exactly: "the attempt pushed a head that passed the
orchestrator gates" (`commits_present`, `chart_major_guard`, `push_succeeded`,
`claim_valid_at_push`). It does NOT mean "the approved scope is implemented": no check yet
compares the result against the approved `tasks.md`. Task-coverage verification is a named
follow-up.

This revision addresses the owner review of the 2026-10-17 proposal: fallback-step
authority (point 1), a three-PR split (point 2), and an honest definition of `complete`
(point 3).

## User stories

- AS the shepherd I WANT a typed completion outcome from each review-feedback run SO THAT
  I decide whether to charge `review_attempts` / `harness_failures` from a closed enum
  instead of a growing exit-code table.
- AS the DevLoopWorkflow I WANT to know whether an implement run that Argo reports as
  `Succeeded` actually passed the orchestrator gates, and which step produced the result,
  SO THAT `success` stops meaning only "a PR exists".
- AS an operator I WANT a failing `implement-fallback` (typically a harness failure on the
  second account) never to hide the primary step's real outcome SO THAT triage starts from
  the actual cause.
- AS an operator I WANT the stop reason, remaining work and verification summary of an
  attempt in `.status.yaml` SO THAT I do not reconstruct intent from pod logs.
- AS a mctl-api / FinOps consumer I WANT each completion bound to the Argo run, step,
  attempt, execution and claim identities SO THAT spend and results join without
  duplicates.
- AS a platform owner I WANT the contract to be unable to express approval, review-clean,
  merge, release or ownership change SO THAT the implementer cannot self-certify past its
  phase.

## Acceptance criteria (EARS)

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
  - `proposal`: `proposal_digest` over requirements.md, design.md and tasks.md, plus an
    optional `review_bundle_digest`;
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
- WHEN the implementer writes `implemented`, `needs-triage`, or a budget / policy
  hand-back to `.status.yaml`, THE SYSTEM SHALL also write a bounded `completion:`
  projection (authoritative record summary plus an optional summary of the other step).
  The projection SHALL hold no verification details or runtime telemetry.
- WHEN `--completion-out PATH` is given, THE SYSTEM SHALL write the full sealed record as
  JSON to PATH (best effort, bounded). The exit code SHALL remain the fallback signal.
- THE SYSTEM SHALL keep every existing exit code, `--refusal-out` payload and
  `.status.yaml` status transition unchanged.

Primary / fallback authority (owner review point 1)
- WHEN the fallback step seals a record AND the primary step's handoff from the same
  `run_id` is readable, THE SYSTEM SHALL select the authoritative record with
  `select_authoritative(primary, fallback)`:
  - IF the fallback outcome is `complete` THEN the fallback record is authoritative and
    the primary record is kept as a `superseded` summary;
  - OTHERWISE the primary record stays authoritative and the fallback record is kept as a
    `fallback` summary. A fallback record SHALL never replace a primary record unless it
    is `complete`.
- IF the fallback step never reaches the claim (token unset, `ensure_auth_for_sdk`
  failure) THEN THE SYSTEM SHALL emit nothing for it and the primary's handoff artifact
  SHALL remain the one committed.
- IF the fallback step cannot read any primary handoff THEN THE SYSTEM SHALL project its
  own record with `primary_observed: false`, and consumers SHALL NOT read that record as
  the primary's outcome.
- THE SYSTEM SHALL pin this with tests for primary-fails then fallback-fails (primary
  authoritative) and primary-fails then fallback-succeeds (fallback authoritative).

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
- WHEN a consumer reads a completion whose `run_id`, `attempt_id`, `owner_epoch` or
  `head_sha` does not match its expectation, THE SYSTEM SHALL treat it as stale and fall
  back to existing exit-code / Argo classification. It SHALL never treat it as `complete`.

Consumers (PR 2 and PR 3)
- WHEN the shepherd receives a valid completion via `--completion-out` whose attempt
  matches the run it started, THE SYSTEM SHALL derive `FollowupKind` from it in shadow
  mode, log `completion-disagreement` against the exit-code class, and change charging
  behaviour only when `SHEPHERD_TRUST_COMPLETION` is on (default off).
- WHEN `record_execution` is called for an implement step and the proposal's
  `.status.yaml` carries a `completion` projection whose `run_id` equals the Argo workflow
  name Temporal submitted, THE SYSTEM SHALL send `completion_id`, `completion_outcome`,
  `completion_stop_reason` and `completion_step` as optional wire fields, behind
  `workflow.patched("implement-completion")`, with no control-flow change.

Delivery
- THE SYSTEM SHALL be delivered as three PRs merged in order: PR 1 contract, emission,
  projection, fallback authority and ADR 021; PR 2 shepherd shadow consumption; PR 3
  Temporal read and `ExecutionRecord` fields.

Documentation
- THE SYSTEM SHALL add `docs/adr/021-implementation-completion-contract.md`. It SHALL state
  that this is an implementer-phase completion contract, not an independent review
  verdict, not approval and not another DevLoop; give the outcome mapping table; state the
  primary / fallback authority rule; state the v1alpha1 meaning of `complete`; and record
  task-coverage verification as a named follow-up.

## Out of scope

- Any new lifecycle owner, nested DevLoop, inner agent loop, or new retry / timeout /
  admission mechanism. #395, #418, #423 and #430 semantics are reused as they are.
- Task-coverage verification (comparing the pushed head with the approved `tasks.md`).
  Named follow-up, not part of v1alpha1.
- Changing how Claude, Agy or required CI gate a PR, or the shepherd's merge decision.
- Changing the CWFT's step order or the rule that the fallback's `.status.yaml` status
  transition is the one committed when it writes one.
- mctl-api storage columns or read models for the new optional fields (cross-repo
  follow-up).
- Durable evidence storage (ADR 018 Tier B).
- Letting the implementer agent author the record.

## Open questions

- The owner review states that `_resolve_attempt_id` returns the same `WORKFLOW_UID` for
  both steps. The deployed `cwft-mctl-agents-implement.yaml` does not set `WORKFLOW_UID`
  for `run-implementer`, so today each pod derives `sha256(service|slug|0|0|HOSTNAME)` and
  the two steps get different ids. The design does not rely on either behaviour: it binds
  `run_id` + `step` explicitly. Should the CWFT set `WORKFLOW_UID` as the code's docstring
  assumes? Left as a separate decision.
- The fallback pod's own gitops clone cannot see the primary's status, because
  `commit-and-push` runs after both steps. Reading the primary's handoff requires one
  small mctl-gitops change: an optional input artifact on `run-implementer` at the
  existing key `{{workflow.name}}/agents-state.tgz`. Until it is deployed, the fallback
  projects with `primary_observed: false`. Is that interim acceptable?
- Approved-content identity: `proposal_digest` is computed at attempt start. Should it
  later bind to an approval-time digest and fail closed on mismatch?
- `incomplete` is reachable only via a new optional `remaining` list in
  `.implementer-refusal.json`. Is that extension acceptable?
- Whether the DevLoop should eventually park on `success` + non-`complete`. Observe-only
  here.
