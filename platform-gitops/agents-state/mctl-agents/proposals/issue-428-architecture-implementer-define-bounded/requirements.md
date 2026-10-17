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

None of these is a single, versioned statement of the form: "attempt X, under claim Y at
epoch Z, against approved proposal content D, produced head H; it ran these verification
checks with these results; this is what remains and why it stopped." So today "a PR
exists" stands in for "implementation complete".

This proposal defines one typed, sealed, versioned **ImplementationCompletion** record per
implementer attempt. It describes how the existing implement / review-remediation phase
ended. It is not a review verdict, not an approval, and not a new lifecycle owner or a
nested DevLoop. The implementer emits it. The existing carriers move it: `.status.yaml`
projection, `--completion-out` for the shepherd, and `record_execution` for mctl-api. Its
consumers can then branch on a closed outcome enum instead of on exit codes and prose.

## User stories

- AS the shepherd I WANT a typed completion outcome from each review-feedback run SO THAT
  I decide whether to charge `review_attempts` / `harness_failures` from a closed enum
  instead of a growing exit-code table.
- AS the DevLoopWorkflow I WANT to know whether an implement attempt that Argo reports as
  `Succeeded` actually finished its approved scope SO THAT `success` stops meaning only
  "a PR exists".
- AS an operator I WANT the stop reason, remaining work and verification results of an
  attempt in `.status.yaml` SO THAT I do not reconstruct intent from pod logs.
- AS a mctl-api / FinOps consumer I WANT each completion bound to the attempt, execution
  and claim identities SO THAT spend and results join to the same attempt without
  duplicates.
- AS a platform owner I WANT the contract to be unable to express approval, review-clean,
  merge, release or ownership change SO THAT the implementer cannot self-certify past its
  phase.

## Acceptance criteria (EARS)

Schema
- THE SYSTEM SHALL provide `orchestrator/implementation_completion.py`, defining
  `ImplementationCompletion` with `api_version: completion.mctl.ai/v1alpha1` and
  `kind: ImplementationCompletion`. It SHALL be a frozen dataclass with a canonical JSON
  form, a `sha256:` `content_hash`, a derived `completion_id` (`ic-` + 16 hex characters),
  and a `from_dict` that rejects unknown keys and unsupported api versions.
- THE SYSTEM SHALL restrict `outcome` to the closed set `complete`, `incomplete`,
  `bounded_refusal`, `budget_exhausted`, `deterministic_failure`, `harness_failure`.
- THE SYSTEM SHALL require these bindings on every record:
  - `subject`: service, slug, and optional `work_item_id`;
  - `attempt`: `attempt_id`, `phase` (`implement` | `review-remediation`), and the
    optional `execution_id` (`we_`), `context_id` (`ex-`), `claim_id` and `owner_epoch`;
  - `source`: repository, base ref and SHA, branch, head SHA or null;
  - `proposal`: `proposal_digest` over the approved requirements.md, design.md and
    tasks.md, plus an optional `review_bundle_digest`;
  - `verification`: a list bounded to 32 entries;
  - `remaining_work`: a list bounded to 32 entries;
  - `stop_reason`: a code from a closed set, plus an optional bounded detail;
  - `evidence_refs`: a list of `{evidence_id, kind}` only.
- THE SYSTEM SHALL bound each verification record to `check_id`, `result`
  (`pass` | `fail` | `unknown` | `not_run`), `classification` (closed set, e.g.
  `exit_zero`, `exit_nonzero`, `timeout`, `budget_denied`, `not_applicable`),
  `required: bool` and an optional `evidence_ref`. It SHALL hold no free-form
  stdout/stderr field.
- IF a record has `outcome == complete` AND any `required` verification has a result
  other than `pass`, OR `remaining_work` is non-empty, OR `source.head_sha` is null, THEN
  THE SYSTEM SHALL reject it at construction with `ImplementationCompletionError`.
- IF a record has `outcome` in {`incomplete`} AND `remaining_work` is empty, THEN THE
  SYSTEM SHALL reject it.
- THE SYSTEM SHALL bound every string leaf, as `execution_evidence.MAX_LEAF_CHARS` does,
  and SHALL redact `stop_reason.detail` and `remaining_work[].summary` through
  `orchestrator/redaction.py` before sealing.
- THE SYSTEM SHALL NOT define any field that expresses approval, review verdict, merge,
  release, ownership transfer, claim extension or budget extension. `from_dict` SHALL
  reject such keys as unknown.

Emission
- WHEN `_implement_one` or `_review_feedback_one` returns or raises on any arm after the
  claim is acquired, THE SYSTEM SHALL build exactly one `ImplementationCompletion` for
  that attempt, mapped deterministically from the existing exit code / `ImplementResult`
  arm by one pure function, `completion_from_result`.
- WHEN the implementer writes `implemented`, `needs-triage`, or a budget / policy
  hand-back to `.status.yaml`, THE SYSTEM SHALL also write a bounded `completion:`
  projection containing `completion_id`, `content_hash`, `outcome`, `stop_reason.code`,
  `attempt_id`, `head_sha` and verification counts. The projection SHALL hold no
  verification details or runtime telemetry.
