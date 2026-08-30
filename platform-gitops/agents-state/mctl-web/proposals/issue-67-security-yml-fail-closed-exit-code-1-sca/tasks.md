# Tasks: issue-67-security-yml-fail-closed-exit-code-1-sca

- [ ] 1. Edit `.github/workflows/security.yml`: change `exit-code: "0"` to `exit-code: "1"` on
      the "Trivy filesystem scan" step, leaving `scan-type`, `scan-ref`, `severity`,
      `ignore-unfixed`, `version`, and the pinned action SHA unchanged. — DoD: the diff touches
      only the `exit-code` value; `git diff` shows a single changed line for this edit.

- [ ] 2. (depends on 1) Remove the stale three-line inline comment
      (`# Report-only: package-lock.json already has CRITICAL findings with upstream fixes
      (Nuxt DevTools, seroval). Dependabot PRs are the remediation path; this workflow exists so
      the scan runs (SOC F16).`) from the same step. Optionally replace it with a short, accurate
      one-line comment describing the current fail-closed behavior (e.g. "Fails on fixable
      CRITICAL findings; ignore-unfixed skips CVEs with no upstream fix."). — DoD: no reference
      to "Report-only", "Nuxt DevTools", or "seroval" remains in `security.yml`.

- [ ] 3. (depends on 1, 2) Branch and PR per `CLAUDE.md`'s Branch Strategy: create
      `ci/security-yml-fail-closed`, commit the change, open a PR via `gh pr create`. Per
      `CLAUDE.md`'s "Trivial changes — merge immediately" rule (config/values YAML), this PR does
      not require waiting on the Claude Opus review gate before merge, but `claude-review.yml`
      will still run automatically on PR open — let it complete or note it as non-blocking for
      this trivial change. — DoD: PR opened against `main`, branch name matches the change type
      (`ci/`), CI (`build.yml`, `worker-test.yml`, and the new fail-closed `security.yml` itself)
      passes on the PR.

- [ ] 4. (depends on 3) Merge via `gh pr merge <N> --merge --delete-branch`, matching the
      required merge-commit pattern in `CLAUDE.md`. — DoD: `main`'s history shows a merge commit
      for this PR; the feature branch is deleted.

## Tests
- [ ] T1. Before merging, confirm the current Trivy config (`v0.69.3`,
      `scan-type: fs`, `scan-ref: .`, `severity: CRITICAL`, `ignore-unfixed: true`) still reports
      zero findings against the branch's `package-lock.json` — either by observing the `trivy`
      job succeed on the PR itself (now fail-closed, so a green check is a real pass, not just an
      always-succeed no-op) or by re-running the local scan referenced in the issue
      (2026-08-27 baseline) against the current lockfile.
- [ ] T2. Confirm the `trivy` job's step logs on the PR run show the scan actually executed
      (not skipped) and completed with exit code 0, i.e. the workflow is now meaningfully
      fail-closed rather than trivially green.
- [ ] T3. Grep the final `security.yml` for "Report-only", "DevTools", and "seroval" and confirm
      zero matches, satisfying the "remove the stale comment" requirement.

## Rollback
If the fail-closed gate produces noisy or unexpected failures (e.g. a Trivy DB update surfaces a
new CRITICAL finding with no immediate fix path), revert with a follow-up PR that sets
`exit-code` back to `"0"` on the same step (same branch-and-PR flow per `CLAUDE.md` — no direct
push to `main`). This is a single-line change with no state, data, or deployed-service impact to
unwind, since the whole change is confined to `.github/workflows/security.yml`.
