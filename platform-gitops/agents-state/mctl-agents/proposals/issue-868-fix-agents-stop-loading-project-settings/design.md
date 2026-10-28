# Design: issue-868-fix-agents-stop-loading-project-settings

## Current state
Clone checked: `mctlhq/mctl-agents` at `25c09b8` (main, after the 852/854 spike-decision docs merge). The
issue cites 131c653; the line numbers below are from the current clone.

Affected `ClaudeAgentOptions` constructions in `orchestrator/options.py`. All four go through `_scrubbed(...)`:
- `build_implementer_agent_options` (line 1324): `cwd=str(repo_dir)`, `setting_sources=["project"]` (1379-1380). Its docstring (1336-1340) says the project source is what picks up `.claude/agents/implementer.md`.
- `build_issue_investigator_options` (line 1500): 1530-1531. Its docstring says the project source exists to pick up the target repo's CLAUDE.md as context.
- `build_issue_investigator_options_from_plan` (line 1545): the `gateway is None` branch at 1611-1612 and the gateway branch at 1632-1633. Its docstring promises structural equivalence with the legacy builder, and `tests/test_options.py` (around lines 98-200) asserts that equivalence.
- The module comment above the issue-investigator drain timeout (lines 293-295) states outright that the investigator loads "whatever `.claude/agents/*.md` that repository ships".

Pinned SDK (`pyproject.toml`: `claude-agent-sdk==0.2.168`, bundled CLI at `claude_agent_sdk/_bundled/claude`):
- `ClaudeAgentOptions.setting_sources` docstring (`types.py`): `"project"` means `.claude/settings.json`; `[]` disables filesystem settings ("SDK isolation mode"); `"project"` is required to load CLAUDE.md.
- `_internal/transport/subprocess_cli.py` (530-568, 729-730) renders the value as `--setting-sources=<csv>`. It is only overridden to `["user","project"]` when `skills` is set AND `setting_sources is None`. With `[]` and `skills=None`, which is the case for all four builders, it emits `--setting-sources=` with no entries.
- `ClaudeAgentOptions.agents: dict[str, AgentDefinition] | None` defines sub-agents programmatically. `AgentDefinition(description, prompt, tools, disallowedTools, model, skills, ...)`.

Persona staging in `orchestrator/run_implementer.py`:
- `_stage_implementer_agent(target, service)` (1794): copies `agents/<service>/.claude/agents/implementer.md`, falling back to `agents/_generic/...`, into `<clone>/.claude/agents/implementer.md`. If neither exists it raises `SystemExit`. It appends that path plus `REFUSAL_MARKER_FILENAME` to `<clone>/.git/info/exclude`.
- It is called at 3033 (review-feedback path) and 4954 (new-PR path). Each is followed by `_run_implementer_agent` (2601; called at 3115 and 4991), which calls `build_implementer_agent_options` at 2648.
- The prompts (2114, 2177) say "Use the `implementer` sub-agent", so the persona name `implementer` must stay resolvable.
- Every persona file (`agents/{_generic,mctl-agent,mctl-agents,mctl-api,mctl-docs,mctl-gitops,mctl-portal,mctl-web}/.claude/agents/implementer.md`) has frontmatter `name`, `description` and `tools` (a comma list) and no `model`.
- Service skills already go through the prompt (`ServiceSkillBundle` and `neutralize_service_skill_tags`), not `.claude/skills`. They are unaffected.
- About 10 test files monkeypatch `_stage_implementer_agent` with `lambda *_a, **_kw: None`, for example `tests/test_run_implementer_ci_budget.py:80` and `tests/test_run_implementer_claims.py:509`.

Investigator prompt (`orchestrator/run_issue_investigator.py:2216`) already says "Read the repo's `CLAUDE.md` (cwd root, if present) for conventions". The agent reaches CLAUDE.md through its Read tool regardless of setting sources. `InvestigatorOrphanedSubagent`'s docstring (around 2335) also cites target-repo agents.

