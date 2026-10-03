# Design: issue-410-implementer-admission-must-reject-accept

## Current state

**Selection.** `orchestrator/run_implementer.py:find_accepted_proposals()`
(line 1104) walks `platform-gitops/agents-state/<service>/proposals/*/`,
parses `.status.yaml`, and returns a `ProposalRef` for every entry whose
`status` is in `{"accepted"}`. It carries exactly two facts forward: `status`
and `approval_ok` (`proposal_state.human_approval_satisfied(data)`). The rest
of the parsed document — including the `source:` block — is discarded.

**Admission today.** `implement_one()` (line 2534) gates in this order:

1. `ref.status != "accepted"` -> skip.
2. `not ref.approval_ok` -> `_mark_blocked(code=BLOCKED_APPROVAL_MISSING)`,
   `counts_toward_limit=False`, status stays `accepted` (gitops#986,
   mctl-agents#349).
3. `--dry-run` -> return early.
4. `_preflight_existing_result(ref)` (line 2252) — `gh pr list --head
   feat/agents-<slug>`, then `gh api repos/<repo>/commits/<branch>` and a
   `compare/main...<sha>`. Returns `open` / `merged` / `closed` /
   `branch-ready` / `needs-triage` / `none`. Each non-`none` action is adopted
   into a durable status write and returns without a model call.
5. `ensure_auth_for_sdk()`, `_resolve_attempt_id()`, `_acquire_claim(...)`
   (ADR-010 phase 2, #352), `update_status_yaml(ref, "in-progress", attempt=…)`.
6. Clone (`_clone_target`), branch, `_stage_implementer_agent`,
   `_build_prompt`, and the SDK run.

Nothing between steps 1 and 5 reads GitHub about the **issue**. The only place
the proposal's origin is used at all is `_issue_closing_line()` (line 2132),
which reads `source.repo` / `source.issue` purely to append `Closes <repo>#<N>`
to the PR body, and `_approval_blocked_message()` (line 2158), which reuses the
same block to name a possible DevLoopWorkflow. That `source` block is written
once by `run_issue_investigator.write_status_yaml()` (line 1043) as
`{type: github_issue, repo, issue, url}` and preserved by every later write
because `proposal_state.update_status_file()` merges rather than replaces.

**The knowledge already exists — one tier away.** `run_shepherd.py:1272`
defines `_source_issue_state(status_data) -> SourceIssueVerdict`: it reads the
same `source` block, calls `_gh_api_json(["repos/<repo>/issues/<N>"])`, and
returns either `_SOURCE_UNKNOWN` (no block, partial block, or GitHub
unreadable), `_SOURCE_ISSUE_OPEN`, or a failure dict with code
`source-resolved` (closed/completed or reason absent) or `source-not-planned`
(`state_reason == "not_planned"`). ADR-005
(`docs/adr/005-temporal-reconcile.md`, the "`failure.code` when there is no PR"
table) specifies exactly these codes. But the only call site is
`run_shepherd.reconcile_one` at line 3055 — reached *after* reconcile has
established that no PR exists for the slug, i.e. long after the implementer
would already have burned its attempt.

**Status vocabulary.** ADR-005 line 79: only `merged` and `rejected` are
genuinely terminal; `needs-triage` parks a proposal at a human gate and is
re-openable by reconcile if a live PR appears. `find_accepted_proposals` only
selects `accepted`, so a `needs-triage` write removes the proposal from the
Tier 2 queue immediately, which is the behaviour this gate needs.

**Batch accounting.** `_implement_refs()` (line 2942) increments `handled` only
when `result.counts_toward_limit`, and `--max-proposals` is forced to 1 for
executable runs (`_max_proposals_error`). A result carrying `error` makes
`_batch_outcome` count a failure and `main()` exit 1 — which is precisely what
the existing preflight `needs-triage` arm (line 2623) already does.

**DevLoop.** `orchestrator/temporal/workflows/dev_loop.py:884` runs
investigate -> `workflow.wait_condition(lambda: self._approved)` -> (patched
`slug-scoped-implement`) `find_proposal_slug` -> (patched `atomic-approve`)
`mctl-agents-approve` CWFT -> `_implement(...)`, which submits
`cwft-mctl-agents-implement.yaml` -> `run_implementer.py --service … --slug …`.
The durable wait is unbounded, so the issue can be closed while the loop is
parked. Every behaviour change inside `run()` in this file is guarded by
`workflow.patched(...)` because replay of a pre-change history through new
commands is a nondeterminism error.

**Activity precedent for issue reads.** `orchestrator/temporal/activities/
proposals.py` (`find_proposal_slug`) and `pr_state.py` (`get_pr_state`) show the
worker-side pattern: `_resolve_token()` from `GITHUB_TOKEN_FILE`/`GITHUB_TOKEN`,
`httpx.AsyncClient`, a dedicated retryable exception for transport/non-404
failures, and no gitops clone on the worker pod.

## Proposed solution

### 1. Extract the source-issue verdict into a shared module

New `orchestrator/source_issue.py`, depending only on `json`, `subprocess` and
`orchestrator.proc.run_capturing` — deliberately importing neither
`run_shepherd` (heavy, and `pr_adoption` already imports it, so an import from
`run_implementer` would build a cycle) nor `run_implementer`.

```python
@dataclass(frozen=True)
class SourceIssueVerdict:
    known: bool                      # GitHub answered about a real source link
    failure: dict[str, str] | None   # populated only for a closed issue
    linked: bool = True              # False => .status.yaml carries no usable source block
    issue_ref: str | None = None     # "mctlhq/mctl-telegram#510"
    closed_at: str | None = None
    state_reason: str | None = None
```

`read_source_issue(status_data, *, stage: str) -> SourceIssueVerdict` keeps the
body of today's `run_shepherd._source_issue_state` verbatim in behaviour, with
two additions:

- The **third** outcome the implementer needs. Today `known=False` folds
  together "this proposal has no `source:` link" and "GitHub did not answer".
  The shepherd treats both as "change nothing" and is right to, but the
  implementer must treat them oppositely: *no link* -> admit and run; *GitHub
  unreadable* -> do not run and do not write. The new `linked` flag carries that
  distinction; `known`/`failure` keep their existing meaning and the shepherd's
  two call-site branches are untouched.
- `stage` is threaded into the emitted `failure.stage` (`"reconcile"` for the
  shepherd, `"admission"` for the implementer) so triage can tell which
  controller refused.

`run_shepherd._source_issue_state` becomes a thin wrapper
(`read_source_issue(data, stage="reconcile")`) so its existing tests and its
`ref.status == "needs-triage" and existing_failure and not source.known`
preservation branch keep passing unchanged.

### 2. Gate admission in `implement_one`, after the result preflight

The check is inserted in exactly one place: immediately after the
`existing.action == "needs-triage"` branch and before `ensure_auth_for_sdk()` —
i.e. only on the `existing.action == "none"` path.

Position matters in both directions:

- **After the preflight**, because a merged PR must win. A proposal that the
  implementer already carried to a merged PR *has* a closed source issue (the
  PR body says `Closes <repo>#<N>`). Gating before the preflight would label
  that proposal stale on the next tick and destroy the `merged` projection.
  With the gate on the `none` arm only, "no branch, no PR, issue closed" is the
  sole shape it can fire on — which is exactly the shape both reproductions had.
- **Before auth, claim and `in-progress`**, because the point is to spend
  nothing: no SDK auth, no `ExecutionClaim` acquire, no `attempt` lease, no
  clone.

```python
verdict = read_source_issue(_load_status(ref.status_path), stage="admission")
if verdict.linked and not verdict.known:
    # GitHub did not answer. Not evidence about the proposal (the same rule
    # the shepherd's _SOURCE_UNKNOWN guard states). Leave it accepted.
    return ImplementResult(ref=ref, pr_url=None,
                           skipped_reason="source issue unreadable; deferring",
                           counts_toward_limit=False)
if verdict.failure:
    message = _stale_source_message(ref, verdict)   # + supersession evidence
    recorded = _mark_needs_triage(ref, code=verdict.failure["code"],
                                  stage="admission", message=message)
    return ImplementResult(ref=ref, pr_url=None,
                           error=_triage_error(message, recorded),
                           counts_toward_limit=False)
```

`_mark_needs_triage` is called with no `attempt` and no `claim_context`, so its
compare-and-swap arm is not engaged — correct, because no attempt was ever
stamped, and it mirrors how `_mark_blocked` writes without a claim on the
approval path. `counts_toward_limit=False` keeps one stale proposal from
consuming the single-proposal batch budget and starving a healthy one behind
it. `_triage_error` annotates the message when the write did not land.

`--dry-run` returns before the preflight today, so the gate is never reached in
dry-run and nothing is written; the summary line for a dry run still lists the
proposal as `skip: dry-run`, unchanged.

### 3. Supersession evidence (the issue's stretch item)

`_stale_source_message()` composes the human-readable refusal:

```
source issue mctlhq/mctl-telegram#510 is closed as completed
(closed 2026-09-06T…Z); admission refused before any model attempt.
Superseded by: https://github.com/mctlhq/mctl-telegram/pull/540.
Reopen the issue, or re-publish this proposal as 'proposed', to make it
runnable again.
```

The supersession line comes from one extra, best-effort GitHub call, only on the
closed-as-**completed** arm (never on `not_planned`, where there is nothing to
supersede): `gh api repos/<repo>/issues/<N>/timeline` filtered to
`cross-referenced` events whose `source.issue.pull_request.merged_at` is set,
plus `closed` events carrying a `commit_id`. Up to three URLs, newest first. Any
failure or empty result drops the sentence and never changes the verdict —
diagnostics, never a gate. This is the honest version of the issue's "lightweight
signal": it detects supersession *as GitHub already recorded it*, instead of
guessing from keywords.

### 4. DevLoop pre-approve check

A new activity `orchestrator/temporal/activities/issue_state.py:get_issue_state(
repo, issue_number) -> IssueState(state, state_reason, closed_at)` built on the
same `_resolve_token()` + `httpx` + `ProposalListingError`-style retryable
failure pattern as `proposals.py`/`pr_state.py`, registered in
`orchestrator/temporal/worker.py` beside the existing activities.

In `DevLoopWorkflow.run`, immediately after
`await workflow.wait_condition(lambda: self._approved)` and guarded by
`workflow.patched("stale-issue-admission")`:

- call `get_issue_state` for `parse_issue_url(issue.issue_url)`;
- if the issue is closed, return
  `DevLoopResult(investigate=investigate_result, implement=None, approve=None)`
  with the skip reason recorded on the result, *before* the approve CWFT and
  before `find_proposal_slug` — so the loop does not flip a proposal to
  `accepted` it will never implement;
- if the activity fails after its retries, proceed (fail-open on the workflow
  side): the implementer's own gate is the authoritative one, and wedging every
  loop on a GitHub blip is worse than one refused implement step.

Old histories take the unpatched branch and replay unchanged, the same
convention `slug-scoped-implement`, `atomic-approve`, `merge-detection` and
`deploy-observation` already follow in this file.

### 5. Observability

- Batch summary gains a `=== Stale source ===` section listing
  `service/slug: <code> <issue-ref>`, printed from `main()` beside the existing
  `=== Blocked ===` block.
- The refusal is durable in `.status.yaml` (`failure.code`, `failure.stage:
  admission`, `notes`), so `mctl_trigger_reconcile` and the mentor digest see it
  with no extra plumbing.

## Alternatives

**A. New terminal `stale` status, written by the implementer.** The issue floats
it. Dropped: ADR-005 is explicit that only `merged` and `rejected` survive
reconcile and that retiring a proposal is an operator decision ("the loop makes
the reason legible, it does not write the terminal"). A new state would need
matching arms in `run_shepherd.reconcile_one`, the reconcile workflow's
projection table, and every consumer that enumerates statuses — a large blast
radius to express something `needs-triage` + `failure.code` already expresses,
using codes #276 already minted.

**B. Filter at selection time in `find_accepted_proposals`.** Cheapest to write:
drop stale proposals from the returned list. Dropped: selection is pure,
filesystem-only and synchronous, and is also used by the `--review-feedback`
path with a different status set; putting a network call in it makes discovery
fail whenever GitHub hiccups, and a silently filtered proposal leaves no record
of *why* it was not attempted — the opposite of what the issue asks for.

**C. Gate before `_preflight_existing_result`.** Marginally cheaper (skips the
PR queries on stale proposals). Dropped because it inverts the precedence
between two truths: a merged PR is a fact about *this proposal*, a closed issue
is a fact about its *origin*, and the first must win. Gating first would flip
already-`merged`/`implemented`-adoptable proposals into `needs-triage` on any
tick that re-selected them.

**D. Content heuristic on the target branch (keyword/path scan).** The issue's
stretch, taken literally. Dropped as the primary mechanism: it requires the
clone that admission exists to avoid, and a false positive silently discards
real work. The GitHub-recorded supersession links in §3 give the same signal for
the reported case (`#510` -> `#540`) at the cost of one API call and with no
guessing.

## Platform impact

- **Migrations:** none. No schema change to `.status.yaml`; `failure.code`
  values `source-resolved` / `source-not-planned` are already defined by ADR-005
  and already produced by the shepherd. The only new value is `failure.stage:
  admission`, and `stage` is a free-text field today.
- **Backward compatibility:** proposals with no `source` block (incident
  responder, service agents) are admitted unchanged — the `linked=False` arm.
  `run_shepherd._source_issue_state` keeps its signature and both of its
  `known`-based call-site branches. DevLoop histories recorded before this change
  replay on the unpatched branch.
- **Resource impact:** one `gh api repos/<repo>/issues/<N>` per accepted proposal
  that reaches the `existing.action == "none"` arm — at most one per implementer
  tick, since executable runs are capped at one proposal. One additional timeline
  call only on the closed-as-completed arm. Negligible against the rate limit;
  strictly cheaper than the model attempt it replaces.
- **Risks and mitigations:**
  - *Wrongly refusing live work* — an issue closed by a maintainer while the
    proposal is genuinely still wanted. Mitigated by: the refusal is
    `needs-triage`, not terminal; the note names the exact reopen/re-publish
    recovery; and reconcile still re-opens the proposal to `implemented` if a
    live PR later turns up.
  - *GitHub outage retiring the queue* — mitigated by the explicit
    `linked and not known` arm, which writes nothing and leaves the proposal
    `accepted`; this is the same failure mode agy's P1 on PR #279 caught in the
    shepherd, which is why `known` and `failure` are two fields and not one.
  - *Red Argo runs* — a refusal exits 1, like the existing preflight triage arm.
    It fires at most once per proposal, because the same tick moves it out of
    `accepted`. Recorded as an open question in `requirements.md` in case
    operators prefer a dedicated exit code.
  - *Timeline call cost/noise* — bounded to three URLs, best-effort, never
    affects the verdict.
  - *DevLoop nondeterminism* — every new command sits behind
    `workflow.patched("stale-issue-admission")`, and
    `tests/test_workflow_replay.py` / `tests/replay_scenarios.py` cover replay of
    recorded histories.
