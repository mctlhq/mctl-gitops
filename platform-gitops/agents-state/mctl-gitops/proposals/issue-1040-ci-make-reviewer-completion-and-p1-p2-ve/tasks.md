# Tasks: issue-1040-ci-make-reviewer-completion-and-p1-p2-ve

- [ ] 1. Capture a real Agy review payload from this repo's PR history via
      `gh api repos/mctlhq/mctl-gitops/issues/<n>/comments`,
      `.../pulls/<n>/comments`, and `.../pulls/<n>/reviews` for a PR Agy has
      actually reviewed, and record the exact actor login, marker text, and
      severity-encoding shape found. — DoD: a short note (can live as a
      comment in the new script) documents the confirmed format, replacing
      the recorded assumption in `requirements.md`'s Open questions; if the
      real format differs from `<!-- agy-review -->` + the assumed severity
      shape, the parser below is written against the real shape, not the
      assumption.

- [ ] 2. Add `.github/scripts/review_gate.py`: a self-contained script with
      `--selftest` (following `deploy-signal.py` / `scripts/validate-*.py`
      convention — "a checker that has never been seen to fail is not known
      to work") that: resolves a PR's live head SHA; queries
      `actions/runs?head_sha=` for `claude-review.yml` and `agy-review.yml`,
      returns "not yet terminal" if either is missing/incomplete for that
      head; once both are terminal, fetches reviews/PR comments/issue
      comments, filters by actor login and time-window per reviewer, and
      extracts P1/P2 severity using the two marker shapes described in
      `design.md`; returns a structured verdict (`pending` /
      `success` / `failure(reviewer, reason)`). (depends on 1) — DoD:
      `python3 .github/scripts/review_gate.py --selftest` exercises all
      three verdict branches (pending, clean success, P1/P2 failure) plus
      the "run concluded non-success with no clean marker" fail-closed
      branch, against fixture payloads, with no live network calls.

- [ ] 3. Add `.github/workflows/review-gate.yml` with the three jobs from
      `design.md`: (a) `pull_request` → POST `pending` with an embedded
      deadline; (b) `workflow_run` on `["Claude PR review", "Agy PR
      review"]` completed → re-verify current head, then run
      `review_gate.py` and POST the resulting status; (c) `schedule
      */10 * * * *` → sweep open PRs, flip any `pending` past its deadline
      to `failure` naming the missing reviewer(s). `permissions:
      contents: read, pull-requests: read, actions: read, statuses: write`
      (no other repo write). (depends on 2) — DoD: workflow parses
      (`yamllint`), and a test PR against a scratch/preview branch shows
      `review-gate` go `pending` on push, then `success` once both
      `claude-review` and `agy-review` post clean, using this repo's own
      dogfood PR for this change.

- [ ] 4. Flip `.github/workflows/agy-review.yml`'s `blocking: false` to
      `blocking: true` and update its surrounding comment (no longer
      "reviewed manually until #240" — reviewed by `review-gate` now,
      independent of `mctl-agents#240`'s unrelated shepherd work).
      (depends on 3, land in the same PR so the two signals never disagree
      in an intermediate state) — DoD: diff is exactly the flag + comment;
      no other behavior change to that workflow.

- [ ] 5. Regression test mirroring the issue's reproduction: a synthetic
      pair of fixture runs in `review_gate.py`'s test suite where Claude's
      run completes clean first and Agy's completes later with a P2 —
      assert `review-gate` is not `success` while Agy is outstanding, and
      is `failure` once Agy's P2 lands, even though Claude was already
      clean. — DoD: test named after `#1038`'s reproduction, fails on the
      pre-#1040 assumption ("first reviewer's clean verdict is enough") if
      accidentally reintroduced.

- [ ] 6. Document the manual override path in `docs/soc2/emergency-
      change.md`: an operator may POST a commit status directly
      (`gh api repos/mctlhq/mctl-gitops/statuses/{sha} -f state=success -f
      context=review-gate -f description="manual override: <reason>"`) to
      unstick a wedged or incorrectly-failing `review-gate`, given
      `current_user_can_bypass=never` on this ruleset means no ruleset-level
      escape hatch exists. Cross-reference from `design.md`'s Risks section.
      (depends on 3) — DoD: `emergency-change.md`'s "Allowed actions" list
      gains this as an explicit item; the existing "afterward, within 7
      days" write-up requirement is unchanged and now demonstrably covers
      this case too.

- [ ] 7. After 1-6 are merged and `review-gate` has been observed `success`
      on at least one real PR (staged rollout per `design.md`'s Platform
      impact), request the owner/admin action to add `review-gate` to
      `main-protection`'s required status checks — out of scope for this
      proposal's code change, tracked here so it isn't lost. (depends on 3,
      4, 5)

## Tests

- [ ] T1. `review_gate.py --selftest`: pending / clean-success /
      P1-failure / P2-failure / non-success-run-fail-closed branches, per
      task 2's DoD.
- [ ] T2. `#1038`-reproduction regression from task 5: Claude-clean-first,
      Agy-P2-later stays unmergeable, then ends `failure`.
- [ ] T3. Stale-head guard: an evaluator run for a `head_sha` that no longer
      matches the PR's live head SHA posts nothing (verifies the new-push
      invalidation acceptance criterion instead of silently reusing an old
      verdict).
- [ ] T4. Timeout sweep: a `pending` status past its recorded deadline with
      no terminal run for one reviewer flips to `failure` naming that
      reviewer, not `success`.
- [ ] T5. `yamllint` / `helm`-adjacent CI sanity: `review-gate.yml` parses
      and its `permissions:` block is exactly `contents: read,
      pull-requests: read, actions: read, statuses: write` (no accidental
      over-grant, matching `docs/runbooks/github-app-scope-audit.md`'s "no
      write beyond what's needed" norm for internal automation).

## Rollback

Revert the `review-gate.yml` / `review_gate.py` / `agy-review.yml`
`blocking` commits. If `review-gate` has already been registered as a
required status check on `main-protection` (task 7), the admin removes it
from the ruleset's required-checks list *before* the revert lands — an
already-required check with no workflow left to satisfy it would otherwise
block every subsequent merge, including the revert PR itself. No data or
schema to roll back; `.status.yaml`/GitOps state elsewhere is untouched by
this change.
