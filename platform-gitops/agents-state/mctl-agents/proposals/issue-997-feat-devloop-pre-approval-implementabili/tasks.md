# Tasks: issue-997-feat-devloop-pre-approval-implementabili

All tasks are in `mctlhq/mctl-agents`, based on the default branch. None is a
spike, and none needs a merge, deploy or approval between steps.

- [ ] 1. Add `orchestrator/feasibility.py`. It holds:
  - the record type: `API_VERSION`, `KIND`, `EVALUATOR_VERSION`, `VERDICTS`
    and the bound constants;
  - `RunnerProfile` with `digest()`, and `runner_profile_for(service)`;
  - `parse_tasks()`, `evaluate()` (rules 1-8 and the severity lattice from
    design.md section 1), `is_current()`, canonical `to_json()` with
    `content_hash`, and `render_markdown()`.

  The module has no temporalio import and reuses
  `proposal_state.content_digest_of`. `prior_refusal` is accepted and only
  produces the `prior-refusal` advisory.
  - DoD: the module imports in a temporalio-free environment, and
    `evaluate()` is pure and deterministic. Every blocker or advisory reason
    is a module constant, and every evidence list and detail string is
    capped.
- [ ] 2. Add the failure-inducing fixtures under
  `tests/fixtures/feasibility/<name>/`. Each fixture is the four digest files
  plus `expected.json` with the verdict, reason codes and blocking task ids:
  - `issue-993-shaped`: replay-sensitive `dev_loop.py` work, a
    `[repo: mctl-gitops]` companion, a `[spike]` gating later tasks, and
    `[base: PR#992]`;
  - `issue-996-first-slice`;
  - `issue-911-cross-repo-prerequisite`;
  - `issue-414-oversized-15-tasks`;
  - `small-single-repo`;
  - `untagged-prose-only`;
  - `cycle-and-missing-dep`;
  - `tasks-missing`.

  (depends on 1)
  - DoD: each fixture loads, and the expected verdicts are:

    | Fixture | Expected verdict |
    | --- | --- |
    | `issue-993-shaped` | `blocked_dependency`, with the ordered slices listed |
    | `issue-996-first-slice` | `feasible` or `uncertain`, never a hard block |
    | `issue-911-cross-repo-prerequisite` | `blocked_dependency` |
    | `issue-414-oversized-15-tasks` | `uncertain` with `broad-multi-component`, not a hard block and not an outage |
    | `small-single-repo` | `feasible` with one slice |
    | `untagged-prose-only` | `uncertain` |
    | `cycle-and-missing-dep` | `blocked_dependency` with `task-graph-unresolvable` |
    | `tasks-missing` | `uncertain` with `tasks-unparseable` |
- [ ] 3. Add `tests/test_feasibility.py`. It covers:
  - a fixture-table test that compares each `expected.json` and prints a
    false-positive/false-negative classification summary;
  - unit tests for each rule;
  - mutation-discriminating tests for each guard: removing one tag flips that
    fixture's verdict, and removing the cycle check makes
    `cycle-and-missing-dep` pass wrongly;
  - determinism: two evaluations are byte-identical;
  - digest drift: one changed byte in `requirements.md` or `tasks.md` changes
    `content_digest`, and `is_current()` returns False even when the slug and
    issue are unchanged;
  - a runner-profile change invalidates the record;
  - evidence bounds, and that no file content is echoed.

  (depends on 1, 2)
  - DoD: the tests pass under `uv run pytest tests/test_feasibility.py`, and
    the FP/FN summary appears in the test output.
- [ ] 4. Investigator publication in `orchestrator/run_issue_investigator.py`:
  - add `FEASIBILITY_FILENAME`;
  - before `write_status_yaml`, compute the record from staged files, unlink
    any agent-written or carried-forward `feasibility.json` in staging, and
    write the computed record;
  - on an exception, write none and flag it unavailable;
  - extend `post_proposal_comment(..., feasibility=...)` with
    `render_markdown`, or the "could not be determined" line;
  - add the "Implementability" annotation block to `_build_prompt`.

  (depends on 1)
  - DoD: `feasibility.json` is not in `PROPOSAL_DIGEST_FILES`, and
    `tests/test_proposal_digest.py` is unchanged and green. An agent-written
    `feasibility.json` claiming `feasible` is replaced by the computed one.
- [ ] 5. In `orchestrator/temporal/activities/proposals.py`:
  - refactor `read_proposal_content_digest` into `read_proposal_content`
    (files, digest, commit), keeping a wrapper;
  - add the `evaluate_proposal_feasibility` activity with
    `FeasibilityInput` / `FeasibilityResult`, the `DEVLOOP_FEASIBILITY_MODE`
    read (default `observe`), and the marker-deduplicated issue comment
    through the policy checkpoint;
  - register it in `orchestrator/temporal/worker.py`.

  In `activities/delegated_approval.py`, add
  `ApprovalRequestInput.expected_content_digest` and the `content-moved`
  early return before `ActionApprovalClient().create`.

  (depends on 1)
  - DoD: `tests/test_proposal_digest_remote.py` stays green. An unreadable
    proposal raises `UNAVAILABLE_TYPE`, and no grant is created on
    `content-moved`.
