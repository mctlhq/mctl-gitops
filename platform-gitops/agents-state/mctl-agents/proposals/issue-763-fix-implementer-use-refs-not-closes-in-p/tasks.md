# Tasks: issue-763-fix-implementer-use-refs-not-closes-in-p

- [ ] 1. Add `orchestrator/spike_issue.py` with `SPIKE_TITLE_RE`,
  `SpikeClassification`, `_parse_issue_binding`, and
  `classify_issue(repo, number, *, gh_api_json)` as described in design.md — DoD:
  module imports nothing from `run_implementer`/`run_shepherd`; every failure path
  returns `observation-error` with a step-specific `detail`; an absent binding is
  skipped, an unparseable present binding is an observation error.
- [ ] 2. (depends on 1) In `orchestrator/run_implementer.py`, add
  `_issue_reference_line(ref)` that validates the `source` block as
  `_issue_closing_line` does, calls `spike_issue.classify_issue` with the bounded
  `_gh_api_json`, logs the `spike-classification:` line, and returns `Refs` unless
  the outcome is `not-spike` — DoD: `_pr_title_and_body` uses it; no other code
  path emits a closing keyword.
- [ ] 3. (depends on 2) Remove `_issue_closing_line` (or keep it as a thin alias
  that delegates, documented as deprecated) and update its docstring references in
  `_approval_blocked_message` and the admission-gate comment near line 4737 — DoD:
  comments no longer claim the body always says `Closes`.
- [ ] 4. (depends on 2) Update `tests/test_run_issue_investigator.py` (lines
  465-509) and `tests/test_github_mutations_policy.py` so they patch the
  classifier; move the reference-line tests into a new
  `tests/test_spike_issue.py` / `tests/test_run_implementer_issue_reference.py` —
  DoD: full `pytest` passes.


## Amendments (2026-10-24, reviewer) — these override the rest of this file

- Task 1 DoD: `_parse_issue_binding` accepts only `{repository, number}`
  (design A1/A2). An absent `spec.github.issue` is an `observation-error`, not
  a skip.
- **T4 replaced:** non-spike title, and the listing returns the verbatim
  `security-finding-lifecycle.yaml` fixture (bound to `mctlhq/.github#209`)
  for source issue `mctlhq/.github#209`. Expect `Refs` and outcome
  `spike-manifest`. Repeat with `MCTLHQ/.GITHUB` as the source repo to cover
  case-insensitivity.
- **T11 (new, regression on real data):** non-spike title for
  `mctlhq/mctl-agents#763`, and the listing returns the verbatim fixtures
  (none bind #763). Expect `Closes mctlhq/mctl-agents#763` and outcome
  `not-spike`. Mutation check: restore the original string-only parser or the
  "unparseable present binding" path, and T11 must fail.
- **T12 (new):** a manifest whose `spec.github.issue` is
  `"mctlhq/.github#209"` (string), `209` (int), `{repo: ..., number: 209}`, or
  is missing. Each gives `Refs` and `observation-error` with
  `step=spike-manifest:<name>`.
- **T13 (new):** `number: true` and `number: 0` give `observation-error`.
- **Post-deploy verification (DoD for the release, recorded on the issue):**
  the first DevLoop PR opened after the release for a non-spike issue carries
  `Closes`, and its workflow log shows
  `spike-classification: ... outcome=not-spike`. If it shows
  `outcome=observation-error step=spike-list`, the token cannot read
  `mctlhq/.github`: revert the release.

## Tests
- [ ] T1. Spike title `spike(security): finding lifecycle` -> body ends with
  `Refs mctlhq/.github#209`; assert no closing keyword regex
  `(?i)\b(close[sd]?|fix(e[sd])?|resolve[sd]?)\s+\S*#\d+` matches; assert the
  SpikeDefinition listing was never requested.
- [ ] T2. `spike: ...` and `  SPIKE(x): ...` titles also classify as `spike-title`;
  `spikes in latency` and `fix: spike handling` do NOT.
- [ ] T3. Non-spike title, listing returns manifests none of which bind the issue
  -> `Closes <repo>#<N>` (regression).
- [ ] T4. Non-spike title, a manifest with `spec.github.issue` bound to the issue
  (each accepted shape: `mctlhq/.github#209`, `209`, `#209`,
  `{repo: mctlhq/.github, number: 209}`) -> `Refs`.
- [ ] T5. Issue GET raises -> `Refs`, outcome `observation-error`, log line
  contains `step=issue-read`.
- [ ] T6. Directory listing raises / returns 404 / returns non-list -> `Refs`,
  `observation-error`.
- [ ] T7. One manifest fails to fetch or parse as YAML -> `Refs`,
  `observation-error` (never `not-spike`).
- [ ] T8. No `source` block -> empty reference line (unchanged).
- [ ] T9. `_preflight_existing_result` opening a PR for an orphaned branch with a
  spike-titled issue passes a body containing `Refs` to `gh pr create`.
- [ ] T10. `test_pr_create_allowed_runs` still verifies the checkpoint digest
  equals the digest of the body actually sent.

## Rollback
Revert the PR. The change is confined to PR-body text built at PR-creation time;
no state, schema, or deployed configuration changes. PRs opened while the change
was live keep `Refs`; any non-spike issue they failed to close (for example after
a lookup outage) can be closed by hand, found via the
`spike-classification: ... outcome=observation-error` log lines.
