# Tasks: issue-868-fix-agents-stop-loading-project-settings

- [ ] 1. Red test first. Add `tests/test_target_clone_settings_isolation.py`, with a fixture clone holding `.claude/settings.json` (a SessionStart/PreToolUse command hook that writes a marker, plus `permissions.allow`), `.claude/agents/evil.md` and `CLAUDE.md`. Add the deterministic argv test (stub `claude` via `SubprocessCLITransport`, as in `tests/test_tool_subprocess_env.py`) for `build_implementer_agent_options`, `build_issue_investigator_options` and both branches of `build_issue_investigator_options_from_plan`. Add the opt-in live test gated on `MCTL_LIVE_CLI_SETTINGS_TEST=1`, which runs the bundled CLI and has a `["project"]` control case. — DoD: the test is committed and fails on current main, because argv contains `project`. Record the live-test result, or "not run, why", in the PR description.
- [ ] 2. Add `TARGET_CLONE_SETTING_SOURCES = []` in `orchestrator/options.py` and use it at the four construction sites (current lines 1380, 1531, 1612, 1633) (depends on 1). — DoD: the task 1 deterministic test passes, and the trusted-cwd builders still use `["project"]`.
- [ ] 3. Add `orchestrator/personas.py` with `load_agent_definition(path)`. It parses the frontmatter with `yaml.safe_load`: `name` and `description` are required, `tools` is a comma-split list, `model` is optional, and the body becomes `prompt`. — DoD: a unit test parses every `agents/*/.claude/agents/implementer.md` without error and with the expected tools, and malformed input raises `ValueError`.
- [ ] 4. Change `run_implementer._stage_implementer_agent(target, service)` so it stops copying into `<clone>/.claude/agents/`. It keeps the per-service then generic resolution and the `SystemExit`, keeps the `REFUSAL_MARKER_FILENAME` exclude entry, and returns the `AgentDefinition` (depends on 3). — DoD: after staging, `<clone>/.claude` is not created, and `.git/info/exclude` still lists the refusal marker.
- [ ] 5. Thread `persona` from the two call sites (current 3033 and 4954) through `_run_implementer_agent` into `build_implementer_agent_options(..., persona=None)`. The builder sets `agents={"implementer": persona}` when it is given (depends on 2, 4). — DoD: options carry `agents["implementer"]` with the image persona prompt, and existing tests that stub `_stage_implementer_agent` to return None still pass.
- [ ] 6. Add a source-scan guard test: every `ClaudeAgentOptions(` in `orchestrator/options.py` with `cwd=str(repo_dir)` uses `TARGET_CLONE_SETTING_SOURCES` (depends on 2). — DoD: the test passes now and fails if one site is reverted to `["project"]`.
- [ ] 7. Update the docstrings and comments that claim target-repo agents or CLAUDE.md are loaded: `options.py` (293-295, 1336-1340, 1509-1510), `_stage_implementer_agent`, and `InvestigatorOrphanedSubagent`. — DoD: a grep for `setting_sources=\["project"\]` near target-clone wording returns no stale claims.
- [ ] 8. Record the severity evidence on issue #868: whether the `["project"]` control executed the hook. Downgrade the severity if it did not, while still shipping the change. — DoD: the PR description states the observed outcome, or "not exercised" with a reason.

## Tests
- [ ] T1. Deterministic isolation test: for each affected builder, `opts.setting_sources == []` and the stub-CLI argv `--setting-sources=` holds no `project`, `user` or `local`.
- [ ] T2. Mutation: monkeypatching `options.TARGET_CLONE_SETTING_SOURCES` to `["project"]` makes T1's assertion fail. This is implemented as an `xfail(strict=True)` or `pytest.raises(AssertionError)` wrapper.
- [ ] T3. Live (opt-in): the bundled CLI in the fixture clone does not create the hook marker, and the `["project"]` control case does, or the test records that the hook does not fire even then.
- [ ] T4. Persona parser: every shipped `implementer.md` parses, the tools list matches the frontmatter, and the body is non-empty.
- [ ] T5. `build_implementer_agent_options(..., persona=defn)` exposes `agents == {"implementer": defn}`, and `persona=None` leaves `agents` None.
- [ ] T6. `_stage_implementer_agent` writes nothing under `<clone>/.claude`, still writes the refusal-marker exclude entry, and raises `SystemExit` when no template exists.
- [ ] T7. Existing `tests/test_options.py` legacy/declarative equivalence tests keep passing with both builders on `[]`.
- [ ] T8. Full `pytest` suite and the repo's lint/type checks pass.

## Rollback
Revert the PR. That restores `setting_sources=["project"]` in the four builders and restores the old
`_stage_implementer_agent`, which copies `implementer.md` into the clone. As a narrower emergency fix, set
`TARGET_CLONE_SETTING_SOURCES = ["project"]`. The programmatic `agents=` persona is harmless alongside it,
because the same name resolves to the same content. No data or gitops state needs to be undone.
