# Credential-separated, policy-mediated Bash for the model shell (852 D2/D4)

## Context

Every SDK session that `orchestrator/options.py` builds gives the model the `Bash` tool through the bundled Claude Code CLI. Bash today is audit-only. `_audit_pre_tool_use` prints the command and returns `{}`, and `_policy_hooks` only matches `mcp__.*`. Each command the model runs, including repository build, test and install scripts it does not control, inherits the CLI process environment. `_scrubbed()` already blanks `MCTL_TOKEN`, the usage- and evidence-writer tokens and their `*_FILE` pointers. It is a denylist, though, and it does not cover `GITHUB_TOKEN` or `GITHUB_TOKEN_FILE`, which every Bash-bearing builder forwards through `env={**os.environ}`. Only the type-check child in `run_implementer.py` gets an allowlisted env (`_TYPECHECK_ENV_KEEP`). In this investigator's own session (2026-11-18), model Bash had a non-empty `GITHUB_TOKEN` and a readable `GITHUB_TOKEN_FILE` in its environment.

The issue asks for an allowlist boundary at the point where the CLI spawns the shell. With it, the model shell starts without long-lived credentials, and anything that needs a credential goes through a mediated path behind the policy checkpoint. A command-text deny-list may be added for defence in depth only. Tests must prove that model Bash cannot read the credential variables, that a mutation restoring the full env fails, and that implementer push and PR creation still work. The investigation also found a residual this proposal cannot close inside the pod: a same-uid model shell can read `/proc/<ancestor>/environ` and mounted credential files. This proposal records that residual explicitly and hands it to the pod-level owner (#807 G2) instead of leaving it implied.

## User stories

- AS a platform operator I WANT model-run shell commands to start with an allowlisted environment SO THAT repository code run by the model cannot read GitHub, mctl-api or writer credentials from its env.
- AS a platform operator I WANT every credentialed operation (git push, PR create, GitHub API reads, mctl API) to run in the orchestrator process or behind an MCP tool that meets the policy checkpoint SO THAT each use of a credential is decided and recorded.
- AS a security reviewer I WANT a test that fails when the full environment is restored to the model shell SO THAT a regression cannot pass CI silently.
- AS the mctl-docs service agent I WANT an authenticated, read-only way to list sibling-repo commits that does not need `$GITHUB_TOKEN` in my shell SO THAT my scan keeps the 5000 req/h limit.

## Acceptance criteria (EARS)

- WHEN any SDK session is built through `orchestrator/options.py:_scrubbed()` THE SYSTEM SHALL set `CLAUDE_CODE_SHELL_PREFIX` in the session env to the canonical model-shell wrapper path (`/usr/local/libexec/mctl-model-shell`).
- WHEN the model runs a command through the `Bash` tool THE SYSTEM SHALL execute it under an environment that contains only variables named in `MODEL_SHELL_ENV_KEEP`, plus variables that start with an allowlisted CLI-internal prefix (`__CLAUDE_CC_`).
- WHILE a model Bash command runs THE SYSTEM SHALL keep out of its environment, with an empty value or absent, every name in `credential_files.INVENTORY`, each of their `<NAME>_FILE` pointers, `GH_TOKEN`, `GITHUB_TOKEN`, `MCTL_RUN_TOKEN_SA_TOKEN_FILE`, and any variable not on the allowlist, including a credential added to the pod in the future.
- IF the wrapper file is missing, not owned by uid 0, writable by group or other, or its content digest differs from the digest of `model_shell.render_wrapper()` THEN THE SYSTEM SHALL refuse to build the session options (raise `ModelShellUnavailable`) and not start the agent.
- WHEN any SDK session is built THE SYSTEM SHALL blank `GITHUB_TOKEN`, `GH_TOKEN`, `GITHUB_TOKEN_FILE` and `MCTL_RUN_TOKEN_SA_TOKEN_FILE` in the CLI process env as well, because the CLI does not need them, so they are not exposed through `/proc/<cli-pid>/environ`.
- WHEN a model-provider session is built (`provider` argument of `_scrubbed`) THE SYSTEM SHALL apply the same wrapper prefix and the same blanking as an Anthropic session.
- WHEN the implementer pushes a branch or opens a PR THE SYSTEM SHALL do it from the orchestrator process (`run_implementer.py` `_run` with the orchestrator's own `os.environ`, governed by the existing `github-push-*` and `github-pr-create` policy rules) and SHALL succeed exactly as before.
- WHEN the mctl-docs service agent needs GitHub commit data THE SYSTEM SHALL provide it through an in-process MCP server `github_read` (tools `mcp__github_read__list_commits` and `mcp__github_read__get_commit`). That server reads the token in-process with `read_credential("GITHUB_TOKEN")`, restricts repositories to `mctlhq/<sibling>`, bounds its output, and is decided by the policy checkpoint under a `requires_grant` rule.
- IF a `github_read` tool is called without its grant, or for a repository outside the sibling allowlist THEN THE SYSTEM SHALL deny the call and record a `POLICY_DECISION`.
- WHERE a command-text deny check is installed for Bash (references to `/proc/*/environ` or to the mounted credential paths) THE SYSTEM SHALL label it defence in depth in code and docs, and SHALL NOT be the control any test relies on for the env guarantee.
- WHEN `credential_files.RESIDUAL_BOUNDARY` is read THE SYSTEM SHALL state that env separation of the model shell is closed by #869, and name the remaining exposure and its owner (#807 G2): same-uid reads of `/proc/<ancestor>/environ` and of mounted credential files.

## Out of scope

- Pod-level isolation: running the model shell under a separate uid or container, removing credentials from the pod env (`envFrom`), and masking mounted credential files or `/proc`. In-pod, user namespaces are refused (`unshare` returns EPERM) and the process runs with `NoNewPrivs=1` and `CapEff=0`, so none of these is possible without pod-spec changes. That work is #807 G2.
- Moving the Anthropic credential out of the CLI env (for example `CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR`). It is recorded as a follow-up.
- The audit-only Bash classifier (#865). It is complementary and unchanged here.
- Changing what the policy checkpoint decides for existing `mcp__mctl__*` tools.

## Open questions

- The exact argument contract between `CLAUDE_CODE_SHELL_PREFIX` and the wrapper in the pinned CLI (claude-agent-sdk 0.2.174) has not been fully verified: one string argument or an argv. The CLI is minified. Its strings show that the prefix must be an absolute path outside the session's writable roots, and that a prefix which drops the env must keep `__CLAUDE_CC_BUN_OPTIONS` or the command fails with exit 126. Task 2 verifies the contract with the real binary before the wrapper is finalised.
- A same-uid model shell can still read `/proc/1/environ` (pod env: `CLAUDE_CODE_OAUTH_TOKEN`, `MCTL_USAGE_WRITER_TOKEN`, `MCTL_EVIDENCE_WRITER_TOKEN`), `/proc/<cli-pid>/environ` (the Anthropic credential) and the mounted files `/var/run/gh/github-token` and `/var/run/secrets/mctl-api/token`. This proposal treats that as #807 G2's pod-level residual. Please confirm that ownership, or decide whether #869 should stay open until it closes.
- The toolchain variables the target repos need are unconfirmed (for example `GOPATH`, `GOCACHE`, `GOFLAGS`, `npm_config_cache`, `CARGO_HOME`). The proposal starts from `_TYPECHECK_ENV_KEEP` plus the run-specific variables (`PATH`, `PROPOSAL_DIR`, `SIBLING_REPOS_PATH`, `INCIDENT_STATE_DIR`). Additions are cheap and reviewable, and a missing one fails the build visibly rather than silently.
- The agent pods' Argo ClusterWorkflowTemplates were not readable from this run. The pod env was inferred from `/proc/1/environ` (names and non-emptiness only), not from the gitops spec. The implementer should confirm that the list of credential names in `MODEL_SHELL_ENV_NEVER` matches those templates.
- Local-dev escape hatch: should `MCTL_MODEL_SHELL=off` exist, or should local dev install the wrapper too? The proposal adds `off`. It is honoured only when `ARGO_WORKFLOW_NAME` is unset and logs a loud warning.