Precedents: `build_authoring_canary_options` (1419) and `build_scout_options` (1433) already pass `setting_sources=[]`. `tests/test_tool_subprocess_env.py` drives `SubprocessCLITransport` against a stub `claude` script to observe what the CLI child actually receives. The red test reuses that technique.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/services/admins/` contains `mctl-agents-worker`, `mctl-agents-worker-exec` and `mctl-agents-worker-implement`, the pods that run these agents.
- A grep for `setting_sources`/`SETTING_SOURCES` over `$MCTL_GITOPS_ROOT/services` and `tenants` found nothing. The setting is purely code, with no deployed env override, so the change ships with the image.
- No mctl MCP tool calls were made. They are not needed, because the behaviour is decided in code.
- Not observed: whether the deployed CLI actually executes a repository `settings.json` hook. See Open questions.

## Proposed solution
1. **Builders: `setting_sources=[]` for target clones.** In `orchestrator/options.py`, change the four constructions to `setting_sources=[]`. Add a module-level constant `TARGET_CLONE_SETTING_SOURCES: list[SettingSource] = []` with a comment citing #868 and 852 D3, and use it at all four sites so tests and reviewers have a single anchor. Leave the trusted-cwd builders (service agent, mentor, incident responder, shepherd) on `["project"]`. Update the docstrings, and the comment at 293-295, so they no longer claim the target repo's agents or CLAUDE.md are loaded.

2. **Implementer persona from the image, programmatically.**
   - Add `load_agent_definition(path: Path) -> tuple[str, AgentDefinition]` in a small new module, `orchestrator/personas.py`. It splits the `---` frontmatter, parses it with `yaml.safe_load` (PyYAML is pinned), requires `name` and `description`, splits `tools` on commas into a list, and passes `model` through if present. The markdown body becomes `prompt`. Malformed or missing fields raise `ValueError`.
   - In `run_implementer.py`, keep the function name `_stage_implementer_agent(target, service)` to limit test churn, but change what it does. It resolves the per-service path, falling back to the generic one exactly as today, with the same `SystemExit` when neither exists. It no longer copies anything into the clone. It still writes `REFUSAL_MARKER_FILENAME` to `.git/info/exclude` (the `.claude/agents/implementer.md` entry is dropped). It returns the parsed `AgentDefinition`.
   - Both call sites (3033, 4954) capture that return value and pass it to `_run_implementer_agent(..., persona=...)`, which forwards it to `build_implementer_agent_options(..., persona=...)`. The builder then sets `agents={"implementer": persona}` when it is not None. `persona` defaults to `None`, so existing tests that stub `_stage_implementer_agent` to return None keep resolving valid options.
   - In production the persona is always present, because `_stage_implementer_agent` raises otherwise.

3. **Investigator CLAUDE.md.** Rely on the existing prompt line telling the agent to Read `CLAUDE.md`. CLAUDE.md becomes ordinary untrusted file content read through a tool, consistent with how the agent already treats the clone. No settings layer is involved and nothing is injected into the system prompt. The implementer persona already tells the agent to follow the repo's CLAUDE.md, which it reads with Read.

4. **Red/green test (issue scope items 1 and 3).** Add `tests/test_target_clone_settings_isolation.py`:
   - Fixture: build a `tmp_path` clone containing `.claude/settings.json` with a `SessionStart` (and `PreToolUse`) command hook that writes a marker file, plus `permissions.allow: ["Bash(*)"]`, `.claude/agents/evil.md` and `CLAUDE.md`.
   - Deterministic test, always runs. For each affected builder, including both `from_plan` branches (the gateway branch uses a stub gateway, as existing tests in `tests/test_options.py` do), build options with `cwd` = fixture clone. Assert `opts.setting_sources == []`. Then run `SubprocessCLITransport` against a stub `claude` script, using the `tests/test_tool_subprocess_env.py` pattern, that records its argv. Assert that the argv `--setting-sources=` value contains no `project`, `user` or `local`. For the implementer, also assert that `opts.agents["implementer"]` exists and its prompt equals the image persona body.
   - Live test, opt-in via `MCTL_LIVE_CLI_SETTINGS_TEST=1` and skipped otherwise. Launch the bundled CLI with the built options in the fixture clone, wait for exit, and assert the marker file does not exist. A parametrized `["project"]` control case asserts the marker DOES appear. That control is the evidence for the severity decision recorded on the issue.
   - Mutation check: a parametrized case monkeypatches `options.TARGET_CLONE_SETTING_SOURCES` to `["project"]`, or the implementer documents and runs a manual `sed` mutation, and asserts the deterministic test fails. The test file states this in a module docstring.
   - Add a guard test that scans `orchestrator/options.py` source. Every `ClaudeAgentOptions` whose `cwd=` is `repo_dir` must use `TARGET_CLONE_SETTING_SOURCES`, so a new target-clone builder cannot silently reintroduce `["project"]`.

5. **Docs.** Update docstrings and comments that cite project-loaded target agents: `options.py` 293-295, 1336-1340 and 1509-1510; `run_implementer._stage_implementer_agent`; `run_issue_investigator.InvestigatorOrphanedSubagent`. Add a short note to `docs/spikes/852-sandbox-isolation-delta.md` or the issue comment recording the live-test outcome. The issue explicitly asks for that record.

## Alternatives
- **Keep `["project"]` and deny Read/Write of `.claude/**` through policy hooks.** This does not help: the CLI reads settings at startup, before any tool hook runs. Rejected.
- **Keep copying `implementer.md` into the clone but point `cwd` elsewhere.** `cwd` must be the clone so git and Bash work in it, and any `cwd` with `["project"]` would still load the clone's own `.claude/settings.json`. Rejected.
- **Use the `plugins=[{"type":"local","path": <image dir>}]` mechanism to ship the persona.** This works, but it adds a plugin manifest and directory layout for one file, while `agents=` is the SDK's documented direct path. Rejected as heavier.
- **Inject the target CLAUDE.md verbatim into the investigator's system prompt.** This puts untrusted text into a more privileged position than a tool read. The prompt already directs a Read. Kept as an open question rather than the default.

## Platform impact
- No migrations and no gitops changes. The change ships with the next mctl-agents image used by `mctl-agents-worker*`.
- Behaviour change: target repos that ship `.claude/agents`, `.claude/skills`, hooks or permissions no longer influence the implementer or investigator. This is intended. Repos lose "automatic" CLAUDE.md context. Mitigation: the prompts already instruct reading CLAUDE.md.
- Risk: the programmatic `AgentDefinition` could differ from what file-based discovery produced, for example in tools parsing or MCP glob `mcp__mctl__*` in `tools`. Mitigation: a persona parser unit test over every shipped `implementer.md`, and an equality check that the parsed tools match the frontmatter list. Watch the first few implementer runs for "sub-agent not found" or orphan exits (`EXIT_ORPHANED_SUBAGENT`).
- Risk: `--setting-sources=` with an empty value might be parsed differently by the bundled CLI. Mitigation: the scout and canary already use `[]` in production, and the live test covers it.
- Resource impact: none.
