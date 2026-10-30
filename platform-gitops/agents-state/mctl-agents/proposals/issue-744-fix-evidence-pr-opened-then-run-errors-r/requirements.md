# Record the PR subject on run evidence as soon as the implementer knows it

## Context

Issue mctlhq/mctl-agents#744 follows #735 / #740 (shipped in 1.89.0). In
`orchestrator/run_implementer.py::_implement_one`, the new-PR path calls
`_push_and_open_pr(...)` (the PR now exists), then `_note_pushed_head(target)`,
then `update_status_yaml(ref, "implemented", ...)` and `_release_claim(...)`.
If anything after `_push_and_open_pr` raises, an `except` arm returns
`ImplementResult(pr_url=None, error=...)`. The PR is only ever named to the
execution evidence by `_note_implement_evidence`, and only when
`result.pr_url` is set, so `RunEvidence.pending_pr` / `RunEvidence.subject`
stay empty and `evidence_producer.build()` seals
`Gap(block="subject", code="not_applicable", required=False)`. That reports
"could not observe" as "observed absent": a PR and a pushed head exist, but
the evidence says the run had no subject.

The same class exists in `_review_feedback_one` (the PR URL is read from
`.status.yaml` only after `_push_followup`, so a failure in or before that read
loses the subject) and in `_implement_one`'s preflight adoption arms
(`existing.action` in `open` / `merged` / `closed`), where `update_status_yaml`
runs before the `ImplementResult` carrying the PR is returned.

## User stories

- AS a platform operator reading execution evidence I WANT a run that opened
  or pushed to a PR to always name that PR (or a required gap) SO THAT a
  failed run is never mistaken for one that touched no PR.
- AS an auditor consuming Tier A / Tier B evidence I WANT `not_applicable` on
  `subject` to mean "this run had no PR" only SO THAT completeness is trustworthy.

## Acceptance criteria (EARS)

- WHEN `_push_and_open_pr` returns a PR URL in `_implement_one` THE SYSTEM
  SHALL record that PR on the active run evidence before
  `update_status_yaml(ref, "implemented", ...)` and `_release_claim(...)` run,
  bound to the head recorded by `_note_pushed_head` when one was recorded.
- IF `update_status_yaml` (or `_release_claim`, or any later step) raises after
  the PR was opened THEN the sealed evidence (Amendment 2 enabled) SHALL carry
  either a `pull_request` subject whose `revision` is the pushed head, or a
  required `Gap(block="subject", code="observation_failed")`, and SHALL NOT
  carry `Gap(block="subject", code="not_applicable")`.
- WHEN `_review_feedback_one` has pushed a follow-up commit THE SYSTEM SHALL
  record on the run evidence the PR URL it read from `.status.yaml` before the
  push (`pre_status["pr"]`), bound to the pushed head, before any further step
  that can raise.
- WHEN a preflight arm of `_implement_one` adopts an existing PR (`open`,
  `merged`, `closed`, `needs-triage` with a PR URL) THE SYSTEM SHALL record that
  PR at `existing.head_sha` on the run evidence before it calls
  `update_status_yaml` / `_mark_needs_triage`.
- WHILE a run's evidence already holds a PR subject bound to an observed head
  THE SYSTEM SHALL keep that binding when `_note_implement_evidence` later names
  the same PR without a head (existing `note_subject_pr` behaviour).
- IF recording the subject itself fails THEN THE SYSTEM SHALL continue the run
  unchanged (evidence bookkeeping is never fatal; use `evidence_producer.note`).
- WHEN the implementer path ends without ever opening, adopting or pushing to
  a PR THE SYSTEM SHALL continue to seal `subject` as `not_applicable`.
- The regression test for the `update_status_yaml`-raises case SHALL fail when
  the early recording in `_implement_one` is reverted.

## Out of scope

- Changing the outcome vocabulary or `ImplementResult` mapping in
  `_note_implement_evidence` (the run still reports `failed` /
  `implementer-error`; only its subject changes).
- Changing `.status.yaml` triage behaviour, claim release, or retry semantics.
- A branch pushed but whose `gh pr create` failed (no PR exists, so no PR
  subject is claimed); the pushed-head-without-PR case is not addressed here.
- Changes to `evidence_producer.build()` or the execution-evidence schema.

## Open questions

- Should the pushed-but-no-PR case (push succeeded, `_open_pr_for_branch`
  raised) seal something other than `not_applicable` (for example a required
  `subject` gap because a branch exists)? This proposal leaves it unchanged; a
  follow-up issue can decide.
- No deployed-state facts were needed (pure code change in an orchestrator
  library); see design.md "Deployed state checked".
