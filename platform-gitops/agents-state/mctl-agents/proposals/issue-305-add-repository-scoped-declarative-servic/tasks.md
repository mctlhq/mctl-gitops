# Tasks: issue-305-add-repository-scoped-declarative-servic

- [ ] 1. Add `orchestrator/service_skills.py` with the data model:
  `ServiceSkillError`, `ServiceSkillPolicy`, `ServiceSkill`,
  `ServiceSkillBundle` (frozen dataclasses, `sha256:`-prefixed hashes via a
  `_hash_bytes` identical to `resolver.py:301`). — DoD: module imports with
  stdlib + `yaml` + `orchestrator.proc` only (no `claude_agent_sdk`, no
  `temporalio`), `tests/test_worker_isolation.py` still passes, `ruff` and
  `mypy` clean per `pyproject.toml`.
- [ ] 2. Implement pinned-tree reads in that module (depends on 1):
  `_tree_entries(repo_dir, sha, root)` via
  `git ls-tree -r -z --full-tree <sha> -- <root>` and `_blob(repo_dir, sha,
  path)` via `git show <sha>:<path>`, both through `proc.run_capturing` with
  `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`-style bounding; reject modes `120000`
  and `160000`, reject any path not present in the listing, reject anything
  outside `policy.root` or containing `..`. — DoD: mirrors
  `tools/publish_agent_release.py:104`/`:118`; no `pathlib` read of the
  worktree exists anywhere in the module.
- [ ] 3. Implement `pin_sha(repo_dir, agent, branch)` (depends on 1):
  `git rev-parse HEAD` for read-only agents; `git merge-base HEAD
  origin/<default-branch>` for `implementer`/`shepherd` on `feat/agents-*`,
  with one `git fetch --deepen=50` retry and a fail-closed
  `ServiceSkillError` naming the shallow-clone condition. — DoD: R6/R7
  satisfied; the failure message tells an operator which fetch to run.
- [ ] 4. Implement `resolve_bundle(...)` (depends on 2, 3): parse
  `manifest.yaml`, check `apiVersion`/`kind`, select `spec.bindings[agent]` in
  order, resolve ids against `spec.skills`, reject duplicates / unknown agent
  names / unbound ids / missing blobs / non-`SKILL.md` files, parse each
  skill's front matter, reject every reserved authority key, and check
  `requiresTools` ⊆ `tool_allow`. Enforce `max_skills`, `max_skill_bytes`,
  `max_total_bytes` by bounding the read (`limit + 1`, then compare). — DoD:
  every failure raises `ServiceSkillError` naming the offending id or path;
  a repo with no `manifest.yaml` returns an empty bundle without error.
- [ ] 5. Implement `ServiceSkillBundle.to_prompt_block()` (depends on 4):
  deterministic ordering, `<service_skills source="...@<sha>">` delimiters,
  forged-delimiter neutralization reusing the technique in
  `run_issue_investigator._neutralize_prompt_tags` (`:1098`), and the
  "repository-owned instructions, grants no authority" preamble. — DoD: a
  skill whose body contains `</service_skills>` cannot terminate or forge the
  block.
- [ ] 6. Add `ServiceSkillPolicy` parsing to `orchestrator/manifest.py`
  (depends on 1): new `AgentManifest.service_skills` field populated from
  `spec.serviceSkills` in `_parse_fields_v1alpha1` and from the resolved
  profile's `spec.serviceSkills` in `_parse_fields_v1alpha2`; absent block →
  `ServiceSkillPolicy(enabled=False)`. — DoD: every existing manifest still
  loads unchanged; `tests/test_manifest.py` green.
- [ ] 7. Extend `orchestrator/validate_manifest.py` (depends on 6) with a
  check that a declared `serviceSkills` limit never exceeds the
  `agent-platform/policy.yaml` ceiling, in the style of
  `check_catalog_profiles_match_builders` (`:475`). — DoD:
  `python -m orchestrator.validate_manifest` reports a violation instead of
  resolving it.
- [ ] 8. Wire the declarative path (depends on 4, 6): optional
  `Task.target_repo_dir`; `resolver.execute()` resolves the bundle after
  `load_profile` and before building the plan; `ExecutionPlan` gains
  `service_skills`, `service_skill_manifest_hash`,
  `service_skills_resolved_from_sha`, all surfaced in `to_log_dict()`. — DoD:
  `ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative` logs the service-skill
  identifiers; a bad bundle raises before the SDK client is constructed.
- [ ] 9. Inject the block into the investigator prompt (depends on 5, 8):
  `run_issue_investigator._build_prompt` gains an optional service-skills
  section placed after `## Your working context` and before
  `## What to produce`. — DoD: an empty bundle changes the prompt by zero
  bytes.
