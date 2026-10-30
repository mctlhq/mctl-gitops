# Tasks: issue-875-spike-how-do-github-agentic-workflows-sa

- [ ] 1. Re-fetch the gh-aw sources: the GA changelog, the full safe-outputs reference (including the
  section past 100k characters), and the AWF/network, threat detection and staged-mode pages. Record what
  was retrieved and when. — DoD: `## 1. Source and limits` lists each URL as retrieved or not retrieved.
- [ ] 2. Re-verify DevLoop evidence on main: `run_issue_investigator.py` (`_staging_dir`,
  `_landed_triplet_defects`, `post_proposal_comment`), `options.py` (`_policy_hooks`,
  `_ReadOnlyDirsHook`, the investigator/implementer `allowed_tools`), `run_implementer.py` push/PR,
  `policy_checkpoint.py`, and gitops (investigator profile, `policy.yaml`, investigate CWFT
  `GITHUB_TOKEN`, egress `proxy.yaml`). — DoD: every evidence cell cites a symbol and a path.
- [ ] 3. (depends on 1, 2) Write `docs/spikes/875-gh-aw-guardrail-comparison.md` with `STATUS: DRAFT`,
  canonical-boundaries section, and the 7-column comparison covering safe outputs, permissions, network,
  sandbox, threat detection, reusable enforcement, interop. — DoD: rows S1-S3, P1-P2, N1-N3, T1, R1,
  I1-I2 present (or justified removals); unverified gh-aw claims are `not-observed`.
- [ ] 4. (depends on 3) Draft follow-ups for each `adopt` row with owner repo, control, rollback; reference
  #807/#830/#852/#868-#870 instead of duplicating. — DoD: `## 5. Follow-ups` complete; no duplicate of a
  tracked gap.
- [ ] 5. (depends on 3) Add `tests/test_spike_875_report.py` modelled on `tests/test_spike_852_report.py`.
  — DoD: test passes locally with `uv run pytest tests/test_spike_875_report.py`.
- [ ] 6. (depends on 4, 5) Open the PR with `Refs #875` (not `Closes`). The STATUS value stays `DRAFT`
  until the owner records the decision. — DoD: PR open, CI green.

## Tests

- [ ] T1. Exactly one `STATUS:` line; its value is `DRAFT`, `ADOPT_PATTERNS`, `REFERENCE_ONLY` or
  `NO_ACTION`.
- [ ] T2. Every comparison row has 7 cells, non-empty `devloop_today` evidence, and a status in
  {adopt, already-covered, covered-by-807, covered-by-852, not-applicable, not-observed}.
- [ ] T3. All six dimensions appear (safe outputs, permissions, network/sandbox, threat detection,
  reusable enforcement, interop).
- [ ] T4. Every `adopt` row has a non-empty `follow_up` and `owner`.
- [ ] T5. No token-shaped strings (`ghp_`, `gho_`, `github_pat_`, `sk-ant-`, `-----BEGIN`).

## Rollback

Docs and test only. Revert the PR to remove the report and the guard test. No runtime, gitops, or profile
state changes. Follow-up issues filed from the report can be closed independently.
