# Tasks: issue-869-feat-agents-credential-separated-policy

- [ ] 1. Add `orchestrator/model_shell.py`. — DoD:
  - The module has `MODEL_SHELL_WRAPPER_PATH`, `BASE_CHILD_ENV_KEEP` (moved from `run_implementer._TYPECHECK_ENV_KEEP`, which becomes an alias), `MODEL_SHELL_ENV_KEEP`, `MODEL_SHELL_ENV_KEEP_PREFIXES = ("__CLAUDE_CC_",)`, `MODEL_SHELL_ENV_NEVER`, `render_wrapper()`, `wrapper_digest()`, `verify_wrapper()`, `model_shell_session_env()`, `mode()`, `ModelShellUnavailable` and a `render` CLI entry point.
  - It is stdlib only.
  - The import-time disjointness assertion between keep and never is in place.
- [ ] 2. Verify the `CLAUDE_CODE_SHELL_PREFIX` contract of the pinned CLI (claude-agent-sdk 0.2.174) and finalise the wrapper (depends on 1). — DoD:
  - The argument shape the CLI passes to the prefix (one string or an argv) is recorded in the module docstring.
  - The required CLI-internal variables are recorded there too. `__CLAUDE_CC_BUN_OPTIONS` at minimum.
  - `render_wrapper()` handles that shape.
  - The final `MODEL_SHELL_ENV_KEEP` is listed there, each entry justified as non-secret.
- [ ] 3. Wire it into `orchestrator/options.py:_scrubbed()` for both the Anthropic and the provider branch (depends on 1). — DoD:
  - Every built session env has `CLAUDE_CODE_SHELL_PREFIX == MODEL_SHELL_WRAPPER_PATH`.
  - In every built session env, `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN_FILE` and `MCTL_RUN_TOKEN_SA_TOKEN_FILE` are `""`.
  - `ModelShellUnavailable` propagates.
  - The builder docstrings that claim "GITHUB_TOKEN is forwarded" are corrected.
- [ ] 4. Dockerfile: render the wrapper as root into `/usr/local/libexec/mctl-model-shell` (root:root, 0555) before `USER app:app` (depends on 2). — DoD: in the built image, `stat -c '%u %a'` reports `0 555`, and `python -c "from orchestrator.model_shell import verify_wrapper; verify_wrapper()"` succeeds as `app`.
- [ ] 5. Add `orchestrator/github_read_tools.py` with the `github_read` SDK MCP server (`list_commits`, `get_commit`). — DoD:
  - `repo` is restricted to `mctlhq/` plus a name in `options._SIBLING_REPOS`.
  - The token is read in-process via `read_credential("GITHUB_TOKEN")`.
  - Output is bounded.
  - Errors never contain the token.
- [ ] 6. Wire `github_read` into the service agent and the policy (depends on 5). — DoD:
  - `build_service_agent_options` registers the server and adds `mcp__github_read__*` to `allowed_tools` and the grants.
  - `policy_checkpoint` adds `Rule("github-read-mcp", MCP_TOOL_CALL, "mcp__github_read__*", ALLOW, requires_grant=True)`.
  - `agents/mctl-docs/.claude/skills/scan-sibling-commits/SKILL.md` and `agents/mctl-docs/CLAUDE.md` no longer reference `$GITHUB_TOKEN`. They use the tools, and unauthenticated WebFetch stays as the fallback.
- [ ] 7. Add the defence-in-depth `_credential_path_guard_hook` (Bash PreToolUse deny for `/proc/*/environ` and the mounted credential paths). Compose it with `_command_audit_hooks()` in every Bash-bearing builder. — DoD:
  - The docstring says "defence in depth, not the control".
  - It denies via the existing `_deny()`.
  - `subagent_wait` drainability is unchanged.
