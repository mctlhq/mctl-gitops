# Design: issue-869-feat-agents-credential-separated-policy

## Current state

**Hooks.** In `orchestrator/options.py`, `_command_audit_hooks()` registers `_audit_pre_tool_use` on `PreToolUse` with the matcher `Bash`. The hook prints `AUDIT tool=Bash cmd=...` and returns `{}`. `_policy_hooks()` puts the policy checkpoint (`_PolicyCheckpointHook`) on the matcher `mcp__.*` only. The other Bash hooks are `_ci_log_guard_hook` (a command-text deny for unbounded CI-log fetches, CI-remediation work classes only) and `_deadline_guard_hook` (a time budget). Neither concerns credentials.

**Session env.** Every builder passes its `ClaudeAgentOptions` through `_scrubbed()`. `tests/test_usage_ledger.py` enforces that structurally. `_scrubbed` blanks `MCTL_TOKEN` (`agent_env_without_mctl_token`), the usage- and evidence-writer tokens, and the `*_FILE` pointers of every `IN_PROCESS` credential (`credential_files.file_env_names()`). It then adds the single active Anthropic credential (`auth.session_auth_env()`). This is a denylist. The SDK layers `options.env` over the inherited process env, so any name `_scrubbed` does not blank reaches the CLI.

**GITHUB_TOKEN forwarding.** `build_service_agent_options`, `build_implementer_agent_options`, `build_issue_investigator_options`, `build_issue_investigator_options_from_plan` and `build_incident_responder_options` all start from `env={**os.environ}`. The docstrings say so explicitly: "GITHUB_TOKEN is forwarded from the parent env". `github_token.refresh_github_token()` writes the fresh token into the orchestrator's `os.environ` so its own `_run` gh/git subprocesses inherit it. As a side effect, every later CLI child, and so model Bash, gets it too.

**Credential inventory.** `orchestrator/credential_files.py` classifies `GITHUB_TOKEN` as `SUBPROCESS_ENV` and the Anthropic keys as `CLI_ENV`. Its `RESIDUAL_BOUNDARY` already says "mctlhq/mctl-agents#869 owns that boundary". `tests/test_credential_files.py:187` asserts `"#869" in cf.RESIDUAL_BOUNDARY`.

**Existing allowlist precedent.** `run_implementer.py:_TYPECHECK_ENV_KEEP` and `_typecheck_env()` build an allowlisted env for the pre-push type check: HOME, LANG, LC_ALL, TMPDIR, UV_*, SSL_CERT_*, the proxy variables, and PATH without `/app/.venv/bin`.

**Credentialed operations are already mediated, except one.**
- Implementer clone, push and PR creation run in the Python wrapper (`run_implementer.py` `_clone_repo` via `gh repo clone`, push and `gh pr create` via `_run`). Each is decided by `policy_checkpoint` rules `github-push-new-branch`, `github-push-with-lease` and `github-pr-create`. The builder docstring says "the agent commits, never pushes".
- CI failure logs are fetched in-process (`ci_checks.fetch_failure_logs`). The prompt tells the model not to fetch more.
- The investigator's issue read, clone and comment are done by the wrapper (builder docstring).
- mctl-api access goes through the `mctl` HTTP MCP server. Its bearer is in the server config (`mctl_mcp_config`), not the env, and it is decided by the checkpoint rules `mctl-mcp-*`.
- The exception is the mctl-docs service agent's skill `agents/mctl-docs/.claude/skills/scan-sibling-commits/SKILL.md:73`. It runs `curl -H "Authorization: Bearer $GITHUB_TOKEN"` from model Bash, and `agents/mctl-docs/CLAUDE.md:62` documents that dependency.

**In-process MCP precedent.** `capability_gateway.CapabilityGateway.sdk_server()` serves tools through `create_sdk_mcp_server(name="capability")` from the orchestrator process. Those tools are `mcp__capability__*`, so `_policy_hooks` sees them.

**CLI support.** The bundled CLI (`claude_agent_sdk/_bundled/claude`, sdk 0.2.174) reads `CLAUDE_CODE_SHELL_PREFIX`. Its strings show three things:
- It only accepts an absolute path, and omits a prefix that lies inside the session's writable roots ("this machine cannot vouch for that wrapper").
- It wraps model shell commands with the prefix.
- It passes `__CLAUDE_CC_BUN_OPTIONS` through the env. A prefix that drops the environment makes the command exit 126 ("a CLAUDE_CODE_SHELL_PREFIX that drops the environment, can cause this").

