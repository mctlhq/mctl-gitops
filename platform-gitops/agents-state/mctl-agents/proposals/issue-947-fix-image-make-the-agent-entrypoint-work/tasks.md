# Tasks: issue-947-fix-image-make-the-agent-entrypoint-work

- [ ] 1. Write the entrypoint read-only test first (`tests/test_entrypoint_readonly.py`). It copies `agents/` into a temp app root, makes it read-only, rewrites `/app` in a copy of the script, runs it with `STATE_DIR` set and `sh -c 'echo started'`, and compares before/after snapshots of the app tree. Include the pre-change script body as a fixture. — DoD: run against the current `entrypoint.sh`, the test fails (non-zero exit or snapshot diff). Skipped when the test process runs as root.
- [ ] 2. Add `agent_state_root()`, `service_inbox_dir()`, `service_proposals_dir()`, `mentor_digest_dir()` and `ensure_dir()` to `config/settings.py`. They read `STATE_DIR` at call time and fall back to `AGENTS_DIR`. — DoD: unit tests show the `STATE_DIR` set and unset paths, and that the unset paths equal today's `AGENTS_DIR/<svc>/inbox`, `AGENTS_DIR/<svc>/proposals` and `MENTOR_DIR/digest`.
- [ ] 3. Reduce `entrypoint.sh` to `set -e` + `exec "$@"` with an explanatory header (depends on 1). — DoD: the test from task 1 passes. No `rm`, `ln` or `mkdir` remains in the script.
- [ ] 4. Service agent (depends on 2): in `orchestrator/run_service_agent.py`, resolve and create the state dirs and replace `PROMPT` with `build_prompt(inbox_dir, proposals_dir)`, which uses absolute paths. Extend `orchestrator/options.py::build_service_agent_options` to add those dirs to `add_dirs` while keeping `cwd=service_dir`. — DoD: `tests/test_run_service_agent.py` and `tests/test_options.py` are updated and green, and with `STATE_DIR` set the prompt and `add_dirs` name `STATE_DIR/<svc>/{inbox,proposals}`.
- [ ] 5. Mentor (depends on 2): in `orchestrator/run_mentor.py`, rotate `mentor_digest_dir()` and make `build_prompt()` list the absolute proposals dirs of `mentor_services()` only (services in `SERVICES` with a baked `agents/<svc>/` dir; today's scope) and the digest path. In `options.build_mentor_options`, add `agent_state_root()` to `add_dirs`. — DoD: `tests/test_run_mentor.py` is extended. `_rotate_old_digests` runs on `STATE_DIR/_mentor/digest` when it is set and on `agents/_mentor/digest` when it is not.
- [ ] 6. Reword the relative `inbox/`, `proposals/` and `_mentor/digest/` references in `agents/<svc>/CLAUDE.md`, `agents/<svc>/.claude/agents/{researcher,analyst,spec-writer}.md` and `agents/_mentor/CLAUDE.md` to point at the absolute paths given in the task (depends on 4, 5). Leave `agents/_manifests/*/agent.yaml` untouched. — DoD: `uv run --locked python tools/check_binding_hash.py` exits 0, or the re-pin runbook is followed and linked in the PR.
- [ ] 7. Update the `Dockerfile` comment above `COPY agents/`. Add a REQUIRED smoke to `.github/workflows/pr-validation.yml`: `docker run --read-only --tmpfs /tmp -e STATE_DIR=/tmp/s "$IMAGE" python -c "import orchestrator.run_all"`, so the real image starts through `/entrypoint.sh` on a read-only root and import-time writes surface too (the unit test in task 1 skips under root) (depends on 3). — DoD: the image builds and the smoke passes in CI; with the old entrypoint it fails.
- [ ] 8. After merge, let release-please cut the release, then comment the released image tag (`ghcr.io/mctlhq/mctl-agents:<version>`) on mctlhq/mctl-gitops#2290 (depends on 1-7). — DoD: the comment with the version exists on #2290.

## Tests
- [ ] T1. `tests/test_entrypoint_readonly.py`: with `STATE_DIR` set, the new entrypoint execs the command against a read-only app copy without changing it. The pre-change script fails the same check.
- [ ] T2. Resolver unit tests in `tests/test_settings_state_dirs.py` (or an existing settings test): set/unset/empty `STATE_DIR`.
- [ ] T3. `tests/test_run_service_agent.py`: the prompt contains the resolved absolute inbox and proposals paths, the directories are created under `STATE_DIR` (tmp_path), and nothing is created under a monkeypatched `AGENTS_DIR`.
- [ ] T4. `tests/test_run_mentor.py`: the digest rotation and prompt target `STATE_DIR/_mentor/digest`; the prompt lists `STATE_DIR/<svc>/proposals` exactly for `mentor_services()`, and does NOT list a service from `SERVICES` without a baked `agents/<svc>/` dir (for example `mctl-telegram`), even when `STATE_DIR/mctl-telegram/proposals/` exists in the fixture.
- [ ] T5. `tests/test_options.py`: `add_dirs` for the service agent and mentor include the state dirs, and `cwd` is unchanged.
- [ ] T6. Full suite `uv run --locked pytest` stays green, including the investigator, implementer, shepherd, reconcile and pr_adoption tests.

## Rollback
Revert the PR and let release-please publish a new patch, or keep the CWFTs pinned to
`ghcr.io/mctlhq/mctl-agents:1.112.3`. The `agents-state` layout is unchanged, so no data
migration is needed either way. Do not enable `readOnlyRootFilesystem` in
mctl-gitops#2290 until the released version has completed one `RUN_MODE=full` run and
committed inbox, proposals and digest output under `agents-state/`.
