# Tasks: issue-313-spike-evaluate-agentic-trading-lab-patte

- [ ] 1. Re-pin sources. Record the current `mctlhq/.github` HEAD. Re-resolve
  Open-Finance-Lab/AgenticTrading `main` and mctl-agents `main`. If either moved from
  `5a49d00a963e99b94b6c559d08a74cb03e1e3da2` / `96b1f542b3a2e7b872e066c627742b0c1c3e7426`, re-check
  each file cited in design.md at the new SHA, update the pins, and note any changed claim. Also
  re-check the open/closed state of mctl-agents#310, #526, #698, #854, #195 and #199, and whether
  `EvaluationSuite` has landed on main. — DoD: the evidence pins table lists three 40-hex SHAs; every
  cited path exists at its pin; issue states are dated.
- [ ] 2. Write `docs/spikes/agentic-trading-lab-patterns.md` with sections 1-11 from design.md
  (non-claims and tags, pins, upstream map with permalinks and the OpenMDW-1.0 license, dedup
  matrix, transferable patterns, experiment protocol, evidence schema reuse, decision criteria
  C1-C6, security/license and stop conditions, ownership map, proposed verdict
  `REUSE_EXISTING_ONLY` with rejected alternatives) (depends on 1). — DoD: every upstream claim is
  tagged implemented / documented only / not verified; every result cell is `observed`,
  `estimated`, `not measured` or `unknown`; the scope-denial blockers are quoted; no trading
  metrics; English only, no emoji.
- [ ] 3. Add `roadmap/spikes/agentic-trading-lab-patterns.yaml` exactly as shown in design.md:
  `lifecycle: proposed`, the four outcomes, `github.issue` mctlhq/.github#313, `execution.devloop:
  true`, `evidence.report`, and no `decision`, `epic` or `timebox` (depends on 2). — DoD:
  `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` exits 0.
- [ ] 4. Add the "Spikes" index bullet to `AGENTS.md` (depends on 2). — DoD: the link resolves to
  the new report; no other line in `AGENTS.md` changes.
- [ ] 5. Open one PR against `mctlhq/.github` with "Refs mctlhq/.github#313" (not "Closes"). The PR
  body says the verdict is proposed and owner-pending, and that no follow-up issue was filed
  (depends on 3, 4). — DoD: the PR touches only the three files above; CI
  (`roadmap-validate.yml`) is green.

## Tests

- [ ] T1. `python roadmap/scripts/validate.py roadmap/epics roadmap/spikes` passes with the new
  manifest.
- [ ] T2. `python -m pytest roadmap/tests/test_validate_spike.py` still passes (no schema or
  validator change).
- [ ] T3. Negative check: a scratch copy of the manifest with a `decision` block while
  `lifecycle: proposed` is rejected by the validator. This confirms the report cannot be mistaken
  for a decision. Do not commit the scratch file.
- [ ] T4. Every link check passes: each upstream and mctl-agents permalink in the report resolves at
  its pinned SHA (`gh api repos/<repo>/contents/<path>?ref=<sha>` returns 200).
- [ ] T5. Review: `grep -n -E 'PASS|observed' docs/spikes/agentic-trading-lab-patterns.md` shows no
  candidate cell claimed as observed. All candidate cells read `not measured`, because the
  experiment was not run.

## Rollback

Revert the single PR. The change is documentation plus one `lifecycle: proposed` manifest that
nothing consumes: spikes are not part of the RoadmapPublication yet (`roadmap/README.md`). Reverting
leaves no runtime, CI or GitOps residue.
