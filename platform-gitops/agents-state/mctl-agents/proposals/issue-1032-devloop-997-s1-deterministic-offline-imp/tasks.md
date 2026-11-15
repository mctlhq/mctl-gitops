# Tasks: issue-1032-devloop-997-s1-deterministic-offline-imp

Everything below is in `mctlhq/mctl-agents`, based on the default branch.
There is no spike, and no approval, merge, release or deploy is needed between
steps. No existing module is modified.

- [ ] 1. Add the task parser, `orchestrator/feasibility_tasks.py`:
  - `TaskGraph`, `parse_tasks()`, with the sections, the head regex, block
    joining, the `(depends on ...)` spec grammar (`,`, `and`, ranges, suffixed
    ids) and tags;
  - unknown-line capture, plus duplicate, missing-target and cycle detection;
  - deterministic Kahn layering.

  DoD: the parser parses the inline, next-line and wrapped-parenthesis clause
  forms. Only stdlib is imported.
- [ ] 2. Add the runner profile, `orchestrator/feasibility_profile.py`:
  - `Capability`, `RunnerProfile`, `digest()`, the pure `derive_profile()`,
    and `load_deployed_snapshot()`;
  - the profile fixtures `tests/fixtures/feasibility/profiles/deployed-2026-11.json`
    (20.00 / 5400, with provenance pointing at
    `argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`),
    `default-only.json` and `commit-verified-single-type.json`.

  DoD: without a deployed snapshot, budget and timeout are `default-only` and
  not verified. A snapshot that is unreadable or malformed raises an error. The
  digest changes when any value or source changes.
- [ ] 3. Add the evaluator, `orchestrator/feasibility.py`:
  - constants, `REASON_CODES`, rules 1-9 in design order, the verdict lattice,
    slices, the bounded evidence, and the canonical `to_json()` /
    `content_hash`;
  - `is_current()`, using `proposal_state.content_digest_of`.

  (depends on 1, 2)

  DoD: `evaluate()` does no I/O and has no `os.environ` access. Every reason
  code is in `REASON_CODES`, and every evidence string and list is capped.
- [ ] 4. Add the fixture corpus under `tests/fixtures/feasibility/`:
  - the eight named fixtures and the synthetic mutation fixtures listed in
    design.md section 5;
  - for each fixture, `meta.json` (with `human_label`) and `SOURCE.md`
    (verbatim or shaped, source path, gitops commit).

  (depends on 3)

  DoD: every fixture loads. The `issue-997-self` meta lists only structural
  asserts (task count, edge set, reason codes) and no expected verdict.
- [ ] 5. Add `tests/test_feasibility.py` (the tests T1-T9 below).

  (depends on 3, 4)

  DoD: `uv run pytest tests/test_feasibility.py` is green, and the whole suite
  is green.
- [ ] 6. Add the offline tools `tools/evaluate_feasibility.py` (with
  `--profile` / `--from-cwft`) and `tools/feasibility_corpus_report.py`
  (FP/FN table, limitations, median/p95 timing). Both write to stdout only.

  (depends on 3, 4)

  DoD: running the report prints all fixtures, and its output is pasted into
  the PR description.
- [ ] 7. Add `docs/feasibility-evaluator.md`:
  - the verdict vocabulary and every reason code with its class;
  - the tasks.md grammar and the optional tags;
  - the profile sources, and the known limitations and thresholds;
  - a statement that S1 has no production consumer.

  Also add a CHANGELOG entry via a conventional `feat:` commit.

  (depends on 3, 6)

  DoD: the doc names every code in `REASON_CODES`. A test asserts this.

## Tests

- [ ] T1. Fixture table: each fixture's verdict and reason codes match
  `meta.json` asserts, and an FP/FN summary is printed. `issue-997-self`
  asserts:
  - 8 tasks;
  - exactly the edges 2->1, 3->1, 3->2, 4->1, 5->1, 6->5, 7->6, 8->4, 8->6;
  - the detected codes.

  It prints the verdict without asserting one.
- [ ] T2. Multiline `depends on`: `multiline-depends` and `issue-911-cross-repo`
  yield their edges. Monkeypatching the block joiner to head-only makes the
  test fail. This is a mutation check, run in the test itself.
- [ ] T3. Graph guards:
  - `cycle` gives `task-graph-cyclic`, and disabling the cycle check flips it;
  - `missing-target` gives `dependency-target-missing`;
  - `duplicate-id` gives `task-id-duplicate`;
  - `ambiguous-depends` and `unknown-task-syntax` give `uncertain`;
  - `tasks-missing` gives `tasks-unparseable`.
- [ ] T4. Rule discrimination. For the repo, base, spike, gate, replay and
  commit-contract rules, removing the triggering token from the fixture
  (deriving it in-test) removes that reason. Disabling the rule makes the
  fixture's assert fail.
- [ ] T5. Capabilities:
  - `small-single-repo` under `default-only.json` is `uncertain` with
    `runner-capability-unknown`;
  - it is `feasible` only under `deployed-2026-11.json`;
  - `issue-1025-commit-contract` is `blocked_dependency` under
    `commit-verified-single-type.json` and `uncertain` under the deployed
    profile, whose commit contract is unverified.
- [ ] T6. Determinism and binding:
  - two evaluations, and an evaluation in a subprocess, give byte-identical
    JSON;
  - a one-byte change in any digest file changes `content_digest`, and
    `is_current` is then False;
  - a profile change also makes `is_current` False.
- [ ] T7. Purity and no side effects:
  - an AST import allowlist for the three modules;
  - `builtins.open`, `socket.socket`, `subprocess.Popen`, `os.environ.__getitem__`
    and `orchestrator.action_approvals.ActionApprovalClient.create` are
    patched to raise, then the whole corpus is evaluated;
  - the fixture tree's file mtimes and set are unchanged, and no
    `.status.yaml` or `feasibility.json` appears.
- [ ] T8. Bounds: an oversized synthetic input with 200 tasks and long lines
  keeps reasons <= `MAX_REASONS`, evidence <= caps and slices <= `MAX_SLICES`.
  No line longer than `MAX_EVIDENCE_CHARS` is echoed.
- [ ] T9. Docs coverage: every `REASON_CODES` key appears in
  `docs/feasibility-evaluator.md`.

## Rollback

Revert the PR. Nothing imports the new modules and no runtime, worker, CWFT,
digest or `.status.yaml` behaviour changes, so a revert needs no deploy, drain
or data cleanup.
