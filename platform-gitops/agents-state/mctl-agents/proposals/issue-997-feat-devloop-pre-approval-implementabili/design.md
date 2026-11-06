# Design: issue-997-feat-devloop-pre-approval-implementabili

## Current state

How a proposal reaches approval and the implementer today:

- **Investigation.** `orchestrator/run_issue_investigator.py` `_investigate`
  runs the agent, which writes `requirements.md` / `design.md` / `tasks.md`
  into a staging directory. Then:
  - `_seal_draft` seals the clarification draft (step 4c);
  - `write_status_yaml` writes `status: proposed` into staging (step 5);
  - staging is swapped into place as a directory (step 6), and
    `_carry_forward` carries over any file the agent did not rewrite;
  - `post_proposal_comment` posts the "pending human approval" comment on the
    issue (step 7). The comment is passed through `policy_checkpoint.require`
    and `gh issue comment`.

  Nothing evaluates whether the tasks can be executed. `_build_prompt` only
  asks for the triplet format.
- **Content digest.** `orchestrator/proposal_state.py`:
  - `PROPOSAL_DIGEST_FILES = ("requirements.md", "design.md", "tasks.md", "proposed-content.md")`;
  - `content_digest_of(files)` is the shared, length-prefixed sha256, pinned by
    `tests/test_proposal_digest.py`.
- **Approval request.** `orchestrator/temporal/workflows/dev_loop.py`:
  - `run` sets `self._canonical = workflow.patched(CANONICAL_APPROVAL_PATCH)`
    and, before the approval park, calls `_request_canonical_approval`;
  - `_request_canonical_approval` runs `find_proposal_slug`, then the
    `request_devloop_approval` activity
    (`orchestrator/temporal/activities/delegated_approval.py`);
  - that activity calls `read_proposal_content_digest` (`activities/proposals.py`),
    which reads the four files at one resolved gitops `main` commit, binds the
    digest as `artifact_hash` in `approval_intent`, and creates the `aar_` via
    `ActionApprovalClient().create`.

  The park then waits up to `CANONICAL_APPROVAL_WAIT` (7 days minus 5 minutes).
  It checks grant freshness every `GRANT_FRESHNESS_INTERVAL` (1 h) and
  supersedes the grant when the digest changes (`_superseded_refs`,
  `MAX_GRANT_SUPERSEDES = 8`). Nothing in this path considers implementability.
- **Implementer envelope.** `orchestrator/run_implementer.py`:
  - `_clone_target` clones only `mctlhq/{service}` with `--depth=10` at the
    default branch, so it has single-repository write authority and no base
    other than the default branch;
  - `agents/_manifests/implementer/agent.yaml` declares `budgetUsd: 3.00`,
    `timeoutSeconds: 900` and sandbox CWFT `mctl-agents-implement`;
  - `orchestrator/options.py` has
    `IMPLEMENTER_BUDGET_USD = float(os.getenv("IMPLEMENTER_BUDGET_USD", "3.00"))`.

  A deliberate refusal is reported through `.implementer-refusal.json`
  (`REFUSAL_MARKER_FILENAME`, `REFUSAL_ERROR_PREFIX = "deliberate no-op:"`),
  and `orchestrator/implementation_completion.py` has `OUTCOME_BOUNDED_REFUSAL`.
  These are the post-approval signals #414 owns.