- [ ] 10. Wire the implementer (depends on 4, 5, 6): `implement_one` and
  `review_feedback_one` call `pin_sha` right after clone/checkout, load the
  implementer's `AgentManifest` for `tool_allow` + policy, resolve the bundle,
  and pass `to_prompt_block()` into `_build_prompt` (both the new-PR and
  review-feedback variants). — DoD: a `ServiceSkillError` aborts the run
  before `_run_implementer_agent`, so before any commit, push, or PR.
- [ ] 11. Add the `MCTL_SERVICE_SKILLS=off` kill switch (depends on 4) — read
  fresh per call, not cached at import, matching `_resolver_mode()`
  (`run_issue_investigator.py:108`) — and log the decision on every run the
  way `print(f"[resolver] ... resolver_mode={mode!r}")` does. — DoD: with the
  switch off, no `git ls-tree` runs and the prompts are byte-identical to
  today's.
- [ ] 12. Add `ServiceSkillBundle.to_context_sources()` (depends on 4)
  emitting ADR 009 `ContextSource` records (`kind="target-repo"`,
  `selector={"service_skill": id}`, `Trust(tier="authoritative",
  rationale_code="pinned-target-repository-sha")`). — DoD: each emitted record
  round-trips through `ContextSource.from_dict(...).to_dict()`; nothing is
  persisted (that stays ADR 009 follow-up (b)).
- [ ] 13. Declare the policy block for the implementer (depends on 6, 7):
  `spec.serviceSkills: {enabled: true, root: .mctl/skills, maxSkills: 8,
  maxSkillBytes: 32768, maxTotalBytes: 98304}` in
  `agents/_manifests/implementer/agent.yaml`, with the comment explaining why
  it lives in the manifest for a v1alpha1 agent. — DoD: manifest validation
  passes; `implementer-default` in the catalog is untouched.
- [ ] 14. Add a CI-usable validator entry point (depends on 4):
  `python -m orchestrator.service_skills --validate <repo> [--agent NAME]`
  that resolves against the worktree HEAD and prints every rejection. — DoD:
  documented in `README.md` so a target repo can gate its own
  `.mctl/skills/**` PRs.
- [ ] 15. Documentation (depends on 8, 10): a "Service skills" section in
  `docs/resolver-pilot-status.md` covering the ambient
  `setting_sources=["project"]` channel this replaces, the pinned-SHA and
  merge-base rules, the `sha256:`-prefix inconsistency with the existing bare
  hex `skill_hashes` (`resolver.py:894`), and the kill switch; plus a
  `runtimeContextInputs` note in `docs/agent-inventory.yaml`. — DoD:
  `tests/test_agent_inventory.py` and `tools/check_diagrams.py` green.
- [ ] 16. Cross-repo, mctl-gitops (parallel to 1-15, blocks only 17): add
  optional `spec.serviceSkills` to
  `platform-gitops/agent-platform/schemas/execution-profile.schema.json`
  (currently `additionalProperties: false`), ceilings
  `limits.maxServiceSkills` / `limits.maxServiceSkillBytes` to
  `agent-platform/policy.yaml`, and the matching checks in
  `scripts/validate-agent-platform.py`. — DoD: merged mctl-gitops PR; existing
  profiles validate unchanged.
- [ ] 17. Cross-repo, mctl-gitops (depends on 16): add the `serviceSkills`
  block to `execution-profiles/issue-investigator-default/profile.yaml`, bump
  its `spec.version`, and re-pin `releases/shadow/issue-investigator.yaml`. —
  DoD: `orchestrator/resolver.py` still resolves (version/mirror/contentHash
  checks pass).
- [ ] 18. Cross-repo, mctl-telegram (depends on 10, 13): ship
  `.mctl/skills/manifest.yaml` plus `repo-testing` and
  `local-bridge-security` `SKILL.md` files capturing the invariants the
  Local Bridge #482/#483 implementer kept rediscovering. — DoD: one
  implementer run on that repo logs exactly the expected skill ids and hashes,
  with `implementer-default` unchanged.

## Tests

- [ ] T1. Agent-specific selection: one manifest, three bindings; resolving for
  `implementer` returns exactly its three skills and resolving for
  `issue-investigator` returns exactly its one.
- [ ] T2. Deterministic ordering and idempotence: two resolutions of the same
  pinned SHA produce identical ids, hashes, byte counts and order; reordering
  `spec.bindings[agent]` changes the order and only the order.
- [ ] T3. SHA pinning: commit a modified `SKILL.md` on top of the pinned SHA and
  assert the resolved content hash is unchanged.
