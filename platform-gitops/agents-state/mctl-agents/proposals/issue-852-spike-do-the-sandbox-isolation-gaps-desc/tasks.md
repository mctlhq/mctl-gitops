# Tasks: issue-852-spike-do-the-sandbox-isolation-gaps-desc

- [ ] 1. Retry fetching https://thenewstack.io/how-to-sandbox-agents/ and extract its taxonomy of
  isolation gaps. If the body is unavailable, use the title-derived categories from requirements.md. Done
  when the report's "Source and limits" section states which source was used.
- [ ] 2. Verify D1-D5 against the code (depends on 1): `orchestrator/options.py` (`_policy_hooks`,
  `_command_audit_hooks`, the builders at about lines 1304 and 1377, every `setting_sources` use) and
  `orchestrator/run_implementer.py` (`_TYPECHECK_ENV_KEEP`). For D3, check the pinned `claude_agent_sdk`
  version in `uv.lock` and its documented meaning of the `"project"` setting source: does it load
  `.claude/settings.json` hooks or permissions? Done when each candidate row is confirmed `new` or demoted
  to `covered-by-*`, `not-observed` or `not-a-gap`, with a file:symbol citation.
- [ ] 3. Map every taxonomy category to #807 G1-G6 (PR #810's `docs/spikes/807-agent-isolation-k8s.md`)
  or to #830 (depends on 1). Done when the coverage map has no unmapped category.
- [ ] 4. Write `docs/spikes/852-sandbox-isolation-delta.md` (depends on 2 and 3). It has the sections
  Source and limits, Coverage map, Delta gap list, Decision (`STATUS: DRAFT` unless the owner records
  `NO_NEW_GAPS`, `NEW_GAPS_FOLLOW_UP` or `FOLD_INTO_807`), and Follow-ups (draft issue bodies, not filed).
  Done when the report contains no secret values, payloads or escape procedures.
- [ ] 5. Add `tests/test_spike_852_report.py` (depends on 4), modelled on `tests/test_spike_796_report.py`.
  Done when `uv run pytest tests/test_spike_852_report.py` passes locally.

## Tests

- [ ] T1. The report has `STATUS: DRAFT` or exactly one allowed token on its `STATUS:` line.
- [ ] T2. Every gap-table row has non-empty `evidence`, and its `status` is in
  `{new, covered-by-807, covered-by-830, not-observed, not-a-gap}`.
- [ ] T3. `git diff --name-only $(merge-base HEAD origin/main) HEAD -- orchestrator config
  agents/_manifests` is empty. The test skips without `origin/main`.
- [ ] T4. The report matches no token-shaped regex (`ghp_`, `gho_`, `github_pat_`, `sk-ant-`,
  `-----BEGIN`).
- [ ] T5. The existing suite still passes, including `tests/test_worker_isolation.py` and
  `tests/test_portable_runtime_isolation.py`.

## Rollback

The spike adds only `docs/spikes/852-sandbox-isolation-delta.md` and `tests/test_spike_852_report.py`.
To roll back, revert the PR. No runtime, manifest, profile or gitops state changes, so nothing else needs
undoing. A follow-up that acts on the decision deletes the guard test.