- WHEN `--completion-out PATH` is given, THE SYSTEM SHALL write the full sealed record as
  JSON to PATH (best effort, bounded, like `_write_refusal_out`). The exit code SHALL
  remain the authoritative fallback.
- THE SYSTEM SHALL keep every existing exit code, `--refusal-out` payload and
  `.status.yaml` status transition unchanged.

Replay / retry / staleness
- THE SYSTEM SHALL derive `completion_id` from the content hash over `(subject, attempt,
  source, proposal, outcome, stop_reason, verification, remaining_work)` and SHALL
  exclude `created_at`. A redelivered or re-sealed identical record therefore has the same
  id.
- WHEN a completion is projected into a `.status.yaml` that already holds a `completion`
  with the same `attempt_id`, THE SYSTEM SHALL either leave it unchanged (same
  `completion_id`) or refuse the overwrite and log the conflict (different
  `completion_id`). It SHALL never replace a non-`complete` outcome with `complete` under
  the same `attempt_id`.
- IF the attempt's claim check (`_check_claim_or_raise`) fails at emission time, or the
  `.status.yaml` `attempt.id` no longer equals this attempt (`_status_is_still_ours`),
  THEN THE SYSTEM SHALL NOT project the completion into `.status.yaml`. It MAY still emit
  it to `--completion-out` with outcome `harness_failure` and stop reason `fenced` or
  `claim_refused`.
- WHEN a consumer reads a completion whose `attempt_id`, `owner_epoch` or `head_sha` does
  not match the consumer's current expectation, THE SYSTEM SHALL treat it as stale and
  fall back to the existing exit-code classification (fail closed). It SHALL never treat
  it as `complete`.

Consumers
- WHEN the shepherd receives a valid completion via `--completion-out` whose `attempt_id`
  matches the run it started, THE SYSTEM SHALL derive `FollowupKind` from `outcome` and
  `stop_reason.code`. IF the completion is absent, invalid, or disagrees with the exit
  code's class, THEN THE SYSTEM SHALL use the exit code and log the disagreement.
- WHEN `record_execution` is called for an implement step and the proposal's
  `.status.yaml` carries a `completion` projection for the attempt, THE SYSTEM SHALL send
  `completion_id`, `completion_outcome` and `completion_stop_reason` as optional wire
  fields, using the existing retry-without-optional-keys fallback.
- WHILE an implement attempt has Argo outcome `success` but completion outcome other than
  `complete`, THE SYSTEM SHALL expose that completion outcome in `ImplementExecutionState`
  and in the DevLoop result. It SHALL NOT change the DevLoop's control flow in this
  proposal.

Documentation
- THE SYSTEM SHALL add `docs/adr/021-implementation-completion-contract.md`. It SHALL
  state that this is an implementer-phase completion contract, not an independent review
  verdict, not an approval, and not another DevLoop, and SHALL give the mapping table from
  existing exit codes to outcomes.

## Out of scope

- Any new lifecycle owner, nested DevLoop, inner agent loop, or new retry / timeout /
  admission mechanism. #395, #418, #423 and #430 semantics are reused as they are.
- Changing how Claude, Agy or required CI gate a PR. Changing the shepherd's merge
  decision.
- mctl-api storage columns or read models for the new optional fields (cross-repo
  follow-up). This proposal only sends them.
- Durable evidence storage (ADR 018 Tier B). `evidence_refs` are pointers only.
- Making the implementer agent itself author the record. The orchestrator builds it from
  what it observed. The agent's existing `.implementer-refusal.json` marker remains the
  only agent-authored input.
- Changes to the CWFT in mctl-gitops: the existing `changes` artifact already carries
  `.status.yaml`.

## Open questions

- Approved-content identity. No approved-proposal digest exists today (`proposal_state.py`
  records only `approval.approved_by`). This proposal computes `proposal_digest` at attempt
  start over the three proposal files. If the approval flow later records its own digest,
  should the completion bind to that digest instead and fail closed on a mismatch?
  Assumed: bind to the attempt-start digest now, and add the approval digest as an
  optional field later.
- Verification sources. The orchestrator can observe only the commands that pass through
  the `exec_budget.CommandBudgetLedger` hook, plus its own post-run checks (new commits,
  chart guard, push). Which commands count as the "required" verification checks for a
  service is not defined anywhere. Assumed for v1alpha1: required checks are
  orchestrator-side gates (`commits_present`, `chart_major_guard`, `push_succeeded`).
  Agent-run test commands are recorded as non-required, with `result: unknown` unless the
  ledger observed an exit code.
- Whether `incomplete` is reachable from the current one-shot implementer at all. Today
  no arm says "partial work pushed, more remains". Assumed: it is reachable only when the
  agent's refusal marker carries a new optional `remaining` list. Otherwise the enum value
  is reserved and tested, but not emitted.
- Whether the DevLoop should eventually fail or park on `success` + non-`complete`. Left
  as observe-only here.
