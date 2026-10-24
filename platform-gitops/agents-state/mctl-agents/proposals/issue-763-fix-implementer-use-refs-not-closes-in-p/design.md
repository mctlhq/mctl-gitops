# Design: issue-763-fix-implementer-use-refs-not-closes-in-p

## Current state
- `orchestrator/run_implementer.py:_issue_closing_line(ref)` (around line 3557)
  reads `.status.yaml` via `_load_status(ref.status_path)`, and for a
  `source: {type: github_issue, repo, issue}` block returns
  `"\n\nCloses {repo}#{issue}"`; otherwise `""`.
- `_pr_title_and_body(ref, typecheck)` (around line 3670) appends that line
  unconditionally to the body. It is a pure function today: no network I/O.
- `_open_pr_for_branch(ref, branch, typecheck)` (around line 3742) is the only
  `gh pr create` call site. It is reached from two paths: the normal post-model
  path (around line 4421) and `_preflight_existing_result` for an orphaned result
  branch (around line 3854). Title/body are also digested into the policy
  checkpoint record (`policy_checkpoint.GITHUB_PR_CREATE`).
- `orchestrator/source_issue.py:read_source_issue` already fetches
  `repos/{repo}/issues/{number}` for the admission gate (called around line 4744
  with `stage="admission"` and the bounded `_gh_api_json` adapter at line 1766),
  but `SourceIssueVerdict` keeps only state/closed_at/state_reason, not the title.
- `_gh_api_json` -> `_github_json` is the bounded, logged, token-refreshing `gh`
  path every implementer GitHub read is supposed to use; it raises
  `GitHubPreflightError` on failure or bad JSON.
- Nothing in `orchestrator/` reads `roadmap/spikes/` or knows about spikes today
  (grep for `spike` only hits `orchestrator/sdd/` docstrings).
- The implementer agent prompt (`agents/`) contains no closing keyword guidance;
  the shepherd merges with `gh pr merge --merge` (`run_shepherd.py` around line
  3608), so the PR body is the only place a closing keyword enters.
- Existing tests: `tests/test_run_issue_investigator.py` lines 465-509 import
  `_issue_closing_line` and assert the `Closes` string;
  `tests/test_github_mutations_policy.py:test_pr_create_allowed_runs` calls
  `_open_pr_for_branch` and `_pr_title_and_body` with a fake `_run`.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  the implementer runs with a GitHub token mounted from a Secret file
  (`github-token-file`, refreshed by `orchestrator/github_token.py`). The file
  does not state which repositories the installation token covers, so read
  access to `mctlhq/.github` is NOT confirmed (recorded under Open questions).
- `$MCTL_GITOPS_ROOT/services/admins/`: lists `mctl-agents-worker`,
  `mctl-agents-worker-exec`, `mctl-agents-worker-implement`; no config change is
  needed there for this proposal.
- The SpikeDefinition manifests in `mctlhq/.github` were not readable from this
  run; their `spec.github.issue` shape is unverified.
- mctl MCP tools were not used; nothing about deployed runtime behaviour is
  asserted beyond the files above.

## Proposed solution
1. New module `orchestrator/spike_issue.py` (depends only on `json`, `yaml`,
   `base64` and a caller-supplied `gh_api_json`, like `source_issue.py`, to avoid
   import cycles):
   - `SPIKE_TITLE_RE = re.compile(r"^\s*spike\s*[(:]", re.IGNORECASE)`.
   - `@dataclass(frozen=True) class SpikeClassification: outcome: str` (one of
     `spike-title`, `spike-manifest`, `not-spike`, `observation-error`),
     `detail: str | None`, and property `is_spike_or_unknown` (true for every
     outcome except `not-spike`).
   - `classify_issue(repo, number, *, gh_api_json) -> SpikeClassification`:
     a. Fetch `repos/{repo}/issues/{number}`; on exception or a payload without a
        string `title` -> `observation-error` (step `issue-read`).
     b. Title matches `SPIKE_TITLE_RE` -> `spike-title` (no manifest lookup).
     c. List `repos/mctlhq/.github/contents/roadmap/spikes`; on error or a
        non-list payload -> `observation-error` (step `spike-list`). A genuine 404
        for the directory is also an observation error, not "no spikes" (fail safe).
     d. For each `*.yaml`/`*.yml` entry, fetch the file contents (base64 `content`),
        `yaml.safe_load`, read `spec.github.issue`. Any fetch/decode/parse failure
        -> `observation-error` (step `spike-manifest:<name>`), after which the loop
        stops. Normalise the binding with `_parse_issue_binding(value)` accepting
        `owner/repo#N`, `N` / `#N` (repo defaults to `mctlhq/.github`), or a
        mapping with `repo` and `number`/`issue`; a manifest without a binding is
        skipped (it binds nothing). Comparison is case-insensitive on repo and
        integer on number.
     e. Match -> `spike-manifest`; no match -> `not-spike`.
