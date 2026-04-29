# Design — Tier 3 PR shepherd

## Architecture
A new orchestrator module `orchestrator/run_shepherd.py` mirrors the
shape of `orchestrator/run_implementer.py`:

- Plain Python entrypoint, runnable as `python -m orchestrator.run_shepherd`.
- Reads `STATE_DIR` (the workflow PVC mounts the gitops worktree there).
- Iterates proposals under `<state>/<svc>/proposals/<slug>/.status.yaml`,
  filters to `status == implemented`.
- For each, fetches PR metadata via `gh api` and runs the decision
  state-machine (see below).
- Writes new state back to the SAME `.status.yaml` on the worktree;
  the surrounding Argo workflow's `commit-and-push` step pushes the
  diff to mctl-gitops main (existing CWFT pattern).

The Claude SDK is used for one specific decision: parsing the codex
findings into "merge-ready vs. needs-fix" and shaping the followup
prompt for the implementer when needed. This keeps the shepherd's
deterministic logic in Python and the language-y judgement in the
agent prompt — same split as Tier 2.

## State machine
```
                            (cron tick)
                                │
                                ▼
                       read .status.yaml
                                │
                ┌───────────────┴────────────────┐
                ▼                                ▼
         status=implemented              status=review-fixing
                │                                │
       ┌────────┼────────┐                       │
       ▼        ▼        ▼                       ▼
     wait   address-   merge       previous followup commit landed?
             review                         │
       │        │        │             ┌────┴────┐
       │        ▼        │             ▼         ▼
       │  flip to      gh pr        yes      no (still pending)
       │  review-     merge          │         │
       │  fixing,       │            ▼         └─► leave as-is
       │  invoke      flip to      flip to
       │  Tier 2      merged       implemented
       │  with        +            (next tick re-evaluates
       │  feedback    merge_commit  with fresh review)
       │
       └─► (no-op, exit clean)
```

Terminal states for the shepherd's purposes:
- `merged` — done, proposal succeeded.
- `rejected` — PR was closed without merging (human override).

The shepherd never overwrites `merged` or `rejected` once set.

## Decision logic — `decide(pr, codex_review)`
```python
if pr.merged:
    return ("flip-to-merged", pr.merge_commit)
if pr.closed_unmerged:
    return ("flip-to-rejected", pr.close_comment_or_default)
if not codex_review.has_responded:
    return ("wait", None)            # codex still parsing the PR
findings = codex_review.findings_p1_p2()
if findings:
    return ("address-review", findings)
if not pr.checks_green:
    return ("wait", None)            # CI not done yet
return ("merge", None)
```

Notes:
- `codex_review.has_responded` is true if either a review with state
  `COMMENTED` exists for the latest commit, or codex has posted a
  top-level issue comment matching `Didn't find any major issues`,
  or codex reacted `+1` to the trigger comment. (The codex-watch
  shell skill already encodes this; the shepherd reuses the GitHub
  API queries.)
- P3 findings are intentionally ignored — they are nits and the
  shepherd will not loop the implementer for them. Humans can still
  push fixes manually if they care.
- `checks_green` requires the `mergeStateStatus == CLEAN` and all
  required checks `SUCCESS`.

## Address-review followup
When findings exist, the shepherd:
1. Builds a plain-text bundle of the unresolved P1/P2 findings (path,
   line, body).
2. Invokes the Tier 2 implementer via `subprocess` with `--service`,
   `--slug`, and a new `--review-feedback /path/to/bundle.txt` flag
   added to `run_implementer.py` in this same PR.
3. The implementer's existing sub-agent receives the bundle as
   additional context and pushes a follow-up commit to the existing
   branch (no new branch — the implementer detects an existing
   `feat/agents-<slug>` branch on origin and rebases/checkouts it).

After the followup completes, the shepherd flips `.status.yaml` back
to `status: implemented` so the next cron tick re-evaluates the same
PR — typically by the time the next tick runs, codex has re-reviewed
the new commit.

To prevent infinite loops on a stubborn finding, the shepherd
records a `review_attempts` counter on the proposal's `.status.yaml`
and gives up at 3 attempts (transitions to `status: review-stuck`,
which is a terminal state pending human triage).

## Sub-agent prompt
A new prompt file `agents/_shepherd/shepherd.md` defines the
sub-agent role used when the shepherd needs the SDK to parse a
review finding or shape an implementer prompt. Kept tight (≈300
words) — the shepherd is mostly deterministic Python; the SDK is
only there to translate codex bodies into "is this a real issue or
a nit?" and to author the followup prompt body.

## Cron + workflow
A new ClusterWorkflowTemplate `mctl-agents-shepherd` mirrors
`cwft-mctl-agents-implement.yaml`:
- volumeClaimTemplate workdir 4Gi
- shared mutex `mctl-gitops-main-writes`
- secrets: `claude-code-oauth-token`, `github-token`
- runs `python -m orchestrator.run_shepherd`
- onExit: telegram notify (same shape as run + implement)

A new CronWorkflow `mctl-agents-shepherd-cron` runs at `*/5 * * * *`
with `concurrencyPolicy: Forbid` so two ticks never overlap.

The CWFT + cron are NOT part of this PR — they are added in a
follow-up gitops PR after the orchestrator code lands and is tagged.
This proposal is scoped to the mctl-agents repo only.

## Tests
- `tests/test_run_shepherd.py` — unit tests for `decide()` covering
  every branch with hand-built `pr` and `codex_review` fixtures.
- `tests/test_run_shepherd.py::test_state_transitions` — drives the
  full state machine on a temp worktree fixture.
- No integration tests — actual GitHub API and Claude SDK are
  mocked at the boundary (existing fixtures in tests/conftest.py).

## Risk
- Cost: each tick does ~1 SDK invocation per non-empty proposal. With
  budget cap `$1.00 / tick` and 12 ticks / hour, worst case ~$12 / hour
  if every proposal is in the review-loop. In practice, most ticks
  find nothing to do and exit free.
- Race with humans: if a human is mid-merging a PR, the shepherd may
  observe the post-merge state on the next tick and flip status
  cleanly — no harm. The shepherd never reverts a human merge.
- Race with itself: `concurrencyPolicy: Forbid` on the cron means at
  most one tick runs at a time. Mutex on gitops main pushes already
  exists. No new locking needed.
