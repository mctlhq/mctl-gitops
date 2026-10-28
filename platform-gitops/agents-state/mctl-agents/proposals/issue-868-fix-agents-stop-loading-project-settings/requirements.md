# Stop loading project settings from target-repository clones (852 D3)

## Amendment A (2026-10-28, requested by the owner before approval)
- A1. MCP isolation. The pinned SDK does not document `setting_sources` as governing a clone's `.mcp.json`.
  On CLI 2.1.301, `[]` happens to stop it, but a CLI bump could change that. The documented switch is
  `ClaudeAgentOptions.strict_mcp_config` (`--strict-mcp-config`), and today only the gateway branch of
  `build_issue_investigator_options_from_plan` sets it. All four target-clone constructions now set it, through one
  constant.
- A2. The tests cover `.mcp.json`. The fixture clone declares a stdio server that writes a marker. The argv test
  asserts `--strict-mcp-config`, and the mutation test and the source guard cover the new constant.
- A3. The severity question is answered (see design.md, "Probe results"). Under today's `["project"]`, a clone's
  `SessionStart` hook and a clone's `.mcp.json` server both execute, before any model request and without
  credentials, and the clone's settings `env` block is applied. None of this happens under `[]`. The live test
  therefore needs no credentials and runs in CI by default, within a hard time bound. The severity is not
  downgraded.
- A4. Impact on MCP and settings. None of the 22 non-archived `mctlhq` repositories has a root `.mcp.json` or
  `.claude/settings.json` on its default branch, so no legitimate MCP server or setting is lost.
- A5. Impact on instruction files. Today `["project"]` makes the CLI load the target repository's instruction
  files into the session on its own: root `CLAUDE.md`, `.claude/CLAUDE.md` with its `@` imports, and `AGENTS.md`
  in a repository with no CLAUDE.md. None of them load under `[]`. Four repositories keep their only CLAUDE.md
  at `.claude/CLAUDE.md` (mctl-design, mctl-docs, mctl-support, mctl-telegram), and four have only `AGENTS.md`
  (.github, mctl-alice, newton-mcp-gateway, portfolio). The prompts and personas name only the root `CLAUDE.md`,
  so their wording is widened to name every instruction file explicitly (new criterion, task 5b).
- A6. Scope of the guarantee. This change closes the channels through which a clone's Claude Code configuration
  acts on the session (D3). It does not stop repository code that the agent itself runs through Bash from seeing
  the pod's credentials (D4, see Out of scope).

## Context
Two agents run with `cwd` set to a fresh clone of an arbitrary `mctlhq/*` target repository, and with
`setting_sources=["project"]`: the Tier 2 implementer and the issue-investigator. That covers four
`ClaudeAgentOptions` constructions in `orchestrator/options.py`: `build_implementer_agent_options`,
`build_issue_investigator_options`, and both branches of `build_issue_investigator_options_from_plan`.
The pinned `claude-agent-sdk==0.2.168` documents `"project"` as loading `.claude/settings.json` and as required
for CLAUDE.md. On the bundled CLI 2.1.301 the same source also brings in `.claude/agents`, `.claude/skills` and
the other project instruction files. The settings layer is not passive data: it runs command hooks on several
events and an `apiKeyHelper` command, and it applies its `env` block to the CLI process and everything the CLI
spawns, which can change the CLI's own configuration without running any code. All of this is read from untrusted
repository content, in a pod that holds the agent's credentials (GITHUB_TOKEN, model credentials, MCP token).
Spike mctlhq/mctl-agents#852 records this as gap D3.

A second channel sits beside the settings layer. Under the current `["project"]`, the CLI also starts every MCP
server declared in the clone's `.mcp.json`, and an MCP stdio server is an arbitrary command. The SDK documents
`strict_mcp_config` as the switch that ignores "project `.mcp.json`, user/global settings, plugin-provided
servers", and only the gateway branch of `build_issue_investigator_options_from_plan` sets it. The implementer,
the legacy investigator and the `gateway is None` branch do not. A probe on 2026-10-28 confirmed that both
channels execute under the current options (Amendment A3).

Today the implementer depends on the `project` source for one legitimate purpose.
`run_implementer._stage_implementer_agent` copies the image-shipped `implementer.md` persona into
`<clone>/.claude/agents/` so the CLI discovers it. Both agents also get the target repo's instruction files
loaded as context. Both must keep working through a trusted channel. Neither may come from the clone's
settings layer.

## User stories
- AS a platform operator I WANT agents working in a target-repository clone to ignore that repository's Claude Code configuration (`.claude/settings.json` with its hooks, helpers and `env` block, `.claude/agents`, `.claude/skills`, and `.mcp.json`) SO THAT a malicious or careless repository cannot, through Claude Code configuration, make the CLI run repository-supplied commands, change the session's environment, or add agents or skills to a session in a pod that holds agent credentials.
- AS the Tier 2 implementer I WANT my `implementer` persona delivered from the image SO THAT delegation to the `implementer` sub-agent keeps working without writing into the clone.
- AS a maintainer of a target repository I WANT the agents to keep reading my conventions from `CLAUDE.md`, `.claude/CLAUDE.md` or `AGENTS.md` SO THAT closing the settings layer does not silently drop them.
- AS a reviewer of this fix I WANT a red/green regression test with a mutation check SO THAT a later change that restores `["project"]` or drops `strict_mcp_config` fails CI.

