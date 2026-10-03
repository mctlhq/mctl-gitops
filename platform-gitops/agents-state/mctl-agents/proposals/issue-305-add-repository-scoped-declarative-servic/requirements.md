# Repository-scoped declarative ServiceSkills in agent execution plans

## Context

`mctl-agents` has two declarative layers today and nothing between them. An
agent's identity and execution shape are declared in Git
(`agents/_manifests/<agent>/agent.yaml`, resolved by `orchestrator/manifest.py`
and, for the one migrated agent, `orchestrator/resolver.py` against the
mctl-gitops `agent-platform` catalog per ADR 007). Platform skills are
centrally versioned and referenced by name from `ExecutionProfile.spec.skills`
(today `skills: []` for `issue-investigator-default`, with `policy.yaml`
`knownSkills: [mctl-platform, git-flow]` as the allow-list). What is missing is
a way for a *target service repository* to declare stable, repository-specific
instructions — test matrix, generated-file rules, security invariants, build
constraints — and have a named agent receive them deterministically.

The gap is not theoretical, and it is worse than "nothing exists". Both
`build_implementer_agent_options` and `build_issue_investigator_options`
(`orchestrator/options.py:300`, `:387`) set `cwd=<target clone>` with
`setting_sources=["project"]`, so the Claude Code CLI already loads whatever
`CLAUDE.md`, `.claude/agents/*.md` and `.claude/skills/**` the target
repository happens to ship — from the **mutable working tree**, with no pin, no
hash, no envelope check, and no record of which bytes were loaded. So a
repository-scoped skill channel exists; it is simply ambient, unauditable, and
writable by the one agent that authors code. This proposal replaces it with an
explicit `ServiceSkillSet` contract read from the pinned target repository SHA,
validated against the agent's existing execution envelope, hashed into the
run's provenance, and injected once.

## User stories

- AS a service owner I WANT to declare repository-specific skills in
  `.mctl/skills/` next to my code and bind them to named mctl agents SO THAT
  the implementer stops rediscovering my test matrix, generated-file rules and
  security invariants on every run.
- AS a platform owner I WANT service skills to be loaded only from the
  pre-execution pinned target SHA and recorded with content hashes SO THAT the
  exact instruction bytes that produced a PR remain auditable after the branch
  diverges.
- AS a security reviewer I WANT a service skill to be unable to widen the
  agent's tools, permissions, policy, budget, timeout, network or sandbox SO
  THAT ADR 007's rule "tools are not authorization; the profile and providers
  remain authoritative" survives contact with repository-owned content.
- AS a platform owner I WANT reusable `ExecutionProfile`s to stay
  service-agnostic SO THAT we never grow `implementer-mctl-telegram`,
  `implementer-mctl-agent`, and so on.
- AS an operator I WANT a malformed, oversized, escaping or out-of-policy
  ServiceSkillSet to fail loudly before the agent runs SO THAT a bad skill
  never silently degrades into "the agent ignored it".

## Acceptance criteria (EARS)

Resolution and pinning

- R1. WHEN an agent run begins for a target repository, THE SYSTEM SHALL pin
  the target repository SHA (`git rev-parse HEAD` in the clone, as
  `orchestrator/run_issue_investigator.py:117` `_target_repository_sha` already
  does) before reading any service skill.
- R2. WHEN service skills are enabled for an agent, THE SYSTEM SHALL read
  `.mctl/skills/manifest.yaml` and every referenced `SKILL.md` from that exact
  pinned SHA using git object reads (`git ls-tree -r -z` plus
  `git show <sha>:<path>`, the pattern already used by
  `tools/publish_agent_release.py:104` `_tree_paths` and `:118` `_read_at_tag`),
  never from the working tree.
- R3. WHILE an execution is in flight THE SYSTEM SHALL NOT re-read, reload or
  refresh any service skill from the working tree, from a later commit, or from
  the platform catalog.
- R4. IF the pinned SHA cannot be determined (empty repository, detached or
  missing HEAD) THEN THE SYSTEM SHALL fail closed with a message naming the
  condition, exactly as `_target_repository_sha` does today.
- R5. WHEN the target repository contains no `.mctl/skills/manifest.yaml` at the
  pinned SHA, THE SYSTEM SHALL resolve an empty service-skill bundle and
  continue — an absent contract is a valid state, not an error.
- R6. WHEN the agent under resolution is an agent-authoring agent working on an
  agent-owned branch (`implementer`, `shepherd` on `feat/agents-*`), THE SYSTEM
  SHALL resolve service skills from the merge-base of that branch with the
  repository default branch rather than from the branch head, SO THAT a skill
  edit authored by a previous run of the same agent cannot become policy for
  the next run without passing human review on the default branch.
