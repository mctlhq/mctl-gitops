# Tasks: issue-601-feat-devloop-register-mctl-claude-remote

- [ ] 1. Add `"mctl-claude-remote"` to `SERVICES` in `config/settings.py` after `"newton-mcp-gateway"` — DoD: appears exactly once; `test_services_has_no_duplicates` passes.
- [ ] 2. Add `"mctl-claude-remote"` to `NON_ROTATING_SERVICES` (depends on 1) — DoD: `ROTATING_SERVICES` is unchanged versus main.
- [ ] 3. Add a comment paragraph to the `config/settings.py` block above `SERVICES` (depends on 1) — DoD: states issue-driven `agents:intake` intake, no `agents/mctl-claude-remote/` scaffold, must not enter `ROTATING_SERVICES`, generic implementer (`agents/_generic/.claude/agents/implementer.md`) covers it, no shepherd skip entry.
- [ ] 4. Do NOT create `agents/mctl-claude-remote/` — DoD: `tests/test_agent_inventory.py` still passes unchanged.
- [ ] 5. Add settings tests in `tests/test_settings.py` (depends on 2) — DoD: T1, T2 pass.
- [ ] 6. Add poller tests in `tests/test_run_issue_poller.py` (depends on 1) — DoD: T3, T4 pass.
- [ ] 7. Run the full test suite (`pytest`) — DoD: green, no existing test modified.

## Tests
- [ ] T1. `test_mctl_claude_remote_is_a_registered_service`: `"mctl-claude-remote" in SERVICES`.
- [ ] T2. `test_mctl_claude_remote_is_non_rotating`: in `NON_ROTATING_SERVICES` and not in `ROTATING_SERVICES`.
- [ ] T3. `test_poll_dispatches_mctl_claude_remote`: `_ref(repo="mctl-claude-remote", number=79)`; `start_dev_loop_workflow` stubbed with `_start_ok_recording`; `remove_label` recorded; assert `started == 1`, `failures == 0`, the issue URL was dispatched and `agents:intake` removed.
- [ ] T4. `test_poll_dry_run_treats_mctl_claude_remote_as_known`: `poll(dry_run=True)` with capsys; output contains "would start/attach" and not "not a known service"; `failures == 0`; start/remove stubs never called.
- [ ] T5. Existing suites (`test_settings.py`, `test_agent_inventory.py`, `test_run_issue_poller.py`) pass unchanged, proving no change for existing services.

## Rollback
Revert the single commit (remove the name from `SERVICES`, `NON_ROTATING_SERVICES`, the comment and the new tests). The poller then again skips mctl-claude-remote issues and keeps their label. Any in-flight DevLoopWorkflow for a mctl-claude-remote issue should be abandoned with `mctl_abandon_dev_loop` before or after the revert; no state migration is required.