- [ ] 6. In `orchestrator/temporal/workflows/dev_loop.py`, add
  `FEASIBILITY_PREFLIGHT_PATCH` and `MAX_FEASIBILITY_REEVALUATIONS`. The
  preflight call sits at the start of `_request_canonical_approval` (after
  `find_proposal_slug`) under the patch. Add `_feasibility_hold()` for the
  enforce-mode hard-blocked case, with these exits:
  - abandon;
  - issue closed;
  - deadline `CANONICAL_APPROVAL_WAIT`, with
    `ended="feasibility hold expired: <verdict>"`;
  - non-blocking re-evaluation.

  Pass `expected_content_digest`, and handle `content-moved` with the bounded
  re-evaluation.

  (depends on 5)
  - DoD: the unpatched code path is unchanged, and
    `tests/test_patch_memoization.py` is green.
- [ ] 7. Record the new replay histories with
  `tools/record_workflow_history.py`, using scenarios added to
  `tests/replay_scenarios.py`:
  - `dev_loop_feasibility_observe.json`, where a hard-blocked verdict in
    observe mode still requests the grant;
  - `dev_loop_feasibility_hold.json`, where an enforce-mode hold is released
    by an amended, feasible digest.

  Also confirm that all existing `tests/fixtures/histories/dev_loop_*.json`
  replay clean.

  (depends on 6)
  - DoD: `tests/test_workflow_replay.py` is green with both new fixtures.
    Temporarily removing the patch guard turns an existing fixture red; check
    this once and note it in the PR description.
- [ ] 8. Docs:
  - add `docs/feasibility-preflight.md`, covering the verdict vocabulary, the
    annotation convention, the observe/enforce modes and how to amend a held
    proposal;
  - add a CHANGELOG entry via conventional commit.

  (depends on 4, 6)
  - DoD: the doc names every reason code defined in `orchestrator/feasibility.py`.

## Tests

- [ ] T1. `tests/test_feasibility.py`: the fixture table with all 8 fixtures,
  the FP/FN summary, a per-rule unit test, and mutation-discriminating guard
  tests.
- [ ] T2. Digest drift: editing `tasks.md` or `requirements.md` changes the
  digest, and `is_current()` returns False with the same slug and issue. In
  the workflow test, a digest change during the park re-runs the preflight
  before the fresh grant.
- [ ] T3. Idempotency: in `tests/test_dev_loop_workflow.py` with mocked
  activities, a repeated preflight, an activity retry and a re-entered
  `_request_canonical_approval` create no extra grant, issue, PR or execution.
  The comment activity posts once per digest, because the marker is already
  present.
- [ ] T4. Observe mode: a `needs_split` verdict still calls
  `request_devloop_approval` exactly once, with `expected_content_digest` set.
- [ ] T5. Enforce mode: with a `blocked_dependency` verdict,
  `request_devloop_approval` is not called. The loop leaves the hold:
  - on a later `feasible` verdict, after which the grant is requested for the
    new digest;
  - on abandon, with `ended="abandoned"`;
  - at the deadline, with `ended="feasibility hold expired: blocked_dependency"`.
- [ ] T6. `content-moved`: the request activity returns `ok=False` without
  calling `ActionApprovalClient.create`. The workflow re-evaluates and is
  bounded by `MAX_FEASIBILITY_REEVALUATIONS`.
- [ ] T7. Fail-closed: a `read_proposal_content` failure raises
  `UNAVAILABLE_TYPE`, and no verdict is invented. A runner profile with an
  unknown budget/timeout yields the `runner-profile-unknown` advisory, never
  `feasible`. An unknown `DEVLOOP_FEASIBILITY_MODE` is treated as `observe`.
- [ ] T8. Investigator: an agent-written `feasibility.json` is replaced, a
  stale carried-forward file is replaced, and an evaluator exception publishes
  no file and puts the "could not be determined" text in the comment body.
  The digest is unchanged by the new file.
- [ ] T9. Replay: the existing `dev_loop_*` histories and the two new
  feasibility histories replay clean in `tests/test_workflow_replay.py`.
- [ ] T10. A small single-repo fixture's end-to-end workflow test shows the
  same grant request sequence as today, plus one preflight activity. No new
  approval friction is added.

## Rollback

- Set `DEVLOOP_FEASIBILITY_MODE=observe`. This is the default, so it means
  removing any `enforce` setting from `services/admins/mctl-agents-worker/values.yaml`.
  It immediately stops all holds at their next re-evaluation, because the mode
  is re-read by every activity call. Loops already parked in a hold proceed to
  request their grant.
- For a full revert, revert the PR and redeploy the previous worker image
  (currently `1.117.0`). Histories that recorded the `feasibility-preflight`
  marker would then fail replay on the old code. Before reverting, drain them:
  abandon held loops with `mctl_abandon_dev_loop`, or keep the patch branch
  and only remove the hold by forcing `observe`. Prefer the mode switch.
- `feasibility.json` files left in agents-state are inert. They are not in the
  digest and nothing else reads them, so they can stay or be deleted.