## Acceptance criteria (EARS)
- WHEN `build_implementer_agent_options`, `build_issue_investigator_options` or `build_issue_investigator_options_from_plan` (with or without a gateway) builds options for a target-repository clone THE SYSTEM SHALL set `setting_sources=[]`.
- WHEN any of those four constructions builds options for a target-repository clone THE SYSTEM SHALL set `strict_mcp_config=True`.
- WHEN the SDK transport builds the CLI command from those options THE SYSTEM SHALL emit `--setting-sources=` with no `project`, `user` or `local` entry, and SHALL emit `--strict-mcp-config`.
- WHEN those options pass MCP servers through `mcp_servers` (the `mctl` server from `mctl_mcp_config`, or the capability gateway) THE SYSTEM SHALL still start those servers under `--strict-mcp-config`.
- WHEN the implementer agent is launched THE SYSTEM SHALL pass the `implementer` persona programmatically via `ClaudeAgentOptions.agents` as an `AgentDefinition`. The definition SHALL be parsed from the image-shipped `agents/<service>/.claude/agents/implementer.md`, falling back to `agents/_generic/.claude/agents/implementer.md`. Its frontmatter `description` and `tools` SHALL be preserved and its markdown body used as the prompt.
- WHEN the implementer clone is prepared THE SYSTEM SHALL NOT write `implementer.md` into `<clone>/.claude/agents/`.
- WHILE the implementer clone is prepared THE SYSTEM SHALL keep the refusal marker (`REFUSAL_MARKER_FILENAME`) registered in `<clone>/.git/info/exclude`.
- IF neither a per-service nor the generic `implementer.md` exists in the image THEN THE SYSTEM SHALL abort before launching the agent, as `_stage_implementer_agent` does today.
- IF a target clone contains `.claude/settings.json` declaring a hook, an `env` block and a permissions entry THEN THE SYSTEM SHALL NOT load that file. The deterministic test SHALL show this through the CLI argv (`--setting-sources=` with no `project`). The live test SHALL show that the hook does not run and the `env` block is not applied, against a `["project"]` control in the same run in which both take effect. The permissions entry has no live assertion: CLI 2.1.301 drops it in an untrusted workspace even under `["project"]`, so the argv assertion is what covers it.
- IF a target clone contains `.mcp.json` declaring an MCP server THEN THE SYSTEM SHALL NOT start that server. The live test SHALL demonstrate this with the same fixture clone and the same control.
- IF a target clone contains `.claude/agents/<name>.md` THEN THE SYSTEM SHALL NOT register that sub-agent. The live test SHALL demonstrate this through the session's agent list, against the same control.
- IF a builder for a target clone is mutated back to `setting_sources=["project"]`, or to `strict_mcp_config=False`, THEN THE SYSTEM's regression test SHALL fail.
- WHILE the issue-investigator or the implementer runs THE SYSTEM SHALL tell the agent, in its prompt or persona, to read the target repo's instruction files with the Read tool when present: `CLAUDE.md` at the cwd root or `.claude/CLAUDE.md`; `AGENTS.md` at the cwd root or `.claude/AGENTS.md`; and any file they import with an `@path` line. These files SHALL be treated as untrusted data, not as a settings layer.
- WHILE builders whose `cwd` is an image-shipped agent directory run (service agent, mentor, incident responder, shepherd) THE SYSTEM SHALL keep `setting_sources=["project"]` and their current MCP configuration unchanged.

## Out of scope
- Builders whose `cwd` is an image-shipped agent directory: `build_service_agent_options`, `build_mentor_options`, `build_incident_responder_options` and `build_shepherd_options`. They load trusted content, and this change adds no `strict_mcp_config` to them.
- The mctl-docs service agent's `add_dirs` sibling repositories (`SIBLING_REPOS_PATH`). Under its `["project"]` source the CLI can pick up `.claude/skills` from those directories. The path is not set in any deployed values today, so the channel is dormant in the cluster. It is left unchanged here and noted for a follow-up.
- Authoring canary and scout already use `setting_sources=[]`.
- Sandboxing or allowlisting Read/Bash access to `.claude/**` or `.mcp.json` inside the clone. With the settings source off and strict MCP config on, the CLI treats these files as inert data. The agent's own tool calls can still read them (D5) or run repository code (D4).
- Other 852 gaps (D1, D2, D4, D5). Repository code that the agent runs through Bash, such as the implementer's build and test step, still runs with the pod environment, including GITHUB_TOKEN and the model credential (D4: #807 G2, folded into the D2 follow-up #869). This change does not address it.
- Changing persona text in any `implementer.md`, except the instruction-file lines named in task 5b.
- `agents/_manifests/issue-investigator/agent.yaml`. Its comment and `runtimeContext` still describe CLAUDE.md as loaded through `setting_sources=["project"]`, which becomes stale. Any byte change to that file needs the mctl-gitops re-pin in `docs/runbooks/agent-yaml-binding-repin.md`, which opens a window in which new investigations fail. The correction is therefore folded into the next change that has to touch that manifest anyway.

## Open questions
- Severity downgrade (issue step 1). Resolved by Amendment A3: a local probe showed the hook and the `.mcp.json` server both execute under `["project"]`. No downgrade. The implementer reproduces the probe as the CI live test (task 1) and records its result on the issue (task 8).
- Whether the investigator should get the instruction files injected verbatim into the prompt. This proposal keeps the prompt instruction to Read them instead, which avoids adding untrusted text to the system prompt. Reviewers may prefer explicit injection with a size cap.
- `InvestigatorOrphanedSubagent` and the implementer orphan handling were justified partly by target-repo `.claude/agents` being loaded. They stay, because built-in sub-agents can still be launched asynchronously. Only their docstrings and comments need updating.