- R7. IF that merge-base cannot be computed because the clone is shallow
  (`gh repo clone --depth=1` / `--depth=10`, `run_issue_investigator.py:926`,
  `run_implementer.py:1225`) and one deepening fetch does not recover it, THEN
  THE SYSTEM SHALL fail closed rather than silently fall back to the branch
  head.

Selection, ordering and validation

- R8. WHEN a `ServiceSkillSet` manifest is parsed, THE SYSTEM SHALL select only
  the skills bound to the concrete agent name under `spec.bindings.<agent>`.
- R9. WHEN skills are composed for a run, THE SYSTEM SHALL order them
  deterministically: platform skills (from `ExecutionProfile.spec.skills`)
  first, then service skills in the order they appear in that agent's binding
  list.
- R10. IF the manifest is malformed, declares an unknown `apiVersion`/`kind`,
  binds an agent name that is not a known agent (`agents/_manifests/*`),
  contains duplicate skill ids, binds a skill id absent from `spec.skills`, or
  references a path that is not a file in the pinned tree, THEN THE SYSTEM SHALL
  fail closed with a message naming the offending id or path.
- R11. IF a declared skill path is not under the declared `.mctl/skills/` root,
  contains `..`, or resolves to a tree entry whose git mode is not a regular
  blob (mode `120000` symlink, `160000` gitlink/submodule), THEN THE SYSTEM
  SHALL reject the whole bundle.
- R12. WHILE validating a bundle THE SYSTEM SHALL accept Markdown `SKILL.md`
  content only and SHALL reject any other file type inside a skill directory in
  v1.
- R13. IF a single skill exceeds the per-skill byte ceiling, or the bundle
  exceeds the total byte ceiling, or the bundle exceeds the maximum skill count,
  THEN THE SYSTEM SHALL fail closed and report measured-versus-allowed values
  (bounding the read, not merely the reported size, as
  `run_issue_investigator.py:517` already does for `MAX_STATUS_BYTES`).

Authority boundary

- R14. WHILE composing a run THE SYSTEM SHALL treat service skills as
  instructions only, and SHALL NOT let them contribute to `allowed_tools`,
  `mcp_servers`, `permission_mode`, `max_budget_usd`, timeout, network,
  sandbox, `policyRef` or any mutation scope.
- R15. IF a skill's front matter declares any key in the reserved authority set
  (`tools`, `allowedTools`, `permissions`, `policyRef`, `mutationScopes`,
  `budgetUsd`, `timeoutSeconds`, `network`, `sandbox`, `mcpServers`, `model`,
  `approval`) THEN THE SYSTEM SHALL reject the bundle.
- R16. WHEN a skill declares `requiresTools`, THE SYSTEM SHALL treat it as a
  validation requirement only and SHALL fail closed if the requirement is not a
  subset of the agent's already-resolved tool allow-list
  (`AgentManifest.tool_allow`, i.e. `ExecutionProfile.spec.tools` for a
  v1alpha2 agent and `spec.toolPolicy.allow` for a v1alpha1 agent).
- R17. WHILE service skills are disabled for an agent — which is the default
  when no `serviceSkills` policy block is declared — THE SYSTEM SHALL resolve an
  empty bundle and SHALL NOT read the target repository's `.mctl/` root at all.
- R18. WHEN service-skill text is injected into an agent prompt, THE SYSTEM
  SHALL wrap it in delimiters, neutralize forged delimiter tags in the content
  (reusing the `_neutralize_prompt_tags` technique at
  `run_issue_investigator.py:1098`), and precede it with an explicit statement
  that the content is repository-owned instruction data that grants no
  authority.

Provenance

- R19. WHEN an `ExecutionPlan` is materialized, THE SYSTEM SHALL record for each
  selected service skill its id, repository-relative path, `sha256:`-prefixed
  content hash and byte count, plus the manifest's own content hash and the
  pinned SHA the bundle was read from.
- R20. WHEN `ExecutionPlan.log()` runs, THE SYSTEM SHALL include those
  identifiers in the structured `to_log_dict()` output.
- R21. WHEN the same pinned SHA, manifest, definition, profile and binding are
  resolved twice, THE SYSTEM SHALL produce byte-identical service-skill
  identifiers and ordering.
- R22. IF a service skill fails any rule above THEN THE SYSTEM SHALL raise
  before the agent SDK client is constructed, and — for agents resolved through
  `orchestrator/resolver.py` — before Argo submission.

Agents covered

- R23. WHEN `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`, THE SYSTEM SHALL
  resolve and record service skills as part of `resolver.execute()`'s
  `ExecutionPlan`.
