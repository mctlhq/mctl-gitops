# Never bind a PR evidence subject to a head read at seal time

## Context

ADR 018 Amendment 2 execution evidence names the PR a run worked on as its
`subject`, at a `revision` (a head SHA). Today
`orchestrator/evidence_producer.py:build()` has a fallback: when a run named a
PR (`RunEvidence.pending_pr`) but recorded neither the head it read nor a head
it pushed, `build()` calls `read_pr_head_sha()` (`gh api repos/<r>/pulls/<n>
--jq .head.sha`) at seal time and binds the subject to whatever the PR head
is at that moment. That head can be one the run never saw: a follow-up commit
pushed while the run was finishing becomes "observed" evidence about a run
that did not observe it. This breaks the repository invariant that "could
not observe" is a gap, never a substituted value. Amendment 2 is live: the
deployed implement, investigate and shepherd CWFTs set
`MCTL_EVIDENCE_AMENDMENT_2="true"`, so this path runs in production.

This proposal is Part B1 of mctlhq/mctl-agents#735 (mctl-agents only). It
removes the seal-time read, records a required `subject` gap instead, and
makes the implementer pass the PR head it did observe on its GitHub preflight
paths. Parts A (sparse gitops checkout, mctl-gitops) and B2 (`base_sha` on
subjects, mctl-api then mctl-agents) are separate issues.

## User stories

- AS an auditor reading execution evidence I WANT a PR subject's revision to
  always be a head the run itself read or pushed SO THAT the evidence never
  claims an observation the run did not make.
- AS an operator I WANT a run that could not observe its PR head to produce
  an INCOMPLETE envelope with an explicit required `subject` gap SO THAT the
  unknown is visible rather than hidden behind a later head.
- AS the implementer runner I WANT to hand the head SHA I read in the GitHub
  preflight to the evidence SO THAT PR-exists runs still get a bound subject.

## Acceptance criteria (EARS)

- WHEN `build()` seals an Amendment 2 envelope for a run that named a PR and
  recorded neither an observed head nor a pushed head THE SYSTEM SHALL set
  `subject=None`, `provenance=None` and add
  `Gap(block="subject", code="observation_failed", required=True)`, and the
  envelope SHALL be `INCOMPLETE`.
- WHILE sealing evidence THE SYSTEM SHALL NOT make any GitHub (`gh`) call to
  read a PR head.
- THE SYSTEM SHALL NOT expose `read_pr_head_sha`, the `PrHeadReader` type, or
  a `read_pr_head` keyword on `build()` / `produce()`.
- WHEN a run recorded a pushed head (`note_pushed_head`) before or after
  naming the PR THE SYSTEM SHALL bind the subject to that pushed head
  (existing behaviour preserved, order-independent).
- WHEN the shepherd's `process_one` reads a PR snapshot with a non-empty
  `headRefOid` THE SYSTEM SHALL bind the subject to that head (unchanged).
- IF the shepherd's PR snapshot has an empty `headRefOid` THEN THE SYSTEM
  SHALL record the required `subject` gap and make no extra `gh` call.
- WHEN the implementer's GitHub preflight finds an existing PR (`open`,
  `merged`, `closed`, or `needs-triage` with a PR) carrying a `headRefOid`
  THE SYSTEM SHALL bind the evidence subject to that head.
- IF the implementer names a PR without any head it read or pushed (e.g. a
  failed `_capture_head_sha`, an error after the PR was opened) THEN THE
  SYSTEM SHALL record the required `subject` gap.
- WHEN a PR subject was already bound to an observed head and the same PR is
  named again without a head THE SYSTEM SHALL keep the bound subject rather
  than discard it.
- WHILE the subject is unchanged THE SYSTEM SHALL produce byte-identical
  envelopes and identical `evidence_id`s to today (no schema change; no new
  gap code).

## Out of scope

- Part A: sparse / blobless gitops clones in the agent CWFTs (mctl-gitops).
- Part B2: `base_sha` on `SubjectRef` (mctl-api first, then mctl-agents).
- Any mctl-api change; adding a new gap code such as `not_observed`.
- Changing the investigator (it records issue subjects only,
  `run_issue_investigator.py:3396`).
- Changing `_note_pushed_head` / `_capture_head_sha` (local `git rev-parse`,
  not a GitHub read).

## Open questions

- Gap code: the issue offers `not_observed` or `observation_failed`. This
  proposal uses `observation_failed`, because `not_observed` is not in
  `execution_evidence.GAP_CODES` and adding it would need an mctl-api schema
  change, which the issue rules out for B1. `observation_failed` is already
  in `UNKNOWN_GAP_CODES` (forced `required=True`), which fits the meaning.
- The issue says to remove the test at `tests/test_evidence_producer.py:882`
  "with the function". That test
  (`test_the_evidence_head_read_is_bounded_at_ten_seconds`) actually checks
  the 10 s bound on `run_implementer._note_pushed_head` ->
  `_capture_head_sha` (a local git read that stays). This proposal keeps it;
  the reviewer should confirm.
- `review_feedback_one` (the shepherd-driven follow-up path) reads `old_head`
  (`run_implementer.py:3024`) before pushing; it is not passed as the subject
  head because it is the pre-push head, not the head the run produced. If the
  push succeeds `_note_pushed_head` covers it; if not, the gap is correct.
