# Stop loading project settings from target-repository clones (852 D3)

## Context
Two agents run with `cwd` set to a fresh clone of an arbitrary `mctlhq/*` target repository, and with
`setting_sources=["project"]`: the Tier 2 implementer and the issue-investigator. That covers four
`ClaudeAgentOptions` constructions in `orchestrator/options.py`: `build_implementer_agent_options`,
`build_issue_investigator_options`, and both branches of `build_issue_investigator_options_from_plan`.
The pinned `claude-agent-sdk==0.2.168` documents `"project"` as covering `.claude/settings.json`
(permissions, hooks), CLAUDE.md, `.claude/agents` and `.claude/skills`. So configuration that may include
hooks is read from untrusted repository content. It runs in a pod that holds the agent's credentials
(GITHUB_TOKEN, model credentials, MCP token). Spike mctlhq/mctl-agents#852 records this as gap D3; it was
not exercised live.

Today the implementer depends on the `project` source for one legitimate purpose.
`run_implementer._stage_implementer_agent` copies the image-shipped `implementer.md` persona into
`<clone>/.claude/agents/` so the CLI discovers it. The investigator also gets the target repo's CLAUDE.md
loaded as context. Both must keep working through a trusted channel. Neither may come from the clone's
settings layer.

## User stories
- AS a platform operator I WANT agents working in a target-repository clone to ignore that repository's `.claude/settings.json`, hooks, agents and skills SO THAT a malicious or careless repository cannot run code or widen permissions in a pod that holds agent credentials.
- AS the Tier 2 implementer I WANT my `implementer` persona delivered from the image SO THAT delegation to the `implementer` sub-agent keeps working without writing into the clone.
- AS a reviewer of this fix I WANT a red/green regression test with a mutation check SO THAT a later change that restores `["project"]` fails CI.

## Acceptance criteria (EARS)
- WHEN `build_implementer_agent_options`, `build_issue_investigator_options` or `build_issue_investigator_options_from_plan` (with or without a gateway) builds options for a target-repository clone THE SYSTEM SHALL set `setting_sources=[]`.
- WHEN the SDK transport builds the CLI command from those options THE SYSTEM SHALL emit `--setting-sources=` with no `project`, `user` or `local` entry.
- WHEN the implementer agent is launched THE SYSTEM SHALL pass the `implementer` persona programmatically via `ClaudeAgentOptions.agents` as an `AgentDefinition`. The definition SHALL be parsed from the image-shipped `agents/<service>/.claude/agents/implementer.md`, falling back to `agents/_generic/.claude/agents/implementer.md`. Its frontmatter `description` and `tools` SHALL be preserved and its markdown body used as the prompt.
- WHEN the implementer clone is prepared THE SYSTEM SHALL NOT write `implementer.md` into `<clone>/.claude/agents/`.
- WHILE the implementer clone is prepared THE SYSTEM SHALL keep the refusal marker (`REFUSAL_MARKER_FILENAME`) registered in `<clone>/.git/info/exclude`.
- IF neither a per-service nor the generic `implementer.md` exists in the image THEN THE SYSTEM SHALL abort before launching the agent, as `_stage_implementer_agent` does today.
- IF a target clone contains `.claude/settings.json` declaring a hook and a permissions entry THEN THE SYSTEM SHALL neither execute the hook nor apply the permission. The regression test SHALL demonstrate this with a fixture clone.
- IF a builder for a target clone is mutated back to `setting_sources=["project"]` THEN THE SYSTEM's regression test SHALL fail.
- WHILE the issue-investigator runs THE SYSTEM SHALL keep telling the agent, in the prompt, to read the target repo's root `CLAUDE.md` with the Read tool when present. CLAUDE.md is treated as untrusted data, not as a settings layer.
- WHILE builders whose `cwd` is an image-shipped agent directory run (service agent, mentor, incident responder, shepherd) THE SYSTEM SHALL keep `setting_sources=["project"]` unchanged.

## Out of scope
- Builders whose `cwd` is an image-shipped agent directory: `build_service_agent_options`, `build_mentor_options`, `build_incident_responder_options` and `build_shepherd_options`. They load trusted content.
- Authoring canary and scout already use `setting_sources=[]`.
- Sandboxing or allowlisting Read/Bash access to `.claude/**` inside the clone. With the settings source off, the files are inert data.
- Other 852 gaps (D1, D2, D5).
- Changing the persona text in any `implementer.md`.

## Open questions
- Severity downgrade (issue step 1). Whether the current options actually execute a repository hook can only be shown by running the bundled CLI (`claude_agent_sdk/_bundled/claude`) against a fixture clone. It is unknown whether a `SessionStart` hook fires without model credentials in CI. The plan is a deterministic unit test on the CLI argv, which always runs, plus an opt-in live test gated on an env var. If the live test shows the hook does not execute, the implementer records that on the issue and downgrades the severity, but still ships the change.
- Whether the investigator should get CLAUDE.md injected verbatim into the prompt. This proposal keeps the existing prompt instruction to Read it instead, which avoids adding untrusted text to the system prompt. Reviewers may prefer explicit injection with a size cap.
- `InvestigatorOrphanedSubagent` and the implementer orphan handling were justified partly by target-repo `.claude/agents` being loaded. They stay, because built-in sub-agents can still be launched asynchronously. Only their docstrings and comments need updating.
