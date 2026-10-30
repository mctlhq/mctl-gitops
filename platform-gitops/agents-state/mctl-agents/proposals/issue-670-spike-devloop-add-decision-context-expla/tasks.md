# Tasks: issue-670-spike-devloop-add-decision-context-expla

- [ ] 1. Write the `decision-context/v0` validator in
  `docs/spikes/670/decision_context.py`: parse the YAML front block, enforce
  the fixed section keys, claim kinds, ref grammar (`repo:<path>@<sha>#L<a>-L<b>`,
  `proposal:<file>`, `evidence:<id>`), grounded-only high-scrutiny sections,
  required failure modes for `risk.level: high`, `repo:` SHA equal to
  `binding.target_repo_sha`, unknown-key rejection and gate-waiver-key
  rejection. Add an optional `ref_resolver` callback. — DoD: importable with
  `python -I`; returns a list of typed violation codes; imports
  `orchestrator.proposal_state.content_digest_of` for digests and nothing
  else from `orchestrator`.
- [ ] 2. Add `freshness(artifact, current_digest, current_sha)` to the same
  module (depends on 1). — DoD: returns `fresh`, `stale` or `unknown`; a
  None input yields `unknown`; any mismatch yields `stale`.
- [ ] 3. Write the explainer prompt `docs/spikes/670/explain.md` and the
  operator script `docs/spikes/670/run_explainer.sh` (read-only tools, repo
  pinned at a given SHA, optional `focus`, writes the artifact plus
  `measurements.json` with latency, tokens, cost and files read). — DoD:
  the script documents every input and runs nothing on import or in CI.
- [ ] 4. Add negative fixtures under `docs/spikes/670/fixtures/invalid/`:
  ungrounded invariant, SHA-mismatched ref, unknown key, `auto_approve` key,
  high-risk artifact missing `state_after_approval`, and a review pointer
  without a ref (depends on 1). — DoD: each fails with exactly its
  expected code.
- [ ] 5. Add a hand-authored valid example for #702 at
  `docs/spikes/670/fixtures/702-decision-context.example.md`, bound to the
  #702 proposal digest computed with `content_digest_of` and the #702
  PR merge-base SHA (depends on 1, 2). Mark it `generator: hand-authored`,
  not model output. — DoD: it validates; `freshness` against the
  post-merge SHA returns `stale`.
- [ ] 6. Write the report `docs/spikes/670-decision-context.md` with
  `STATUS: DRAFT`, the allowed tokens (`GO`, `LIMITED_GO`, `NO_GO`), the
  current-state map (files cited in design.md), the contract, the
  hypotheses for Q1 to Q10, the risk-based review-depth model (advisory
  only), the failure modes (polished-but-wrong, stale context,
  rubber-stamping, digest-scope confusion), the comparison with the current
  flow, a measurement table with every cell `unobserved`, and a GO-criteria
  checklist (depends on 1 to 5). — DoD: no metric is estimated; every
  unmeasured cell reads `unobserved`.
- [ ] 7. Write the guard and contract tests
  `tests/test_spike_670_decision_context.py` (depends on 1 to 6). — DoD:
  `uv run pytest tests/test_spike_670_decision_context.py -q` passes.
- [ ] 8. Open the PR with `Refs mctlhq/mctl-agents#670` (never `Closes`).
  The PR body lists the operator measurement procedure: run task 3 on #702
  and on one low-risk merged proposal; time a reviewer on the current and
  experimental paths; diff the review pointers against the merged #702 PR;
  fill the table; replace `STATUS: DRAFT` with one token. — DoD: CI is
  green, and the PR touches only `docs/spikes/670*` and the new test.

## Tests

- [ ] T1. Every invalid fixture is rejected with its expected violation
  code. The valid #702 example passes with zero violations.
- [ ] T2. `freshness` returns `fresh` on exact match, `stale` on a digest or
  SHA mismatch, and `unknown` when either current value is None.
- [ ] T3. The binding digest in the #702 example equals
  `content_digest_of` over the committed copy of the proposal bytes, or the
  test recomputes from `$MCTL_GITOPS_ROOT` when set and skips otherwise.
- [ ] T4. Gate-waiver keys (`auto_approve`, `skip_review`,
  `satisfies_gate`, `waive_*`) are rejected at any depth.
- [ ] T5. Report guard: either `STATUS: DRAFT` is present or the STATUS
  line holds exactly one of `GO`, `LIMITED_GO`, `NO_GO`.
- [ ] T6. No-runtime guard: `git diff` against the merge-base shows no change
  under `orchestrator/`, `config/` or `agents/_manifests/` (skip when
  there is no `origin/main`, as in `tests/test_spike_796_report.py`).
- [ ] T7. Committed fixtures are below 256 KiB each and contain no
  token-like strings (`ghp_`, `art_`, `sk-`).

## Rollback

The spike adds only `docs/spikes/670-decision-context.md`,
`docs/spikes/670/` and `tests/test_spike_670_decision_context.py`. Revert
the PR. No runtime, gitops, registry or deployed state is touched, so
nothing else needs to be undone.
