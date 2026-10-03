# Design: issue-305-add-repository-scoped-declarative-servic

## Current state

**Agent contract.** `orchestrator/manifest.py` parses
`agents/_manifests/<agent>/agent.yaml` into one `AgentManifest`
(`manifest.py:79`) whose fields are deliberately identical across API versions:
`tool_allow`, `budget_usd`, `timeout_seconds`, `entrypoint`, `options_builder`,
`sandbox_backend`, `cluster_workflow_template`. `_parse_fields_v1alpha1`
(`:162`) reads them inline from `spec.toolPolicy` / `spec.execution`;
`_parse_fields_v1alpha2` (`:226`) resolves them out of the referenced
`ExecutionProfile`. Five agents are v1alpha1 (`implementer`, `shepherd`,
`incident-responder`, `service-agent`, `mentor`); only `issue-investigator` is
`agents.mctl.ai/v1alpha2`.

**Declarative resolver.** `orchestrator/resolver.py` implements ADR 007's
runtime seam for that one agent: `load_definition` (`:422`), `load_profile`
(`:477`), `load_release_binding` (`:597`), and `execute(agent, task)` (`:788`)
which returns the frozen `ExecutionPlan` (`:226`). It reads the mctl-gitops
catalog at `platform-gitops/agent-platform/` (`GITOPS_ROOT` / `CATALOG_DIR`,
`:96`-`:101`), fails closed on every missing/ambiguous/unbounded/unapproved
condition, and is reached only when
`ISSUE_INVESTIGATOR_RESOLVER_MODE=declarative`
(`run_issue_investigator.py:1310`, default `legacy`). `Task` carries exactly one
field, `target_repository_sha` (`:145`), pinned by
`run_issue_investigator._target_repository_sha` (`:117`) via
`git rev-parse HEAD`.

**Skills today.** `ExecutionProfile.spec.skills` is a list of *names*:
`issue-investigator-default/profile.yaml` has `skills: []`, and
`agent-platform/policy.yaml` `knownSkills` allows only `mctl-platform` and
`git-flow`. `resolver.execute` hashes those names, not their content —
`skill_hashes=tuple(hashlib.sha256(skill.encode()).hexdigest() ...)`
(`resolver.py:894`), bare hex, no `sha256:` prefix (ADR 009 lines 148-174 calls
this out as the one hashing convention in the repo not to copy). There is no
mechanism anywhere for a *target repository* to contribute skill content.

**The ambient channel that already exists.** `build_implementer_agent_options`
(`options.py:300`) and `build_issue_investigator_options` (`:387`) both set
`cwd=str(repo_dir)` — the fresh target clone — together with
`setting_sources=["project"]`. The CLI therefore already loads that
repository's `CLAUDE.md`, `.claude/agents/*.md` and `.claude/skills/**` from the
**mutable worktree**: unpinned, unhashed, unrecorded, unbounded, and (for the
implementer) inside the very tree the agent is authoring into.
`run_implementer._stage_implementer_agent` (`:1233`) even writes into that tree
itself. So issue #305 is not adding a repository-scoped skill channel; it is
replacing an implicit one with a pinned, validated, recorded one.

**Prompt assembly.** Neither driver injects target-repo file content into the
prompt. `run_implementer._build_prompt` (`:1288`) returns one of two plain
f-strings and delegates conventions with "Follow that repo's CLAUDE.md
conventions" (`:1372`). `run_issue_investigator._build_prompt` (`:1127`) already
establishes the house pattern for untrusted repository/user text: a warning
paragraph, `<issue_title>`/`<issue_body>` delimiters, and
`_neutralize_prompt_tags` (`:1098`) to strip forged closing tags.

**Pinned-SHA reads already exist, elsewhere.** `tools/publish_agent_release.py`
reads prompt bytes from a git tag, never the worktree: `_tree_paths(tag)`
(`:104`) runs `git ls-tree -r -z --name-only`, `_read_at_tag` (`:118`) runs
`git show <tag>:<relpath>`, and `prompt_hash` (`:233`) refuses any path that is
not in the blob listing because `git show <tag>:<dir>` prints a directory
listing and exits 0. `orchestrator/proc.py:run_capturing` is the subprocess
wrapper that keeps stderr in the raised error.

