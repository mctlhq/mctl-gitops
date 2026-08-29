# Tasks: issue-913-path-guard-auto-merge-for-claude-branche

- [ ] 1. Add `scripts/check_pr_path_allowlist.py`: reads newline-separated
      changed-file paths from stdin, checks each against
      `ALLOWED_PREFIXES = ("platform-gitops/services/",
      "platform-gitops/agents-state/")` via `str.startswith()`, prints any
      non-matching path to stdout (one per line), exits `1` if any
      non-matching path exists, exits `0` otherwise (including on empty
      input). No third-party dependencies. — DoD: script runs standalone
      via `printf 'a\nb\n' | python3 scripts/check_pr_path_allowlist.py`
      and exits/prints correctly for allowed-only, mixed, and
      blocked-only input.

- [ ] 2. Modify `.github/workflows/auto-merge.yml`'s `auto-merge` job
      (depends on 1):
      - Add `actions/checkout` (reuse the pinned SHA from
        `validate-manifests.yml`) with
        `ref: ${{ github.event.pull_request.base.ref }}`.
      - Add a `path-check` step: fetch changed files via
        `gh api "repos/${{ github.repository }}/pulls/${{
        github.event.pull_request.number }}/files" --paginate --jq
        '.[].filename'`, pipe into
        `scripts/check_pr_path_allowlist.py`, capture blocked-file
        output and exit status, write `allowed=true`/`allowed=false` to
        `$GITHUB_OUTPUT`. Do not let the python exit code fail the step;
        let a `gh api` failure (network/auth error) fail the step
        naturally (`set -euo pipefail`, no swallowing on that command).
      - Gate the existing `gh pr merge --merge --delete-branch` step on
        `steps.path-check.outputs.allowed == 'true'`.
      - Add a `comment-path-guard` step gated on
        `steps.path-check.outputs.allowed == 'false'`: check existing PR
        comments for the marker `<!-- auto-merge-path-guard -->` via
        `gh api repos/${{ github.repository }}/issues/${{
        github.event.pull_request.number }}/comments`; if absent, `gh pr
        comment` with the marker, the blocked-file list, and an
        explanation that manual merge is required.
      — DoD: workflow YAML is valid (passes whatever YAML lint the repo
      runs — `yamllint.yml` — and is structurally sound: `gh act`/manual
      read-through confirms step ordering and `if:` conditions reference
      valid prior step IDs/outputs).

- [ ] 3. Update the in-file comment above the `auto-merge` job (depends on
      2) to describe the new gate, mirroring the explanatory-comment style
      already used in this workflow and in `gitops-bump.yaml` /
      `release-deploy.yaml` — DoD: a reader with no prior context can tell
      from the comment alone why the allowlist exists and how to widen it.

- [ ] 4. Add a short note to CLAUDE.md's "Branch Protection Exception"
      section (or a new adjacent section) documenting that `claude/*`
      auto-merge is now path-scoped, cross-referencing the two allowed
      prefixes, so the exception's documented safety story stays accurate
      (depends on 2) — DoD: CLAUDE.md text matches the actual
      `ALLOWED_PREFIXES` in `scripts/check_pr_path_allowlist.py`.

## Tests

- [ ] T1. Unit-style check for `scripts/check_pr_path_allowlist.py`
      covering: (a) all paths under `platform-gitops/services/**` ->
      exit 0, no output; (b) all paths under
      `platform-gitops/agents-state/**` -> exit 0; (c) a mix of allowed
      and a single `.github/workflows/auto-merge.yml` path -> exit 1,
      output contains exactly that path; (d) empty stdin -> exit 0.
      Can be a small script invoked from `validate-manifests.yml` or a
      standalone `scripts/test_check_pr_path_allowlist.py` — either is
      acceptable, but it must run in CI so a future edit to the allowlist
      logic can't silently regress.
- [ ] T2. Manual/integration verification per the issue's own acceptance
      test: open a `claude/*` PR that touches only
      `platform-gitops/services/<team>/<svc>/values.yaml`, get it
      approved, confirm it still auto-merges (no behavior change for the
      routine case).
- [ ] T3. Manual/integration verification: open a `claude/*` PR that
      touches `.github/workflows/**` (or any other out-of-allowlist path),
      get it approved, confirm the merge is skipped and exactly one
      explanatory comment appears containing the marker and the blocked
      path.
- [ ] T4. Manual/integration verification: on the PR from T3, request a
      second approving review (or re-trigger `pull_request_review`) and
      confirm no second comment is posted (de-dup via the marker works).
- [ ] T5. Verify the paginated `gh api ... /files --paginate` call against
      a PR with >100 changed files does not truncate — can be verified by
      reading the `--paginate` behavior in `gh` docs plus a code review
      check that no `--jq` step downstream re-introduces a 100-item cap;
      a live >100-file PR is not required to land this proposal but should
      be noted as unverified-at-scale in the PR description.

## Rollback

Revert the single commit/PR that lands tasks 1-4 (`git revert` on
`mctl-gitops` `main`, or hand-edit): removing the `path-check` and
`comment-path-guard` steps and the `actions/checkout` step from
`auto-merge.yml`'s `auto-merge` job restores the exact prior behavior
(merge on first approval, no path inspection). Deleting
`scripts/check_pr_path_allowlist.py` is optional and has no effect once
the workflow no longer references it. No state, no data, no in-flight
migration — safe to revert at any time with a single PR (which, per the
existing rule, needs review since it touches `.github/workflows/**`).

## Operator decision: REJECTED (2026-08-29)

Premise is stale. Verified 2026-08-28/29: the last 60 merges to
mctl-gitops main contain zero `claude/*` branches, and agents-state
changes land via direct bot push (DeployKey bypass), not via `claude/*`
PRs — the path-guard would gate a flow that no longer exists, while
adding real friction (self-blocking rollout, throwaway PRs to test,
interference with interactive claude/* sessions). The actual residual
exposure is bypass-token direct pushes, which is a different control
(audit of bypass actors), tracked separately. Issue closed with this
rationale; no implementation.