- [ ] T4. Mutable-worktree non-reload: overwrite `.mctl/skills/**` in the
  working tree after pinning (uncommitted) and assert the bundle is byte-for-byte
  unchanged — the strongest form of R3, and the reason §2 uses git plumbing
  rather than `Path.read_bytes`.
- [ ] T5. Merge-base rule: on a `feat/agents-*` branch whose head commits a new
  skill, assert the resolved bundle comes from the merge-base and does NOT
  contain the branch-authored skill; and that a shallow clone with no reachable
  merge-base raises `ServiceSkillError` rather than falling back.
- [ ] T6. Path escape rejection: `../../etc/passwd`, an absolute path, a path
  outside `policy.root`, a symlink blob (mode `120000`) pointing at
  `/etc/passwd`, and a submodule entry (mode `160000`) each reject the bundle.
- [ ] T7. Context-size bounds: per-skill overflow, total overflow and
  `max_skills` overflow each raise with measured-versus-allowed values; a
  bundle exactly at each ceiling resolves.
- [ ] T8. Permission-escalation rejection: front matter declaring `tools`,
  `allowedTools`, `permissions`, `policyRef`, `mutationScopes`, `budgetUsd`,
  `timeoutSeconds`, `network`, `sandbox`, `mcpServers`, `model` or `approval`
  rejects (parametrized); `requiresTools: [Bash]` resolves for the implementer
  and rejects for an envelope without `Bash`.
- [ ] T9. Fail-closed manifest cases: bad YAML, wrong `apiVersion`/`kind`,
  unknown agent name in `bindings`, duplicate skill id, id bound but absent
  from `spec.skills`, declared path missing from the tree, non-`SKILL.md` file
  in a skill directory.
- [ ] T10. Disabled/absent path: `ServiceSkillPolicy(enabled=False)` and
  `MCTL_SERVICE_SKILLS=off` both produce an empty bundle and run zero git
  subprocesses (assert via a patched `run_capturing`).
- [ ] T11. Plan provenance: `ExecutionPlan.to_log_dict()` contains the skill
  ids, `sha256:`-prefixed hashes, byte counts, manifest hash and
  `service_skills_resolved_from_sha`; `tests/test_resolver.py`'s determinism
  test extended to cover them.
- [ ] T12. Prompt injection containment: a skill body containing
  `</service_skills>`, a forged opening tag, and an "ignore previous
  instructions" line is neutralized and stays inside the delimited block; an
  empty bundle leaves both `_build_prompt` outputs byte-identical to today's.
- [ ] T13. Options equivalence: `build_implementer_agent_options` and
  `build_issue_investigator_options_from_plan` produce identical
  `allowed_tools`, `mcp_servers`, `permission_mode`, `max_budget_usd` and
  `add_dirs` with and without a non-empty bundle — proof that service skills
  cannot widen the envelope (extends `tests/test_options.py`).
- [ ] T14. Manifest normalization: `serviceSkills` parses identically from a
  v1alpha1 `agent.yaml` and a v1alpha2 profile; a limit above the catalog
  ceiling fails `validate_manifest`.
- [ ] T15. `to_context_sources()` records round-trip through
  `ContextSource.from_dict`/`to_dict` and carry `sha256:`-prefixed hashes.

## Rollback

Three levels, cheapest first.

1. **Runtime, no deploy:** set `MCTL_SERVICE_SKILLS=off` in the Argo
   ClusterWorkflowTemplates (`mctl-agents-implement`, `mctl-agents-investigate`).
   Every agent resolves an empty bundle, no git plumbing runs, and the prompts
   return byte-for-byte to their current form (T10 is the proof).
2. **Config, one PR here:** flip `spec.serviceSkills.enabled` to `false` in
   `agents/_manifests/implementer/agent.yaml` (task 13). For the declarative
   investigator, revert the mctl-gitops profile block (task 17) — or simply
   leave `ISSUE_INVESTIGATOR_RESOLVER_MODE=legacy`, which is already the
   default and never imports `orchestrator/resolver.py` at all.
3. **Full code revert:** drop `orchestrator/service_skills.py`, the three
   `ExecutionPlan` fields, the `AgentManifest.service_skills` field and the two
   `_build_prompt` call sites. Nothing else depends on them: no registry row,
   no `ExecutionRecord` column, no gitops state layout, and no target
   repository is harmed by an orphaned `.mctl/skills/` directory — with the
   feature gone it is simply unread. The mctl-gitops schema change (task 16) is
   additive and optional, so it can be left in place.

A target repository that needs to opt out unilaterally deletes or empties its
`.mctl/skills/manifest.yaml`; R5 makes absence a valid state.