- **Replay discipline.** `tests/test_workflow_replay.py` replays the
  `tests/fixtures/histories/*.json` fixtures recorded by
  `tools/record_workflow_history.py` from `tests/replay_scenarios.py`. An added
  or reordered activity in an existing history is a `NondeterminismError`, so
  any new activity must sit behind a new `workflow.patched` marker
  (`tests/test_patch_memoization.py`).

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`:
  - the DevLoop control worker runs image tag `1.117.0` with
    `command: python -m orchestrator.temporal.worker --role control`;
  - env includes `TEMPORAL_NAMESPACE: mctl-agents`,
    `MCTL_POLICY_APPROVALS: mctl-api`, `EXECUTION_REQUEST_DISPATCHER: "true"`
    and `LIFECYCLE_ROLLOUT_MODE: observe`. The last is the precedent for a
    default-`observe` rollout flag;
  - no `IMPLEMENTER_BUDGET_USD` / `IMPLEMENTER_TIMEOUT_SECONDS` override was
    found in this file.
- `$MCTL_GITOPS_ROOT/services/admins/` also contains
  `mctl-agents-worker-exec` and `mctl-agents-worker-implement`. Their env was
  not read in this run. Whether the implement worker or the
  `mctl-agents-implement` CWFT overrides the implementer budget/timeout was
  not observed (see Open questions in requirements.md).
- mctl MCP tools were not called. The design relies on the gitops values above
  and the code, and makes no claim about live service status.

## Proposed solution

### 1. Pure evaluator: `orchestrator/feasibility.py` (new)

The evaluator imports nothing from temporalio, so it runs in both the agent
container and the Temporal worker. It mirrors the record style of
`orchestrator/implementation_completion.py`:

- **Record identity.** `API_VERSION = "feasibility.mctl.ai/v1alpha1"`,
  `KIND = "ProposalFeasibility"`, and `EVALUATOR_VERSION`, a constant bumped
  whenever any rule changes.
- **Verdicts.** `VERDICTS = {"feasible", "needs_split", "blocked_dependency", "uncertain"}`.
- **Bounds.** `MAX_BLOCKERS = 32`, `MAX_ADVISORIES = 32`, `MAX_SLICES = 16`,
  `MAX_DETAIL_CHARS = 256`.
- **`RunnerProfile`** (frozen dataclass):
  - `profile_id` (`"implementer/single-repo-v1"`), `write_repos` (target
    service only), `base_ref` (`"default-branch"`), `budget_usd`,
    `timeout_s`. The last two are `None` when unknown;
  - `digest()` is the sha256 of the canonical JSON.

  `runner_profile_for(service)` builds it from `IMPLEMENTER_BUDGET_USD` /
  `IMPLEMENTER_TIMEOUT_SECONDS` when importable, else `None`. Unknown values
  are recorded as unknown. No rule reads them as a capability, so they can
  only produce advisories.
- **`parse_tasks(text)`.** Matches
  `^- \[[ xX]\] (?P<id>T?\d+(?:\.\d+)?)\.\s+(?P<body>.*)$` under `## Tasks` /
  top-level, and ignores the `## Tests` section's `T` ids for dependency
  purposes. It extracts:
  - `(depends on 1, 2)`;
  - the annotations `[repo: <name>]`, `[spike]`, `[gate: merge|release|deploy|approval]`
    and `[base: <ref>]`, case-insensitive, any position in the line.

  An unknown `[gate:` value is kept as an advisory, not dropped.
- **`evaluate(files, service, profile, *, prior_refusal=None) -> ProposalFeasibility`.**
  The rules run in a fixed order:
  1. `tasks.md` is missing or has 0 parsed tasks: verdict `uncertain`,
     reason `tasks-unparseable`.
  2. Graph checks: an unknown dependency id or a cycle gives a hard blocker
     `task-graph-unresolvable`.
  3. Repository authority: a `[repo: X]` with `X != service` is a foreign task.
     If any target task reaches a foreign task through dependencies, the
     blocker is `cross-repo-prerequisite` (verdict class `blocked_dependency`).
     Otherwise it is `cross-repo-write` (class `needs_split`).
  4. Base: a `[base: R]` where R is not the profile base gives
     `foreign-branch-base` (class `blocked_dependency`). The implementer
     cannot stack on an open PR.
  5. A `[spike]` task with dependents gives `spike-gates-downstream`
     (class `needs_split`).
  6. A `[gate: K]` task with dependents gives `inter-step-gate`
     (class `needs_split`).
  7. Advisories, scanned over all four files with fixed regexes:
     - `undeclared-cross-repo-reference`: `mctlhq/<repo>` or `platform-gitops/`
       paths, or a known sibling-repo name from the service enum, used in a
       task line without a matching `[repo:]` tag;
     - `undeclared-branch-base`: "draft PR", "on top of #N", "stack on";
     - `undeclared-spike`: "spike", "investigate first", "decide whether";
     - `replay-sensitive-without-fixture`: `workflow.patched`, `_PATCH`,
       `dev_loop.py` or `DevLoopWorkflow` in the design, with no task line
       mentioning a replay or history fixture;
     - `broad-multi-component`: more than 12 tasks and 3 or more distinct
       top-level paths cited in tasks;
     - `runner-profile-unknown`: the budget or timeout is unknown;
     - `prior-refusal`: only when `prior_refusal` is supplied; the hook for #414.
  8. The verdict is the most severe class present:
     `blocked_dependency` > `needs_split` > `uncertain` (any advisory)
     > `feasible`.
- **Slices** are computed for every verdict:
  - the tasks are topologically layered;
  - the order is cut at every spike, gate and foreign-repository boundary;
  - consecutive tasks with the same repository are grouped;
  - each slice is `{index, repo, task_ids, reason_for_cut}`.

  `feasible` yields one slice. On an unresolvable graph no slices are proposed.
