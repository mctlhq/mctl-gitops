# Tasks: issue-25-ci-add-claude-review-yml-automated-pr-re

- [ ] 1. Author `.github/workflows/claude-review.yml` — DoD: file exists in
  the repo with correct YAML structure; triggers on `pull_request` types
  `[opened, reopened, synchronize, ready_for_review]`; draft-skip `if:`
  condition on the job; `actions/checkout` pinned to
  `de0fac2e4500dabe0009e67214ff5f5447ce83dd`; `claude-code-action` pinned to
  `51ea8ea73a139f2a74ff649e3092c25a904aed7e`; `model: claude-opus-4-8`;
  `allowed_tools` matches spec; `claude_code_oauth_token` wired to secret;
  prompt covers TypeScript ESM rules, plugin-SDK boundary, Vitest conventions,
  P1/P2/P3 severity, and trivial-diff short-circuit; no tabs in the file;
  `permissions` block includes `contents: read` and `pull-requests: write`;
  `concurrency` group scoped to PR number with `cancel-in-progress: true`;
  `timeout-minutes: 10`.

- [ ] 2. Open a pull request from a feature branch (depends on 1) — DoD: PR
  exists on `mctlhq/mctl-openclaw` targeting `main`; PR body explains the
  bootstrap caveat (anti-tamper check will not pass on this PR by design; merge
  directly); PR references issue #25 with `Closes #25`.

- [ ] 3. Merge the bootstrap PR directly without waiting for a passing
  `claude-review` status check (depends on 2) — DoD: `.github/workflows/
  claude-review.yml` is present on `main`; `CLAUDE_CODE_OAUTH_TOKEN` secret is
  consumed by a live workflow on `main`; the next non-bootstrap PR triggers and
  completes a real automated review.

## Tests

- [ ] T1. After step 1: run `actionlint` locally on
  `.github/workflows/claude-review.yml` (or confirm `workflow-sanity.yml`
  passes on the bootstrap PR's CI run) — DoD: zero `actionlint` errors; zero
  tab characters in the file.

- [ ] T2. After step 3: open a follow-up test PR with a small TypeScript change
  — DoD: the `claude-review` workflow job appears in the PR's status checks,
  completes, and posts at least one inline comment or a summary comment to the
  PR using the configured allowed tools.

- [ ] T3. After step 3: open a draft PR — DoD: the `claude-review` job does
  not appear as triggered (draft-skip guard works).

- [ ] T4. After step 3: mark the draft PR from T3 as ready-for-review — DoD:
  the `claude-review` job triggers and completes.

## Rollback

Delete `.github/workflows/claude-review.yml` from `main` in a follow-up
commit. No other files are touched by this change, so rollback has no side
effects. The `CLAUDE_CODE_OAUTH_TOKEN` secret remains provisioned but inert
without the workflow file. No branch protection rules reference `claude-review`
as a required check (per the issue, which makes no mention of requiring the
check), so removing the file does not break any merge gates.