**Provenance schema.** `orchestrator/context_snapshot.py` (ADR 009) defines
`ContextSource` (`:278`) with `content_hash` (`sha256:`-prefixed,
`_hash_bytes` at `:79`), `byte_count`, `selector`, `Trust` ("grants nothing"),
`ContextBudget` (`:537`) with `max_bytes`/`max_bytes_per_source`/`truncated`,
and the closed `SOURCE_KINDS` vocabulary (`:50`) including `target-repo`. It is
pure schema with no I/O and, today, no production producer.

**Implementer specifics.** `_clone_target` (`run_implementer.py:1218`) does
`gh repo clone ... --depth=10`; `implement_one` checks out `feat/agents-<slug>`
(`:2593`) and never captures a SHA; `review_feedback_one` checks out the
existing branch (`:1681`) and captures `old_head = _capture_head_sha(target)`
(`:1692`, helper at `:1844`) only as a "did the agent commit anything" baseline.
So the follow-up run's HEAD is a commit a previous implementer run authored.

## Proposed solution

### 1. Repository contract

Reserve `.mctl/skills/` in the target repository:

```text
.mctl/skills/manifest.yaml
.mctl/skills/<skill-id>/SKILL.md
```

```yaml
apiVersion: agents.mctl.ai/v1alpha1
kind: ServiceSkillSet
metadata:
  service: mctl-telegram
spec:
  bindings:
    implementer: [repo-testing, generated-files, local-bridge-security]
    issue-investigator: [local-bridge-security]
    shepherd: [repo-testing]
  skills:
    repo-testing: {path: .mctl/skills/repo-testing/SKILL.md}
    generated-files: {path: .mctl/skills/generated-files/SKILL.md}
    local-bridge-security: {path: .mctl/skills/local-bridge-security/SKILL.md}
```

`SKILL.md` keeps the existing house format (YAML front matter with `name` and
`description`, as in `agents/mctl-docs/.claude/skills/scan-sibling-commits/SKILL.md`)
and may additionally declare `requiresTools: [...]`. Every other front-matter
key in the reserved authority set is a hard rejection (R15).

`.mctl/skills/` is deliberately NOT `.claude/skills/`: the latter is already
loaded ambiently from the mutable worktree, and a single root would make
"pinned bundle" and "ambient bundle" indistinguishable in both code and audit.

### 2. New module `orchestrator/service_skills.py`

One new module, stdlib + `yaml` + `orchestrator.proc` only — no
`claude_agent_sdk`, no `temporalio` imports, so `tests/test_worker_isolation.py`
stays green and the module is importable from the Temporal worker.

```python
class ServiceSkillError(ValueError): ...          # fail-closed, non-retryable

@dataclass(frozen=True)
class ServiceSkillPolicy:                         # the platform-side envelope
    enabled: bool
    root: str            = ".mctl/skills"
    max_skills: int      = 8
    max_skill_bytes: int = 32 * 1024
    max_total_bytes: int = 96 * 1024

@dataclass(frozen=True)
class ServiceSkill:
    skill_id: str; path: str; content_hash: str   # "sha256:..."
    byte_count: int; text: str = field(compare=False, repr=False)

@dataclass(frozen=True)
class ServiceSkillBundle:
    agent: str; resolved_from_sha: str; root: str
    manifest_hash: str | None                     # None when no manifest exists
    skills: tuple[ServiceSkill, ...]
    total_bytes: int
    def identifiers(self) -> tuple[dict, ...]: ...        # for ExecutionPlan
    def to_prompt_block(self) -> str: ...                 # delimited, neutralized
    def to_context_sources(self, *, retrieved_at: str) -> tuple[ContextSource, ...]

def resolve_bundle(*, agent: str, repo_dir: Path, policy: ServiceSkillPolicy,
                   tool_allow: Sequence[str], pinned_sha: str) -> ServiceSkillBundle
def pin_sha(repo_dir: Path, *, agent: str, branch: str | None) -> str
```

