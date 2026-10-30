# Harden landed-binding correlation after the #812 review

## Context
PR #812 (mctlhq/mctl-agents#809) added landed-fix binding for SecurityFinding remediation: the
`security_record_landed` DevLoop activity (`orchestrator/security_findings/landed.py::bind_landed`)
and the verifier sweep's fallback for a missed hook (`orchestrator/run_security_verifier.py::_bind_missed`
with `default_merged_lookup`). The review on the merged head reported two P2 correctness defects:

1. `default_merged_lookup` reconstructs the repository from the DevLoop workflow id with a lazy regex
   (`^dev-loop-[A-Za-z0-9_.-]+?-([A-Za-z0-9_.-]+)-(\d+)$`). Because owners and repos may both contain
   hyphens, `dev-loop-my-org-my-repo-42` yields repo `org-my-repo`, the proposal/PR lookup misses, and a
   real occurrence can stay in `fixing` forever.
2. `bind_landed` appends `LandedOutcome(summary.id, UNKNOWN)` when reading a candidate fails, before
   proving the candidate's active attempt belongs to the current `workflow_id`. With several remediations
   in one repository, a transient failure attributes an unrelated occurrence to the current DevLoop's
   `DevLoopResult.security`.

This issue is a release/enablement blocker for the verifier sweep: it must not be scheduled until both are fixed.

## User stories
- AS a platform operator I WANT the fallback sweep to look up the proposal/PR using the occurrence's own
  repository identity SO THAT a hyphenated owner or repo name can never redirect or break the lookup.
- AS a DevLoop consumer reading `DevLoopResult.security` I WANT it to list only occurrences proven to belong
  to that DevLoop SO THAT an unrelated occurrence is never reported as this loop's outcome.

## Acceptance criteria (EARS)
- WHEN the sweep fallback resolves a merged PR for a `fixing` occurrence THE SYSTEM SHALL take the repository
  name from the occurrence's `subject.repository` (full read, else the listing summary), never from the
  workflow id.
- WHEN the occurrence repository is `github.com/mctlhq/<repo>` or `mctlhq/<repo>` THE SYSTEM SHALL use `<repo>`
  for `find_proposal_slug` / `get_pr_state` only if the attempt's `devloop_workflow_id` equals exactly
  `dev-loop-mctlhq-<repo>-<N>` with `<N>` all digits, and SHALL take the issue number `<N>` from that terminal
  segment only.
- IF the occurrence repository is empty, unparseable, on a host other than `github.com`, or owned by anything
  other than `mctlhq` THEN THE SYSTEM SHALL skip the merged lookup for that occurrence (return "not known to be
  merged") and emit a diagnostic line, without any GitHub/gitops call.
- IF the workflow id does not equal `dev-loop-mctlhq-<repo>-<digits>` for the occurrence's repository THEN THE
  SYSTEM SHALL skip the lookup (no repository is ever guessed from the id).
- WHEN the workflow id is `dev-loop-my-org-my-repo-42` THE SYSTEM SHALL NOT call the proposal/PR lookup with
  `org-my-repo` (or any repo derived from the id).
- IF `bind_landed` cannot read a candidate occurrence (non-OK verdict or no body) THEN THE SYSTEM SHALL NOT
  emit a `LandedOutcome` carrying that candidate's id, and SHALL log the skipped candidate id to stderr/stdout
  as an unscoped warning.
- WHILE two `fixing` occurrences exist in the same repository and reading one fails THE SYSTEM SHALL return
  only the outcome of the occurrence whose active attempt's `devloop_workflow_id` equals the current workflow id.
- IF the `fixing` listing itself fails THEN THE SYSTEM SHALL keep returning the existing unscoped
  `LandedOutcome("", UNKNOWN)` (empty occurrence id), unchanged.
- WHILE binding is replayed or re-delivered THE SYSTEM SHALL keep the existing idempotency keys
  (`sra-fix`, attempt id, merge commit) and existing test behaviour.

## Out of scope
- Pagination / starvation visibility of the 50-item fallback cap (`SWEEP_CAP`).
- Retry UX returning `devloop_exists` instead of `already_active`.
- Supporting owners other than `mctlhq` (kept explicit; only the regex fragility is removed).
- Scheduling the verifier CronWorkflow in mctl-gitops.

## Open questions
- Whether an unread unmatched candidate should additionally surface as a separate unscoped diagnostic in the
  activity result. This proposal chooses log-only (the issue allows either), so `DevLoopResult.security`
  retains its current shape and can only contain proven matches plus the pre-existing listing-failure marker.