- [ ] 8. Rewrite `credential_files.RESIDUAL_BOUNDARY` and the `auth.session_auth_env` docstring (depends on 3). — DoD:
  - The text states that the model shell env is allowlisted (#869).
  - It names the remaining `/proc/<ancestor>/environ` and mounted-file exposure, owned by mctlhq/mctl-agents#807 G2.
  - `tests/test_credential_files.py` asserts both issue numbers.
- [ ] 9. Live shadow verification (depends on 3, 4, 6), an operator step on the released image. — DoD:
  - One investigator run, one implementer run (review work class) and one mctl-docs service-agent run complete normally.
  - The implementer opens its PR.
  - A shadow-only prompt line that runs `env | cut -d= -f1` in each shows no name outside the allowlist.
  - The run logs show `AUDIT tool=Bash` lines with no `ModelShellUnavailable`.

## Tests

- [ ] T1. `tests/test_model_shell.py::test_wrapper_strips_credentials`. — Steps:
  - Write `render_wrapper()` to a tmp file, mode 0555.
  - Run it as the CLI would (the shape from task 2), with a parent env containing every `INVENTORY` name, its `_FILE`, `GH_TOKEN`, `GITHUB_TOKEN`, `MCTL_RUN_TOKEN_SA_TOKEN_FILE` and a novel `ACME_FUTURE_SECRET`, each with a sentinel value, and with the command `env`.
  - Assert that no sentinel value and no non-allowlisted name appears in the output.
  - Assert that `PATH`, `HOME` and `__CLAUDE_CC_BUN_OPTIONS` survive.
- [ ] T2. Mutation guard `test_full_env_wrapper_fails`. — Steps:
  - Run T1's assertion helper (`assert_model_shell_env_clean(wrapper_path)`) against a pass-through wrapper (`exec "$@"`) and assert that it raises.
  - Assert that `verify_wrapper()` on that file raises `ModelShellUnavailable` (digest mismatch).
  - Monkeypatch `model_shell.render_wrapper` to the pass-through and assert that the helper flags it.
  - Restoring the full env must fail the suite.
- [ ] T3. `tests/test_options.py`: for every `build_*_options` function (enumerated by name so a new builder is covered), with `GITHUB_TOKEN`, `GH_TOKEN` and `GITHUB_TOKEN_FILE` set in `os.environ` and `verify_wrapper` stubbed OK, assert that `options.env["CLAUDE_CODE_SHELL_PREFIX"] == MODEL_SHELL_WRAPPER_PATH` and that the credential names are `""`. Repeat for the provider branch of `_scrubbed`.
- [ ] T4. Fail-closed cases: the wrapper is absent, app-owned (simulated `st_uid != 0`), group- or other-writable, or has a content mismatch. In each case the builder raises `ModelShellUnavailable`. `MCTL_MODEL_SHELL=off` is ignored while `ARGO_WORKFLOW_NAME` is set.
- [ ] T5. Invariants:
  - `MODEL_SHELL_ENV_KEEP` and `MODEL_SHELL_ENV_NEVER` are disjoint.
  - No never-name matches a keep prefix.
  - Every `credential_files.INVENTORY` name and its `_FILE` is in never.
  - No keep name matches `(?i)token|secret|key|password` except reviewed exceptions listed in the test.
- [ ] T6. CLI pin guard: the bundled `claude_agent_sdk/_bundled/claude` contains `CLAUDE_CODE_SHELL_PREFIX` and `__CLAUDE_CC_BUN_OPTIONS`. Skipped with a reason, not passed, when the binary is absent.
- [ ] T7. Implementer flows: existing push and PR tests in `tests/` still pass. A new test asserts that after `build_implementer_agent_options(...)` the orchestrator's `os.environ["GITHUB_TOKEN"]` is untouched and that `_run(["git", "push", ...])` (mocked `subprocess.run`) inherits it. Only the session env is blank.
- [ ] T8. `github_read`:
  - A repo outside `mctlhq/<sibling>` is rejected.
  - The output is bounded.
  - The token never appears in the result or the error.
  - Without the grant, `_PolicyCheckpointHook` denies `mcp__github_read__list_commits`. With it, the call is allowed.
- [ ] T9. Defence-in-depth hook: denies `cat /proc/1/environ` and `cat /var/run/gh/github-token`, and allows `pytest`. The test docstring states that it is not the env control.
- [ ] T10. `tests/test_usage_ledger.py`'s structural guard still passes, since every `ClaudeAgentOptions(...)` still goes through `_scrubbed`.

## Rollback

- Revert the PR. This restores `_scrubbed()`, the builders and `credential_files`/`auth` docstrings, removes `model_shell.py`, `github_read_tools.py`, the policy rule and the hook, and restores the mctl-docs skill text. Rebuild and release the image. No state, gitops or pod-spec change needs undoing.
- If an image is already deployed and a session refuses to start (`ModelShellUnavailable`), or a target build breaks for lack of an env var, the fast path is to pin the previous mctl-agents image or release. `MCTL_MODEL_SHELL=off` is deliberately ignored in Argo pods and is not a production rollback switch.