2. `run_implementer.py`:
   - Replace `_issue_closing_line(ref)` with `_issue_reference_line(ref)` that
     keeps the same `source` validation, calls
     `spike_issue.classify_issue(repo, int(issue), gh_api_json=_gh_api_json)`,
     prints `spike-classification: issue=<repo>#<N> outcome=<o> keyword=<Refs|Closes>
     [detail=...]`, and returns `\n\nRefs {repo}#{issue}` unless outcome is
     `not-spike`, in which case `\n\nCloses {repo}#{issue}`. Keep
     `_issue_closing_line` as an alias for one release so the investigator test
     import does not break, or update that test (task 4).
   - `_pr_title_and_body` uses `_issue_reference_line`. Because it now performs
     I/O, `_open_pr_for_branch` computes the body once and the policy checkpoint
     digests that same body (already the case: the body is built once there).
     The classification happens immediately before PR creation, so the lookup is
     performed only when a PR is actually opened, not on every tick.
3. The `observation-error` outcome is reported on the log line with a stable
   prefix so it is greppable in the workflow log archive; no new metric or
   incident is created (out of scope, see Alternatives).

Why here: `_pr_title_and_body` is the single choke point for both PR-opening
paths, so one decision covers the main and preflight paths. Reading the issue
title at PR time (rather than at investigation time) also catches a title edited
to `spike:` after the proposal was written.

## Alternatives
- Record `is_spike` in `.status.yaml` at investigation time: avoids network I/O
  at PR time, but needs a schema change in the investigator, is stale if the
  issue is retitled or a SpikeDefinition is added later, and gives existing
  proposals no value. Dropped.
- Extend `SourceIssueVerdict` with `title` and reuse the admission-gate read:
  saves one API call, but the admission gate runs before the model attempt
  (minutes earlier) and does not run on the preflight PR path, so the title
  would need to be threaded through `ImplementResult`/`ref`. More coupling for a
  single cheap GET. Dropped; can be revisited.
- Never emit a closing keyword (always `Refs`): simplest and safest, but removes
  auto-close for all normal DevLoop work and contradicts the regression
  criterion. Dropped.
- Use GitHub code search for `spec.github.issue` instead of listing the
  directory: code search is eventually consistent and rate-limited; a stale index
  would be read as "not a spike". Dropped.

## Platform impact
- No migration, no schema change. Existing open PRs keep their bodies.
- Extra GitHub API calls only when a PR is opened: 1 issue GET plus 1 directory
  listing plus one GET per spike manifest (expected to be a handful). Negligible.
- Risk: the implementer token cannot read `mctlhq/.github`, so every PR gets
  `Refs` and no issue auto-closes. Mitigation: the `observation-error` log line
  names the failing step; reviewer verifies token scope before rollout; the
  first DevLoop PR after deploy should be checked for `Closes`.
- Risk: an unexpected `spec.github.issue` shape makes a real spike look unbound
  (`not-spike` -> `Closes`). Mitigation: unparseable non-empty bindings are an
  observation error (fail to `Refs`), not a skip; only an absent binding is
  skipped.
- `_pr_title_and_body` stops being pure; tests that call it must patch
  `spike_issue.classify_issue` or `_gh_api_json`.
- Backward compatible for proposals without a `source` block.