- R24. WHEN the `implementer` runs, THE SYSTEM SHALL resolve service skills
  through the same module from the same pinned-SHA rules even though the
  implementer is still `agents.mctl.ai/v1alpha1` and has no `ExecutionPlan`,
  taking its envelope from `AgentManifest` (`tool_allow`, `budget_usd`,
  `timeout_seconds`).
- R25. WHEN an operator sets the kill switch `MCTL_SERVICE_SKILLS=off`, THE
  SYSTEM SHALL behave exactly as if no agent had service skills enabled, and
  SHALL log that it did so.

## Out of scope

- Executable scripts, hooks, or non-Markdown assets inside a ServiceSkill
  package. v1 is Markdown `SKILL.md` only.
- Path/glob-based conditional activation ("load this skill only when touching
  `internal/bridge/**`"). v1 is explicit deterministic bindings.
- A second registry, version number, or publication lifecycle for service
  skills. The target repository SHA already names the exact bytes.
- Changing what platform skills are, how they are published, or the
  `policy.yaml` `knownSkills` allow-list semantics.
- Migrating `implementer` or `shepherd` to `agents.mctl.ai/v1alpha2`, or
  flipping `ISSUE_INVESTIGATOR_RESOLVER_MODE` away from `legacy`. Both remain
  blocked on a registry-backed `ReleaseBinding` (`docs/resolver-pilot-status.md`).
- Persisting a sealed `ContextSnapshot` (`orchestrator/context_snapshot.py`) to
  mctl-api. ADR 009 leaves that to a follow-up with no producer yet; this
  proposal only makes the service-skill sources *expressible* as
  `ContextSource` records.
- Disabling or replacing the ambient `setting_sources=["project"]` loading of
  the target repository's own `CLAUDE.md` / `.claude/` tree. That channel is
  documented here as the motivating hazard and narrowed in a follow-up, because
  the implementer depends on `.claude/agents/implementer.md` being staged into
  the clone (`run_implementer.py:1233` `_stage_implementer_agent`).
- CODEOWNERS enforcement inside target repositories.

## Open questions

1. **Where the enablement knob lives.** Following the issue's own suggestion,
   this proposal puts "permission to load service skills plus limits" on the
   platform side and the agent-to-skill bindings in the service repo. Concretely
   that means a new optional `spec.serviceSkills` block on `ExecutionProfile`
   (mctl-gitops, whose `execution-profile.schema.json` is
   `additionalProperties: false`, so it requires a schema PR there) and a
   mirrored `spec.serviceSkills` on v1alpha1 `agent.yaml` for agents not yet
   migrated. Reviewers should confirm they want the v1alpha1 mirror rather than
   blocking the whole feature on the implementer's v1alpha2 migration.
2. **`.mctl/skills/` versus an existing convention.** The issue asks whether to
   match a Claude/Codex skill convention. This proposal keeps `.mctl/skills/`
   deliberately *separate* from `.claude/skills/`, because `.claude/` is already
   auto-loaded from the mutable worktree by `setting_sources=["project"]` and
   reusing it would make "pinned bundle" and "ambient bundle" indistinguishable.
   A reviewer who wants one root must also decide what happens to the ambient
   load path.
3. **CODEOWNERS / platform approval for high-risk bindings.** R6 (resolve from
   the merge-base for agent-authored branches) is this proposal's mechanical
   answer, which does not require target repositories to adopt CODEOWNERS. A
   reviewer may still want a required-review policy for
   `.mctl/skills/**` bound to `implementer`; that is a target-repo policy
   decision, recorded and not implemented here.
4. **Unknown agent names fail closed (R10).** This is what the issue asks for,
   but it means a service repo that binds a future agent name breaks every
   current run in that repo. The alternative — ignore-with-warning for unknown
   names — trades fail-closed for forward compatibility. Proceeding with
   fail-closed as specified.
5. **`ContextSource.kind` vocabulary.** `orchestrator/context_snapshot.py:50`
   defines `SOURCE_KINDS` as a closed frozenset containing `target-repo` but no
   service-skill kind. This proposal reuses `target-repo` with a
   `selector: {"service_skill": "<id>"}` rather than widening the vocabulary;
   ADR 009's follow-up (e) (per-file enumeration) may prefer a new kind later.
6. **Pre-submission versus pod-start enforcement.** R22 can only be literally
   "before Argo submission" for agents whose plan is resolved outside the pod.
   The implementer resolves inside its own Argo pod, so for it the gate is "at
   the start of the run, before the SDK client and before any commit". Recorded
   rather than papered over.
