# Tasks: issue-1032-devloop-997-s1-deterministic-offline-imp

Everything below is in `mctlhq/mctl-agents`, based on the default branch.
There is no spike, and no approval, merge, release or deploy is needed between
steps. No existing module is modified. No tests, implementer or other execution are authorized until separate approval of the amended proposal digest.

- [ ] 1. Add the task parser, `orchestrator/feasibility_tasks.py`:
  - `TaskGraph`, `parse_tasks()`, with the sections, the head regex, block
    joining, the `(depends on ...)` spec grammar (`,`, `and`, ranges, suffixed
    ids) and tags;
  - unknown-line capture including detached/unindented dependency clauses, malformed/wrapped task heads, duplicate ids, missing targets and cycles;
  - deterministic Kahn layering.

  DoD: the parser parses the inline, next-line and wrapped-parenthesis clause
  forms. Only stdlib is imported.
- [ ] 2. Add the runner profile, `orchestrator/feasibility_profile.py`:
  - `Capability` with `source_code | gitops_declared | runtime_observed | synthetic_fixture | unknown` origins, evidence reference, source/image/config revision;
  - pure `RunnerProfile` / `derive_profile()` and provenance-bound digest;
  - separate commit-shape contract from red/green/mutation test-evidence contract;
  - `load_evidence_snapshot()` and profiles: `gitops-declared-2026-11.json` (20/5400 **declared, not observed**), `default-only.json`, `synthetic-verified.json`, `commit-verified-single-type.json`.

  DoD: GitOps and source HEAD are not misrepresented as live effective runner; unknown runtime facts remain unknown; synthetic fixture is labelled; changing a value or provenance invalidates the digest.
- [ ] 3. Add the evaluator, `orchestrator/feasibility.py`:
  - constants, `REASON_CODES`, rules 1-9, verdict lattice, slices, bounded evidence, canonical `to_json()` / `content_hash`;
  - unknown/detached dependency and runner-provenance guards;
  - independent commit-shape versus test-evidence classification;
  - `is_current()`, using `proposal_state.content_digest_of`.

  (depends on 1, 2)

  DoD: `evaluate()` does no I/O and has no `os.environ` access. Every reason
  code is in `REASON_CODES`, and every evidence string and list is capped.
- [ ] 4. Add the fixture corpus under `tests/fixtures/feasibility/`:
  - the eight named fixtures and synthetic mutations in design.md, plus `red-before-single-commit`, `unindented-detached-dependency`, `malformed-wrapped-task-head`;
  - for each fixture `meta.json` with independently reviewed `human_label` or `ground_truth_unverified`, and `SOURCE.md` with verbatim/shaped/synthetic provenance, source path/SHA and review evidence.

  (depends on 3)

  DoD: every fixture loads. `issue-997-self` asserts its structural facts, not a forced model verdict; an independently established impossibility may still trigger a critical false-feasible stop.
- [ ] 5. Add `tests/test_feasibility.py` (the tests T1-T9 below).

  (depends on 3, 4)

  DoD: `uv run pytest tests/test_feasibility.py` is green, and the whole suite
  is green.
- [ ] 6. Add the offline tools `tools/evaluate_feasibility.py` (with
  `--profile` / `--from-cwft`) and `tools/feasibility_corpus_report.py`
  (4x4 confusion matrix, critical false-feasible STOP signal, provenance,
  limitations, median/p95 timing). Both write to stdout only.

  (depends on 3, 4)

  DoD: running the report prints all fixtures, and its output is pasted into
  the PR description.
- [ ] 7. Add `docs/feasibility-evaluator.md`:
  - the verdict vocabulary and every reason code with its class;
  - the tasks.md grammar and the optional tags;
  - capability provenance (source/GitOps/runtime/synthetic/unknown), limitations and thresholds;
  - a statement that S1 has no production consumer.

  Also add a CHANGELOG entry via a conventional `feat:` commit.

  (depends on 3, 6)

  DoD: the doc names every code in `REASON_CODES`. A test asserts this.

## Tests

- [ ] T1. Fixture table: verdict and reasons match `meta.json` asserts,
  with independently reviewed ground truth, 4x4 confusion matrix and
  explicit critical false-feasible STOP signal. `issue-997-self`
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
  - `tasks-missing` gives `tasks-unparseable`;
  - detached/unindented clauses and malformed/wrapped task heads return `uncertain`.
- [ ] T4. Rule discrimination. For the repo, base, spike, gate, replay and
  commit-contract rules, removing the triggering token from the fixture
  (deriving it in-test) removes that reason. Disabling the rule makes the
  fixture's assert fail.
- [ ] T5. Capabilities and commit/test-evidence separation:
  - `small-single-repo` is `uncertain` under default-only or GitOps-declared profiles;
  - only a visibly synthetic, fully specified test profile exercises `feasible`, without claiming production readiness;
  - explicit #1025 commit-shape mismatch is blocked under a verified-incompatible synthetic profile and uncertain under an unverified one;
  - `red-before-single-commit` MUST NOT yield `commit-contract-incompatible` solely for test evidence.
- [ ] T6. Determinism and binding:
  - two evaluations, and an evaluation in a subprocess, give byte-identical
    JSON;
  - a one-byte change in any digest file changes `content_digest`, and
    `is_current` is then False;
  - changed profile value, source origin or evidence revision makes `is_current` False.
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

## Pre-approval execution-envelope checkpoint

This covers three new modules, two tools, a large fixture corpus, mutation
tests and docs despite only seven task headings. GitOps declares $20 / 5400
seconds but that is not a live runner attestation. Before approval, present
an explicit file/test sizing breakdown. If one-shot feasibility cannot be
defended, split into independently digest-approved S1a (core/critical tests)
and S1b (expanded corpus/report/docs); no implicit inherited approval.

## Acceptance stop condition

- [ ] T10. If any independently confirmed hard-impossible fixture is
  classified `feasible`, report `S2 readiness: STOP`. Do not promote
  the evaluator into S2 approval-path integration until corrected.
  Human labels of uncertain origin are reported separately.

## Rollback

Revert the PR. Nothing imports the new modules and no runtime, worker, CWFT,
digest or `.status.yaml` behaviour changes, so a revert needs no deploy, drain
or data cleanup.