It also knows `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR` and `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR`, which are not used here.

**Image.** `Dockerfile`: `/app` is owned by `app` (the session uid). `/usr/local/bin` is root-owned. `USER app:app` is set at line 156. `~/.gitconfig` sets `credential.https://github.com.helper=!/usr/bin/gh auth git-credential`, so git in model Bash authenticates from whatever `GITHUB_TOKEN` it sees.

Deployed state checked:
- Live process observation inside this investigator run (an `mctl-agents` investigate pod, argo workflow). Only names and empty/non-empty were read, never values.
  - Model Bash env: `GITHUB_TOKEN` non-empty, `GITHUB_TOKEN_FILE` set and readable (`/var/run/gh/github-token`). `MCTL_TOKEN`, `MCTL_USAGE_WRITER_TOKEN`, `MCTL_EVIDENCE_WRITER_TOKEN` and the IN_PROCESS `*_FILE` vars are empty, which confirms that today's `_scrubbed` works for those. `MCTL_RUN_TOKEN_SA_TOKEN_FILE` is non-empty and its file `/var/run/secrets/mctl-api/token` is readable. `CLAUDE_CODE_SHELL_PREFIX` is unset.
  - `/proc/<cli-pid>/environ` is readable from model Bash: `CLAUDE_CODE_OAUTH_TOKEN` non-empty, `GITHUB_TOKEN` non-empty.
  - `/proc/<orchestrator-python-pid>/environ` and `/proc/1/environ` (argoexec) are readable: `MCTL_USAGE_WRITER_TOKEN`, `MCTL_EVIDENCE_WRITER_TOKEN` and `CLAUDE_CODE_OAUTH_TOKEN` are non-empty. These are pod-level env values (#807 G2).
  - `unshare --user --map-root-user --pid ...` fails with "Operation not permitted". `/proc/self/status` shows `CapEff=0`, `NoNewPrivs=1`, `Seccomp=2`. In-pod namespace or uid separation is therefore not available.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker/values.yaml`: the Temporal worker gets `MCTL_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` and `GITHUB_TOKEN` via `envFrom: secretRef mctl-agents-worker-secrets`, plus `GITHUB_TOKEN_FILE` as a mounted file. This confirms credentials in pod env at the worker as well.
- The Argo ClusterWorkflowTemplates of the agent pods (`platform-gitops/argo-workflows/...`) are not in the directories this run can read. The pod spec was inferred from `/proc/1/environ` only. That gap is recorded under Open questions.
- mctl MCP tools were not needed for this code-level change and were not called.

## Proposed solution

### 1. `orchestrator/model_shell.py` (new, stdlib only)

- `MODEL_SHELL_WRAPPER_PATH = "/usr/local/libexec/mctl-model-shell"`.
- `BASE_CHILD_ENV_KEEP`: the current `_TYPECHECK_ENV_KEEP` tuple, moved here. `run_implementer._TYPECHECK_ENV_KEEP` becomes an alias, so behaviour is unchanged.
- `MODEL_SHELL_ENV_KEEP = BASE_CHILD_ENV_KEEP + ("PATH", "USER", "LOGNAME", "SHELL", "TERM", "TZ", "PWD", "PROPOSAL_DIR", "SIBLING_REPOS_PATH", "INCIDENT_STATE_DIR", "GOPATH", "GOCACHE", "GOMODCACHE", "GOFLAGS", "npm_config_cache", "COREPACK_ENABLE_AUTO_PIN", "CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")`. The final list is set in task 2 against what the CLI requires. Every additional name is reviewed as "not a credential".
- `MODEL_SHELL_ENV_KEEP_PREFIXES = ("__CLAUDE_CC_",)`, the CLI handshake variables such as `__CLAUDE_CC_BUN_OPTIONS`.
- `MODEL_SHELL_ENV_NEVER`: every `credential_files.INVENTORY` name and its `_FILE`, plus `GH_TOKEN`, `GITHUB_TOKEN`, `MCTL_RUN_TOKEN_SA_TOKEN_FILE`, `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`, `CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR` and `CLAUDE_CODE_MESSAGING_TOKEN`. An import-time assertion requires that it is disjoint from the keep list and matches no keep prefix. This is an invariant check, not the control. The control is the allowlist.
- `render_wrapper() -> str`: a POSIX `sh` script with the allowlist baked in as literals. It builds `env -i NAME=value ...` only for allowlisted names that are set, adds any `__CLAUDE_CC_*`, and `exec`s the wrapped command. Task 2 fixes the argument handling to match the pinned CLI's contract, `exec env -i ... "$@"` or `... /bin/bash -c "$1"`. The script never prints values.
- `wrapper_digest()`: the sha256 of `render_wrapper()`.
- `verify_wrapper(path=MODEL_SHELL_WRAPPER_PATH)`: `os.stat` checks `st_uid == 0` and `mode & 0o022 == 0`, and the content digest must equal `wrapper_digest()`. Any failure raises `ModelShellUnavailable` with a reason that is a name, never content.
- `model_shell_session_env() -> dict[str, str]`: returns `{"CLAUDE_CODE_SHELL_PREFIX": MODEL_SHELL_WRAPPER_PATH, "GITHUB_TOKEN": "", "GH_TOKEN": "", "GITHUB_TOKEN_FILE": "", "MCTL_RUN_TOKEN_SA_TOKEN_FILE": ""}` after calling `verify_wrapper()`. Blanking `GITHUB_TOKEN` in the CLI env shrinks what `/proc/<cli-pid>/environ` exposes to the Anthropic credential alone, which the CLI needs.
- `mode()`: reads `MCTL_MODEL_SHELL` (default `enforce`). `off` is honoured only when `ARGO_WORKFLOW_NAME` is unset (local dev). It prints `WARNING model shell env separation OFF`, and the session env is then left as today.
- `python -m orchestrator.model_shell render` writes the wrapper to stdout, for the Dockerfile.

### 2. `_scrubbed()` applies it to every session

After the existing blanking and before the auth env:

```
options.env = {**options.env, **model_shell.model_shell_session_env()}
```

For the provider branch, the same dict is merged into the env that `provider_session_env` returns. It is applied unconditionally, including to builders that do not grant Bash (mentor, scout, canary). That is harmless and makes "every session" the invariant. The builder docstrings that say "GITHUB_TOKEN is forwarded" are corrected.

The orchestrator process keeps `GITHUB_TOKEN` in its own `os.environ`, so `_run` push, PR and clone keep working through the existing policy-checked path. Only the CLI child and the model shell lose it.

### 3. Dockerfile

Before `USER app:app`, as root, after `COPY orchestrator/` and the venv sync:

```
RUN install -d -m 0755 /usr/local/libexec \
 && /app/.venv/bin/python -m orchestrator.model_shell render > /usr/local/libexec/mctl-model-shell \
 && chown root:root /usr/local/libexec/mctl-model-shell && chmod 0555 /usr/local/libexec/mctl-model-shell
```

The wrapper is root-owned and lives outside every session writable root. The model cannot rewrite it, even though `/app` is app-owned. If someone edits `/app/orchestrator/model_shell.py` at runtime, the wrapper does not change. The digest check in the next session then fails closed instead of trusting the edit.

### 4. Mediated GitHub read for the one Bash consumer

`orchestrator/github_read_tools.py` (new) provides `github_read_sdk_server()` via `create_sdk_mcp_server(name="github_read")`, following the `capability_gateway` pattern. It has two tools:

- `list_commits(repo, since?, path?, per_page<=100)`
- `get_commit(repo, sha)`

`repo` must be `mctlhq/<name>`, with `<name>` in `options._SIBLING_REPOS`. The token is read per call with `credential_files.read_credential("GITHUB_TOKEN")` and sent only as a request header. Results are trimmed to sha, author date, message and changed file paths, and bounded in characters. Errors carry the status code and never the token.

`build_service_agent_options` adds the server to `mcp_servers` and `mcp__github_read__*` to `allowed_tools` and the checkpoint grants. `policy_checkpoint` gets `Rule("github-read-mcp", MCP_TOOL_CALL, "mcp__github_read__*", ALLOW, requires_grant=True)`. `agents/mctl-docs/.claude/skills/scan-sibling-commits/SKILL.md` and `agents/mctl-docs/CLAUDE.md` replace the `curl ... $GITHUB_TOKEN` fallback with these tools. Unauthenticated `WebFetch` remains the degraded path.

No other builder needs a mediated helper. Push, PR, clone and CI logs are already in-process, and mctl goes through MCP.

### 5. Defence in depth (not the control)

`_credential_path_guard_hook`, a Bash `PreToolUse` deny composed beside `_command_audit_hooks()` in every Bash-bearing builder. It denies commands that reference `/proc/` together with `environ`, `/var/run/gh/`, `/var/run/secrets/`, or the value of `GITHUB_TOKEN_FILE` or `MCTL_RUN_TOKEN_SA_TOKEN_FILE`, using the existing `_normalize_shell_command`. The docstring and tests label it defence in depth. It is trivially bypassable (for example by assembling a string at runtime) and no env-guarantee test depends on it.

### 6. Residual boundary made explicit

`credential_files.RESIDUAL_BOUNDARY` is rewritten to say:

- The model shell env is allowlisted (#869).
- Remaining: a same-uid model shell can read `/proc/<ancestor>/environ` (pod env and the CLI's Anthropic credential) and mounted credential files. Closing that needs pod-level separation, owned by mctlhq/mctl-agents#807 G2.

`auth.session_auth_env` docstring is updated accordingly. `tests/test_credential_files.py:187` is changed to assert both `#869` and `#807` in the text.

## Alternatives

1. **Rewrite every Bash command in the PreToolUse hook (`updatedInput`) to `mctl-model-shell -c '<cmd>'`.** This keeps the control in code we own, but it nests the user command inside the CLI's own shell wrapper, which already runs with the full env. It also breaks the CLI's cwd and env tracking between calls, and it depends on quoting being exactly right. The issue itself says the separation must happen at the spawn boundary, not in the hook alone. Dropped as the primary mechanism. The shell-prefix variable is the CLI's own spawn boundary.
2. **Strip credentials from the CLI process env only (extend the `_scrubbed` denylist).** This is necessary (task 3 does it for `GITHUB_TOKEN`), but not sufficient. The CLI must hold the Anthropic credential, which a denylist on the CLI env cannot remove from the shell, and a denylist does not cover future credentials. Kept as a complement, not as the control.
3. **Run model Bash in a namespace sandbox (bubblewrap or `unshare`) or under a separate uid.** This would also close `/proc` and file reads, but it was observed to be impossible in the current pod (EPERM on user namespaces, `NoNewPrivs=1`, `CapEff=0`). It needs pod-spec changes and is deferred to #807 G2.
4. **Command-text deny-list as the control.** Rejected by the issue and by construction, since shell text can be obfuscated. It is used only as task 5's defence in depth.

## Platform impact

- **Migrations:** none. The image changes because the Dockerfile adds the wrapper. No gitops or pod-spec change is required.
- **Backward compatibility:** model Bash loses non-allowlisted variables. A build that relied on an unlisted variable (for example a toolchain cache var) fails visibly. The mitigation is to start from a generous non-secret list (task 2), plus a live shadow run per Bash-bearing agent (task 9). mctl-docs moves from `curl $GITHUB_TOKEN` to `mcp__github_read__*`. Its unauthenticated fallback is unchanged.
- **Fail-closed risk:** if the wrapper is missing or altered, sessions refuse to start. That is intentional in pods. Local dev uses `MCTL_MODEL_SHELL=off`.
- **CLI upgrade risk:** a claude-agent-sdk bump could change prefix semantics. T6 pins the CLI contract strings and T2 runs the wrapper as the CLI does, so a bump that breaks it fails CI.
- **Resources:** one extra `exec` of `env` per Bash call, which is negligible. The `github_read` tools use the same 5000/h quota the curl path used.
- **Security delta:** closes the direct-env path for `GITHUB_TOKEN` and any future pod credential, and removes `GITHUB_TOKEN` from `/proc/<cli-pid>/environ`. It does not close the `/proc/1/environ` and mounted-file paths, which are explicitly recorded as #807 G2.