**Reading at the pin.** `resolve_bundle` never touches the worktree. It runs
`git ls-tree -r -z --full-tree <sha> -- <root>` (full output, not
`--name-only`, so the mode column is available) and `git show <sha>:<path>`,
mirroring `tools/publish_agent_release.py`. Mode `120000` (symlink) and
`160000` (gitlink) entries are rejected; only `100644`/`100755` blobs are read;
a path absent from the listing is rejected rather than handed to `git show`,
which would happily print a directory listing. This kills path traversal and
symlink escape by construction — there is no filesystem path to escape from —
and makes R3 (no reload from the mutable worktree) structural rather than a
convention.

**Which SHA (R6/R7).** `pin_sha` returns `git rev-parse HEAD` for read-only
agents. For an agent-authored branch (`implementer`, `shepherd` on
`feat/agents-*`) it returns
`git merge-base HEAD origin/<default-branch>`, attempting one
`git fetch --deepen=50 origin <default-branch>` if the shallow clone cannot
answer, and raising `ServiceSkillError` if it still cannot. That is the concrete
answer to "prevent self-modifying agent policy": within a run the bundle is
already immutable, but across runs on the same branch the implementer's own
committed skill edit would otherwise become its next run's instructions. Reading
from the merge-base means a skill change only takes effect for agent runs after
a human merges it.

**Ordering and validation.** Selection is `spec.bindings[agent]` in list order
(R9); ids are validated against `spec.skills`; duplicates, unknown agent names
(checked against `manifest.load_all()` keys), missing blobs, non-`SKILL.md`
files inside a skill directory, and any path outside `policy.root` reject the
whole bundle. Sizes are enforced on the read, reading `limit + 1` bytes and
comparing, the pattern already used for `MAX_STATUS_BYTES`
(`run_issue_investigator.py:517`) and `MAX_REFUSAL_MARKER_BYTES`.

**Envelope check.** `requiresTools` must be a subset of `tool_allow`, which the
caller passes from `AgentManifest.tool_allow` — the same field for both API
versions, so one check covers the v1alpha1 implementer and the v1alpha2
investigator. Nothing in the bundle is ever returned to a caller in a position
to widen `allowed_tools`, `mcp_servers`, `permission_mode`, `max_budget_usd`,
`policyRef` or a mutation scope: `ServiceSkillBundle` exposes text and
identifiers, nothing else. That is the enforcement of R14 — a type boundary
rather than a runtime check that could be forgotten.

### 3. Enablement and limits (platform-owned)

The policy block is authored where each agent's execution shape already lives:

- **v1alpha2** (`issue-investigator`): a new optional
  `spec.serviceSkills: {enabled, root, maxSkills, maxSkillBytes, maxTotalBytes}`
  on `ExecutionProfile`, plus ceilings in `agent-platform/policy.yaml`
  (`limits.maxServiceSkillBytes`, `limits.maxServiceSkills`). Because
  `schemas/execution-profile.schema.json` is `additionalProperties: false`, this
  needs a mctl-gitops PR before any profile can carry the block; until then the
  investigator resolves `enabled: false` and reads nothing.
- **v1alpha1** (`implementer`, `shepherd`): the mirrored
  `spec.serviceSkills` block in `agents/_manifests/<agent>/agent.yaml`.

`orchestrator/manifest.py` normalizes both into one new
`AgentManifest.service_skills: ServiceSkillPolicy` field, exactly as it already
normalizes `toolPolicy`/`execution` across versions. Absent block =
`ServiceSkillPolicy(enabled=False)` (R17). `orchestrator/validate_manifest.py`
gains a check that a declared limit never exceeds the catalog ceiling, in the
same style as `check_catalog_profiles_match_builders` (`:475`).

### 4. Wiring