- **Serialization.** `to_json()` is canonical: sorted keys and no timestamp.
  `content_hash` is computed over everything else, so duplicate evaluations
  are byte-identical. `render_markdown(record)` produces the bounded comment
  section, which is shared by the investigator and the workflow.

The digest binding is `record.content_digest = proposal_state.content_digest_of(files)`
plus `runner_profile_digest`. `is_current(record, files, profile)` compares
both, so a changed proposal or profile makes an earlier record stale.

### 2. Investigator publication (`orchestrator/run_issue_investigator.py`)

- Add `FEASIBILITY_FILENAME = "feasibility.json"`.
- After the triplet validation and before `write_status_yaml` (step 5):
  - read the staged digest files;
  - run `feasibility.evaluate(..., runner_profile_for(service))`;
  - unlink any existing `feasibility.json` in staging, which may be
    agent-written or carried forward;
  - write the orchestrator-computed record.

  The investigator always overwrites and never trusts this file, and
  `_carry_forward` cannot resurrect a stale one because the overwrite happens
  in staging before the swap.
- On an exception, write no file and set `feasibility_unavailable=True`.
- `post_proposal_comment` gains a keyword `feasibility: ProposalFeasibility | None`.
  It appends `render_markdown(record)`, or "Feasibility could not be
  determined" when the record is unavailable. The body still goes through
  `policy_checkpoint.require`.
- `_build_prompt` gains a short "Implementability" block:
  - the implementer writes one repository at its default branch, in one attempt;
  - annotate tasks with `[repo: ...]`, `[spike]`, `[gate: ...]` and `[base: ...]`
    when they apply;
  - prefer proposing the first independently implementable slice and listing
    the rest under Out of scope.

`feasibility.json` is not in `PROPOSAL_DIGEST_FILES`, so the approval digest,
`scripts/proposal-content-digest.py` and the implementer's digest checks are
unchanged.

### 3. DevLoop activity: `evaluate_proposal_feasibility` (new, `activities/proposals.py`)

- Refactor `read_proposal_content_digest` into
  `read_proposal_content(service, slug) -> (files, digest, commit)`, which
  keeps the same one-commit and fail-closed reads, plus a thin
  `read_proposal_content_digest` wrapper so existing callers are untouched.
- `evaluate_proposal_feasibility(FeasibilityInput(service, slug, issue_url, report=True))`
  returns `FeasibilityResult(verdict, content_digest, content_commit,
  runner_profile_digest, mode, summary_markdown, blocking_task_ids)`:
  - `mode` is read from env `DEVLOOP_FEASIBILITY_MODE` (`observe` default;
    `enforce`; an unknown value is treated as `observe` and logged). It
    travels in the activity result, so the workflow stays deterministic;
  - an unreadable proposal raises `ApplicationError(type=UNAVAILABLE_TYPE)`
    for a bounded retry, the same as `request_devloop_approval`;
  - when `report` is set, it lists the issue's comments, and only if none
    carries `<!-- mctl-feasibility:<digest> -->` does it post
    `render_markdown` with that marker through the policy checkpoint. A
    retried activity therefore cannot double-post.
- Register the activity in `orchestrator/temporal/worker.py`'s
  control-role short activities.

### 4. DevLoop workflow (`orchestrator/temporal/workflows/dev_loop.py`)

- New constants:
  - `FEASIBILITY_PREFLIGHT_PATCH = "feasibility-preflight"`;
  - `MAX_FEASIBILITY_REEVALUATIONS = 8`, which bounds the re-runs after a
    content-moved refusal.
- At the start of `_request_canonical_approval`, after `find_proposal_slug`
  and only `if workflow.patched(FEASIBILITY_PREFLIGHT_PATCH)` (memoised per
  run):
  1. Run the `evaluate_proposal_feasibility` activity and store
     `self._feasibility_digest`.
  2. If `mode == "enforce"` and the verdict is in
     {`needs_split`, `blocked_dependency`}, run `_feasibility_hold()`:
     - a loop of `workflow.wait_condition(lambda: self._abandoned, timeout=GRANT_FRESHNESS_INTERVAL)`;
     - the issue state is checked through the existing `get_issue_state`
       activity on the same cadence the approval-watch uses;
     - each pass re-runs the activity with `report=True`, which only posts for
       a new digest;
     - the loop exits when the verdict is no longer hard-blocked;
     - it returns a `DevLoopResult` (ending the loop) on abandon (`"abandoned"`),
       on the issue closing (the existing wording), or at the deadline
       (`"feasibility hold expired: <verdict>"`).

     It never creates a grant.
  3. Call `request_devloop_approval` with
     `ApprovalRequestInput(..., expected_content_digest=self._feasibility_digest)`.
