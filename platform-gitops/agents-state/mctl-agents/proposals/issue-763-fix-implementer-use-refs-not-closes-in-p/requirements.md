# Implementer PRs reference spike issues with `Refs`, not `Closes`

## Context
The Tier 2 implementer (`orchestrator/run_implementer.py`) builds every PR body in
`_pr_title_and_body`, which unconditionally appends the line produced by
`_issue_closing_line`: `Closes <repo>#<N>` for any proposal whose `.status.yaml`
carries a `source: {type: github_issue}` block. GitHub then auto-closes the source
issue when the PR merges. For a spike issue that is wrong: the research PR only
recommends an outcome, and the spike is supposed to stay open until its owner
records `decision.verdict` in the SpikeDefinition manifest and closes it by hand.
On 2026-10-23 mctlhq/.github#213 merged and auto-closed the spike
mctlhq/.github#209 while `roadmap/spikes/security-finding-lifecycle.yaml` was
still `lifecycle: active`; it had to be reopened manually.

The issue asks the implementer to emit `Refs <repo>#<N>` instead of `Closes` when
the source issue is a spike, identified either by its title (`spike(` / `spike:`
prefix) or by a SpikeDefinition in `mctlhq/.github` `roadmap/spikes/*.yaml` whose
`spec.github.issue` binds it. When spike status cannot be determined, the
implementer must fail safe to `Refs` and report the failure as an observation
error.

## User stories
- AS a spike owner I WANT the research PR to leave my spike issue open SO THAT I
  can record the verdict in the SpikeDefinition before the issue closes.
- AS a roadmap operator I WANT spike issues and their manifests to stay consistent
  SO THAT the Roadmap Control Plane does not see a closed issue bound to an
  `active` spike with no decision.
- AS a maintainer of ordinary DevLoop work I WANT non-spike issues to keep
  auto-closing on merge SO THAT this fix does not create manual cleanup elsewhere.

## Acceptance criteria (EARS)
- WHEN the implementer builds a PR body for a proposal whose source issue title,
  after stripping leading whitespace and compared case-insensitively, starts with
  `spike(` or `spike:` THE SYSTEM SHALL end the body with `Refs <repo>#<N>` and
  SHALL NOT include any GitHub closing keyword (close, closes, closed, fix, fixes,
  fixed, resolve, resolves, resolved) followed by an issue reference.
- WHEN the source issue is named by the `spec.github.issue` field of any
  SpikeDefinition under `mctlhq/.github` `roadmap/spikes/*.yaml` THE SYSTEM SHALL
  use `Refs <repo>#<N>`, whatever the issue title.
- WHEN the source issue title is not spike-prefixed AND the SpikeDefinition lookup
  completed successfully AND no SpikeDefinition binds the issue THE SYSTEM SHALL
  keep emitting `Closes <repo>#<N>` exactly as today.
- IF the source issue title cannot be read, or the SpikeDefinition listing, any
  manifest fetch, or any manifest parse fails THEN THE SYSTEM SHALL emit
  `Refs <repo>#<N>`, SHALL log one `spike-classification: observation-error`
  line naming the issue and the failing step, and SHALL NOT treat the failure as
  "not a spike".
- WHEN the title alone already classifies the issue as a spike THE SYSTEM SHALL
  NOT require the SpikeDefinition lookup to succeed.
- WHILE a proposal has no usable `source` block THE SYSTEM SHALL emit no issue
  reference line at all (unchanged behaviour).
- WHEN the same proposal's PR is opened from the preflight path for an orphaned
  result branch (`_preflight_existing_result` -> `_open_pr_for_branch`) THE SYSTEM
  SHALL apply the same classification as the main path.
- THE SYSTEM SHALL log one `spike-classification:` line per PR body built, stating
  the issue, the outcome (`spike-title`, `spike-manifest`, `not-spike`,
  `observation-error`) and the keyword chosen.

## Out of scope
- Closing spike issues automatically after a verdict is recorded; the owner closes
  them by hand.
- Slice issues that must not close a parent epic (mentioned in the issue via
  #759 / #746). They are not spikes; the proposal does not add a parent/slice
  rule. A follow-up can reuse the same `Refs` decision point.
- Rewriting PR bodies of PRs that are already open or merged.
- Changing the shepherd's merge method or commit messages (the shepherd merges
  with `gh pr merge --merge`, whose merge commit does not carry the PR body).
- Changing the issue-investigator, the DevLoop Temporal workflow, or `.status.yaml`
  schema.

## Open questions
- The exact shape of `spec.github.issue` in a SpikeDefinition was not observable
  from this clone (the manifests live in `mctlhq/.github`). The design accepts an
  `owner/repo#N` string, a bare integer or `#N` (meaning an issue in
  `mctlhq/.github`), and a `{repo, number}` mapping; the implementer must confirm
  against a real manifest such as `roadmap/spikes/security-finding-lifecycle.yaml`.
- Whether the implementer's GitHub App installation token can read
  `mctlhq/.github` contents was not verified. If it cannot, every lookup fails
  and every DevLoop PR would fall back to `Refs` (no issue would auto-close).
  The observation-error log line makes this visible; the reviewer should confirm
  the token's repository access before merge.