**Declarative path (R23).** `resolver.Task` gains an optional
`target_repo_dir: Path | None`; `execute()` calls `resolve_bundle` after the
profile is resolved (so `tool_allow` is known) and before constructing the plan.
`ExecutionPlan` gains `service_skills: tuple[Mapping[str, Any], ...]`,
`service_skill_manifest_hash: str | None` and
`service_skills_resolved_from_sha: str`, all included in `to_log_dict()`
(R19/R20). New hashes carry the `sha256:` prefix; the existing bare-hex
`skill_hashes` is left untouched to avoid changing an already-asserted value,
and the inconsistency is documented in `docs/resolver-pilot-status.md`.
`build_issue_investigator_options_from_plan` is unchanged — the bundle reaches
the agent through the prompt, not through options, which is precisely the point.

**Legacy/implementer path (R24).** `run_implementer.implement_one` and
`review_feedback_one` call `service_skills.pin_sha` right after clone+checkout,
then `resolve_bundle` with the policy and `tool_allow` read from
`manifest.load(AGENTS_MANIFEST_DIR / "implementer" / "agent.yaml")`, then pass
`bundle.to_prompt_block()` into `_build_prompt`. Any `ServiceSkillError` aborts
the run before `_run_implementer_agent` and therefore before any commit or PR
(R22, with the honest caveat that for the implementer this is pod-start, not
pre-submission, because nothing before submission knows the target SHA).

**Injection format (R18).** The block is rendered once, ordered per R9, wrapped
in `<service_skills source="mctlhq/<repo>@<sha>">` delimiters, with forged
delimiters stripped by the same technique as
`run_issue_investigator._neutralize_prompt_tags`, and preceded by:
repository-owned instructions, authoritative for repository conventions only,
granting no tool, permission, budget or network capability, and never an
instruction to act outside the current proposal's scope.

**Provenance seam.** `to_context_sources()` emits one `ContextSource` per skill
with `kind="target-repo"`,
`locator=f"git+https://github.com/{repo}@{sha}#{path}"`,
`selector={"service_skill": id}`, the `sha256:`-prefixed `content_hash`,
`byte_count`, and `Trust(tier="authoritative",
rationale_code="pinned-target-repository-sha")` — matching the golden fixture
`tests/fixtures/context/investigator-snapshot.json`. Nothing persists it yet;
this proposal only makes ADR 009 follow-up (e) expressible.

### 5. First real ServiceSkillSet