- `ApprovalRequestInput` gains `expected_content_digest: str = ""`. In the
  activity, when it is non-empty and differs from the digest just read, the
  activity returns `ApprovalRequestResult(ok=False, reason="content-moved")`
  before `ActionApprovalClient().create`.

  The workflow (patched branch only) treats `content-moved` as "re-run the
  preflight", bounded by `MAX_FEASIBILITY_REEVALUATIONS`. When the bound is
  exceeded the loop ends with `"approval request refused: proposal kept moving"`.
- The grant-freshness supersede path already re-enters
  `_request_canonical_approval`, so a drifted digest is re-evaluated before
  the fresh grant. No extra wiring is needed.
- Unpatched histories take none of these branches. The legacy (non-canonical)
  signal path is untouched in this slice.

### 5. Proposal for itself

This proposal is single-repository (`mctl-agents`), has no spike, no gate, and
no foreign base. It does touch `dev_loop.py`, so tasks 6 and 9 explicitly
include replay-fixture work. Its own expected verdict is `feasible`.

## Alternatives

1. **Model-based feasibility review: a second LLM pass or an extra
   investigator output file.** Dropped for this slice. It costs budget on
   every proposal, is not deterministic (it breaks the idempotency and
   digest-binding acceptance tests), and a model-written verdict file is
   forgeable by the same agent uid (see the `.status.yaml` forgery reasoning
   in `_landed_triplet_defects`). Declared annotations plus deterministic
   rules keep the hard blockers objective and leave prose-only signals as
   advisories.
2. **Put the verdict in the approval intent (`artifact_hash` or a new intent
   field) so mctl-api shows it in the card.** Dropped. mctl-api rebuilds the
   intent (`handlers_approval_grant.go`), so any change is a 409
   `approval_intent_mismatch`, and it is cross-repo work beyond this slice.
   The digest already binds the content, and the verdict is a pure function of
   it.
3. **End the DevLoop on a hard-blocked verdict instead of holding.** Dropped.
   `mctl_trigger_issue` does not restart a closed loop (only an abandoned
   pre-implement loop), so ending would strand the issue. A bounded hold that
   reacts to amendment matches the existing supersede and amend flow, which
   says "edit the proposal through a gitops PR, the loop asks again".
4. **Gate in the implementer (refuse earlier).** Dropped. That is after
   approval, which is exactly the defect. Recovery from implementer refusals
   stays with #414.

## Platform impact

- **Migrations.** None. The change adds a new optional file `feasibility.json`
  next to proposals. Old proposals without it are evaluated on demand by the
  DevLoop activity.
- **Backward compatibility.**
  - Content digest, approval intent hash, `.status.yaml` and approve CWFT are
    unchanged.
  - New workflow commands only run behind `FEASIBILITY_PREFLIGHT_PATCH`.
    Recorded `dev_loop_*` fixtures must replay unchanged, and new
    patched-branch fixtures are added.
  - The new `ApprovalRequestInput` field defaults to `""`, which is the old
    behaviour. Per the table in `tests/test_workflow_replay.py`, an added
    argument is invisible to replay.
- **Rollout.** `DEVLOOP_FEASIBILITY_MODE` defaults to `observe`, so verdicts
  are published and commented but nothing is held. Switching to `enforce` is a
  later, separate gitops change to `services/admins/mctl-agents-worker/values.yaml`
  after the fixture false-positive/negative report and some observed traffic.
  It is not part of this proposal's tasks.
- **Resources.** One extra activity per approval request, made of the same four
  GitHub content reads `request_devloop_approval` already makes plus one
  comments list. A hold adds at most one activity per hour for 7 days, which
  is the same cadence as grant freshness. History growth is bounded by the
  same deadline.
- **Risks and mitigations.**
  - False-positive hard blocks in `enforce` mode. Mitigation: hard blockers
    come only from explicit annotations or graph impossibility, prose signals
    are advisory only, and rollout starts in `observe`.
  - False negatives when annotations are missing. Mitigation: the advisory
    scan turns undeclared cross-repo, branch and spike phrasing into
    `uncertain`, never `feasible`.
  - Comment spam. Mitigation: one comment per digest, deduplicated by a hidden
    marker read back from GitHub.
  - Replay breakage. Mitigation: patch marker, recorded pre/post fixtures, and
    the memoisation test.
  - Comment posting fails. Mitigation: it is non-fatal, as in
    `post_proposal_comment`. The verdict still gates in `enforce` mode, since
    gating uses the computed result, not the comment.
