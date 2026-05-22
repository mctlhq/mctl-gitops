# Tasks: tier3-pr-shepherd

Implementer scope is the mctl-agents repo only. The companion CWFT and
CronWorkflow live in mctl-gitops and are added in a follow-up PR after
this lands and a new mctl-agents tag is published.

- [ ] 1. Add `agents/_shepherd/shepherd.md` — sub-agent system prompt
  (≤ 300 words). Role: parse code review findings into `{p1: bool,
  p2: bool, summaries: [...]}` JSON and shape the implementer
  followup prompt when needed. Tone matches existing implementer.md /
  researcher.md.
  - DoD: file exists, Markdown lint clean, prompt grounded in the
    shepherd's deterministic Python (does not duplicate logic the
    Python already does).
- [ ] 2. Add `orchestrator/run_shepherd.py` — main module.
  - DoD: `python -m orchestrator.run_shepherd --help` prints
    `--service`, `--slug`, `--budget` options. **Note:**
    `--review-feedback` is on the implementer CLI (task 3 below),
    not the shepherd — the shepherd builds the bundle in-memory and
    passes it to a `subprocess.run([... 'run_implementer', ...,
    '--review-feedback', path])` call.
  - DoD: implements the `decide()` function and the state-machine
    described in design.md.
  - DoD: implements `find_pr_for_proposal()`, `read_codex_review()`,
    `read_copilot_review()` (observed only, never gates a merge —
    its findings ride along to the per-tick operator log per
    design.md), `apply_followup()`, `merge_pr()`, `update_status()`
    helpers.
  - DoD: respects `SHEPHERD_BUDGET_USD` env (default 1.00); exits with
    a warning when the cap is crossed.
  - DoD: writes `<service>/<slug>: <decision>` for every processed
    proposal to stdout (greppable).
- [ ] 3. Extend `orchestrator/run_implementer.py` with a
  `--review-feedback <path>` flag that the shepherd uses to address
  codex findings on an existing branch.
  - DoD: when `--review-feedback` is set, the implementer detects
    that `feat/agents-<slug>` already exists on origin, fetches it,
    checks it out (instead of creating a new one), passes the bundle
    to its sub-agent, and pushes a follow-up commit (no new PR).
  - DoD: a unit test exercises the existing-branch path with a
    fixture worktree and a mocked GitHub API.
- [ ] 4. Add `tests/test_run_shepherd.py` — unit tests.
  - DoD: covers each branch of `decide()` (wait, address-review,
    merge, flip-to-merged, flip-to-rejected). The `give-up-after-3`
    cap lives in the outer state machine, not in `decide()` —
    covered separately by T6.
  - DoD: full state-machine test on a temp worktree fixture passing
    both the happy path (clean review → merge) and the loop path
    (P1 finding → followup → re-evaluate).
  - DoD: `pytest tests/test_run_shepherd.py` finishes successfully.
- [ ] 5. README — add a "Tier 3 — PR shepherd" section describing
  what the module does, the cron cadence, and how to run it locally
  (one-shot, against a real PR, with `--service X --slug Y`).
  - DoD: section under existing "Architecture" heading; cross-linked
    from the Tier 2 / implementer section.
- [ ] 6. Update `pyproject.toml` ONLY if a new third-party dep is
  needed (likely none — `gh` CLI + `subprocess` cover GitHub API).
  - DoD: `pip install -e .` clean.

## Tests
- [ ] T1. `decide()` returns `merge` when the PR is mergeable, codex
  has reacted +1 (or posted "no major issues"), and all checks are
  green.
- [ ] T2. `decide()` returns `address-review` when codex has posted a
  P1 review comment whose body contains the literal substring
  `![P1 Badge]` (codex prefixes findings with a Markdown badge image
  whose alt text is exactly `P1 Badge`, `P2 Badge`, etc.). Match
  with `"![P1 Badge]" in body` — no regex needed; if regex is
  preferred, use `re.search(r"!\[P[0-9] Badge\]", body)`.
- [ ] T3. `decide()` returns `wait` when codex has not yet responded
  (no review, no comment, no reaction on the latest commit).
- [ ] T4. `decide()` returns `flip-to-merged` when the PR is already
  merged (e.g. human merged it out of band).
- [ ] T5. `decide()` returns `flip-to-rejected` when the PR is closed
  unmerged.
- [ ] T6. The **outer state machine** (NOT `decide()`) flips a
  proposal's `.status.yaml` to `status: review-stuck` after 3
  unsuccessful followup attempts on the same PR. `decide()` itself
  stays pure (`pr` + `codex_review` only); the attempt counter
  lives on the proposal as `review_attempts:` in `.status.yaml` and
  is read/incremented by the loop that calls `decide()`. Test the
  cap by driving the outer loop with three consecutive
  `address-review` results from `decide()` and asserting the
  fourth tick transitions the proposal to `review-stuck`.
- [ ] T7. End-to-end state-machine test: implemented → review-fixing
  → implemented → merged with fixture data driving each tick.

## Rollback
1. The shepherd has no destructive output beyond `.status.yaml`
   transitions and merging open PRs. Rollback = revert this commit
   in mctl-agents and re-tag.
2. In-flight `review-fixing` states will be left dangling — they
   live in `platform-gitops/agents-state/<svc>/proposals/<slug>/.status.yaml`
   (committed to gitops main), NOT in Vault. Clear them with a
   one-line PR to mctl-gitops that flips the affected files back to
   `status: implemented` so the next operator decides what to do
   manually. Alternatively, close the dangling PR on GitHub — the
   shepherd's next non-rolled-back run will observe `closed_unmerged`
   and flip the proposal to `rejected` on its own.
3. The companion gitops CWFT/cron are NOT in this PR; they ship in a
   follow-up that can be reverted independently if needed.