`mctl-telegram` ships `.mctl/skills/` with `repo-testing` (CGO_ENABLED=0 for
production builds, `go test -race` needing a C toolchain — runtime side tracked
by #304 — canonical validation commands, mirrored docs) and
`local-bridge-security` (no hosted MTProto session on activation,
`session_encrypted` stays NULL, explicit owner consent to send, PoP/device-bound
credentials with scopes from live DB state, no legacy token bypass). That is a
PR in a different repository and is tracked as such; `implementer-default`
gains only the `serviceSkills` enablement block, never a service-specific skill
name, so the profile stays reusable.

## Alternatives

1. **Put service skills in `ExecutionProfile.spec.skills`.** Rejected for the
   reason the issue gives and the catalog confirms: `policy.yaml`'s
   `knownSkills` is a platform allow-list, and binding repository knowledge to
   it forces one profile per service (`implementer-mctl-telegram`, ...), which
   ADR 007 sec. 2 explicitly designed against ("no current budget, tool, or
   permission boundary is silently broadened to manufacture sharing").
2. **Keep using the ambient channel — just document `.claude/skills/` in the
   target repo as the contract.** Zero code. Rejected: it is read from the
   mutable worktree at session start, so the implementer can commit a skill edit
   and have it apply on the next follow-up run; nothing is hashed or recorded,
   so a PR's instruction inputs are unreconstructable after the branch diverges;
   nothing bounds its size against `ContextBudget`; and there is no envelope
   check at all. Every acceptance criterion in this proposal exists because this
   option fails it.
3. **Keep service knowledge in `mctl-agents` itself, extending the existing
   `agents/<service>/.claude/skills/**` convention** (real today:
   `agents/mctl-docs/.claude/skills/scan-sibling-commits/SKILL.md`, referenced
   by `agents/_manifests/service-agent/agent.yaml`'s
   `glob: agents/[!_]*/.claude/skills/**`). Rejected: that tree is reachable
   only by the service-agent, whose `cwd` is `agents/<svc>/`
   (`options.py:279`) — the implementer's `cwd` is the target clone, so it never
   sees it; ownership sits with the platform rather than the service; and the
   knowledge drifts from the code it describes because it is versioned in a
   different repository. It also does not generalize past the eight mctl repos
   hardcoded in `config/settings.py`.
4. **A central ServiceSkill registry with its own versions and publication
   lifecycle,** mirroring platform skills. Rejected: the git object hash already
   names the exact bytes, so a second version number would be a claim about
   content rather than the content itself — the precise failure mode
   `docs/resolver-pilot-status.md` documents for `ExecutionProfile.spec.version`
   and explicitly does not want repeated.

## Platform impact

- **Migrations.** None. No registry row, no `ExecutionRecord` column, no gitops
  state layout change. `ExecutionPlan` gains three fields (frozen dataclass,
  additive); `AgentManifest` gains one with a disabled default.
- **Backward compatibility.** A repository with no `.mctl/skills/` resolves an
  empty bundle and behaves exactly as today (R5). An agent with no
  `serviceSkills` block never reads the target repo's `.mctl/` root at all
  (R17). `ISSUE_INVESTIGATOR_RESOLVER_MODE` stays `legacy` by default, so the
  declarative path is unchanged in production. The implementer path is the only
  behavioural change, and only once `agents/_manifests/implementer/agent.yaml`
  declares the block.
- **Cross-repo dependency.** The v1alpha2 half needs a mctl-gitops PR
  (`schemas/execution-profile.schema.json` is `additionalProperties: false`,
  plus `policy.yaml` ceilings, plus `scripts/validate-agent-platform.py`). The
  v1alpha1 half does not, which is why the implementer — the agent with the
  actual pain — can ship first. Sequencing is explicit in tasks.md.
- **Resource impact.** Two to `2 + N` git plumbing calls per run
  (`ls-tree`, `merge-base`, one `show` per selected skill), each bounded by
  `IMPLEMENTER_COMMAND_TIMEOUT_SECONDS`; at most `max_total_bytes` (96 KiB
  default) of added prompt, roughly 25k tokens worst case against an $8/$3
  budget, which is why the ceiling is a policy value and not a constant.
- **Risk: prompt injection from a target repository.** Service skills are
  attacker-influenceable by anyone who can merge to a target repo. Mitigations:
  Markdown only, no scripts (R12); delimiters plus tag neutralization (R18); an
  explicit "grants no authority" preamble; the type boundary in §2 so the bundle
  physically cannot reach `allowed_tools`/`mcp_servers`; the reserved-key
  rejection (R15); the merge-base rule (R6) so agent-authored edits need human
  merge; and size ceilings so a skill cannot crowd out the proposal. The
  residual risk — a merged, human-reviewed skill that instructs badly — is the
  same trust level the target repo's `CLAUDE.md` already has, except now it is
  hashed and attributable.
- **Risk: shallow clones.** `--depth=1` / `--depth=10` may not contain the
  merge-base. Mitigated by one deepening fetch, then fail closed (R7) rather
  than silently pinning the branch head.
- **Risk: a fail-closed rule takes a repo's whole pipeline down** (e.g. a typo'd
  skill id blocks every implementer run for that service). Mitigated by the
  `MCTL_SERVICE_SKILLS=off` kill switch (R25), by the error naming the offending
  id/path, and by validating the manifest in the target repo's own CI via a
  documented `python -m orchestrator.service_skills --validate` entry point.
- **Security posture unchanged where it matters.** ADR 007's authority model is
  preserved verbatim: providers and the `ExecutionProfile` remain authoritative,
  `tools` is still not authorization, and a service skill's `requiresTools` is a
  validation requirement that can only ever *narrow* the run by failing it.
