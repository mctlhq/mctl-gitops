# Design: issue-852-spike-do-the-sandbox-isolation-gaps-desc

## Current state

Agent isolation in mctl has two layers.

**Pod layer (mctl-gitops, owned by the #807 spike).** Each agent runs as one Argo step built from a
`cwft-mctl-agents-*.yaml` ClusterWorkflowTemplate. The #807 proposal
(`agents-state/mctl-agents/proposals/issue-807-spike-which-kubernetes-primitives-rbac-n/design.md`,
status `implemented`, PR mctlhq/mctl-agents#810 open) already ranks six gaps:

| #807 gap | What it covers |
|---|---|
| G1 | No egress control on agent pods |
| G2 | Credentials in env |
| G3 | Shared `argo-workflows` namespace and namespace-wide ingress admits |
| G4 | No namespace PSA, `readOnlyRootFilesystem` unset |
| G5 | No sandbox runtime (shared kernel) |
| G6 | No compute quota |

PR #810 adds `tools/agent_isolation_audit.py`, `docs/spikes/807-agent-isolation-k8s.md`,
`tests/test_agent_isolation_audit.py` and `tests/test_spike_807_report.py`. None of these is on `main` in
this clone yet. #830 (open, `spike:scout`) covers runtime observability and egress detection for the
"package install reached the internet" escape.

**Process layer (this repo, not covered by either spike).** The controls inside the agent process are
in-process:

- `orchestrator/options.py` `_policy_hooks()` registers the policy checkpoint (`_PolicyCheckpointHook`,
  ADR 014) with `HookMatcher(matcher="mcp__.*")`. Only MCP tool calls are policy-evaluated.
- `orchestrator/options.py` `_command_audit_hooks()` registers `_audit_pre_tool_use` on `Bash`. It prints
  an `AUDIT tool=Bash cmd=...` line and returns `{}`. The hook audits commands but never denies them.
- The builders around `orchestrator/options.py:1304` and `:1377` (service-agent and implementer families)
  grant `Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash` plus `mcp__mctl__*`, with
  `permission_mode="acceptEdits"`. `WebSearch` executes on the model provider's side, so the pod's
  NetworkPolicy, which is what #807 G1 recommends, cannot see or block it.
- `setting_sources=["project"]` is set on several builders (`options.py:1307`, `:1380`, `:1399`, `:1483`).
  The comment at `options.py:293-295` states that for the issue-investigator "cwd is a fresh clone of the
  TARGET repository, so setting_sources=["project"] loads whatever `.claude/agents/*.md` that repository
  ships". Agent configuration is therefore partly controlled by the target repository's contents.
- `orchestrator/run_implementer.py` `_TYPECHECK_ENV_KEEP` (around line 4264) is an env allowlist for the
  type-check child. It exists because "`uv sync` runs build backends and mypy runs plugins, both taken from
  the clone", following claude P2 on #787. This is the only place that strips credentials from a child
  that runs repo code. The model's own `Bash` tool inherits the full pod env.
- `tests/test_worker_isolation.py` enforces the orchestration/agent split from ADR-005/006: the Temporal
  worker must not import `claude_agent_sdk`, `run_implementer` or `orchestrator.auth`.
  `tests/test_portable_runtime_isolation.py` enforces the containment of `experiments/`.
- Spike convention: `docs/spikes/796-rea-investigation-evidence.md` has a `STATUS: <TOKEN>` line, and
  `tests/test_spike_796_report.py` checks for the draft marker or exactly one token. It also checks that
  `orchestrator`, `config` and `agents/_manifests` are unchanged against `origin/main`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`: per-pod
  `workdir` is an `emptyDir` (line ~196). The comments at lines 27 and 167 say "There is no shared workdir
  volume", replacing the earlier PVC. Cross-run filesystem persistence therefore looks closed for the
  implementer.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`: the same
  spec-level `emptyDir`, with a `sizeLimit` (lines 177-184).
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/implementer-default/profile.yaml`: `tools` lists
  `Bash`, `WebSearch`, `WebFetch` and `mcp__mctl__*`. This matches `options.py`.
- `agents-state/mctl-agents/proposals/issue-807-.../.status.yaml`: `status: implemented`,
  `pr: .../pull/810`, `github.state: open`.
- `gh pr view 810`: open. It adds the four files listed above.
- `gh issue view 830`: open, scope as summarised above. No proposal directory for #830 exists under
  `agents-state/mctl-agents/proposals/`.
- WebFetch of the source article: returned only site navigation and the title. **The article body was not
  observed.**
- mctl MCP tools: not used. No service or tenant state is relevant to a docs-only spike. Live cluster
  state was not observed.

## Proposed solution

This is a spike, so the deliverable is evidence and a decision, not a platform change. There are two
artefacts.

### 1. `docs/spikes/852-sandbox-isolation-delta.md`

The report has these sections:

1. **Source and limits.** The article URL, whether its body was retrieved, and the taxonomy used: the
   article's sections if retrieved, otherwise the title-derived categories listed in requirements.md.
2. **Coverage map.** One row per taxonomy category, mapped to `covered-by-807:G<n>`, `covered-by-830`,
   `new` or `not-observed`.
3. **Delta gap list.** The issue's requested outcome. The rows below are candidates from this
   investigation. The implementer confirms each against the cited code and either keeps it or demotes it to
   `not-observed` or `covered-by-*`:

| id | layer | gap | evidence | expected status | recommended control | owner |
|---|---|---|---|---|---|---|
| D1 | tool | Web tools granted to execution profiles (`WebSearch` and `WebFetch`, plus any other server-executed tool) may run on the model provider's side rather than in the pod's network path. Where they do, #807 G1 egress policy and #830 egress detection cannot see them, and query strings or fetched URLs can carry data. The execution boundary of each tool is to be established from the pinned SDK/CLI, not assumed. | `options.py:1304`, `:1377`; `implementer-default/profile.yaml` tools | new, medium (one verdict per tool: `WebSearch`, `WebFetch`) | Drop `WebSearch` from profiles that do not need it, or route it through an MCP tool so the policy checkpoint mediates it | mctl-gitops (profiles) and mctl-agents (`options.py`) |
| D2 | tool | `Bash` is audit-only. No PreToolUse deny path exists for shell commands, so the app layer has no policy ceiling for shell. | `_command_audit_hooks`, `_audit_pre_tool_use` | new, medium (pod controls remain the backstop) | Policy-mediated `Bash` with credential-separated execution: model shell runs without long-lived credentials in its env, and credentialed operations (git push, `gh`, registry auth) go through a mediated helper or MCP tool behind the policy checkpoint. A pattern deny-list hook may be added only as defence in depth and is never recorded as the control | mctl-agents |
| D3 | config | Agent configuration is loaded from the untrusted target-repo clone through `setting_sources=["project"]`, which loads at least `.claude/agents` and `.claude/skills`. Whether settings and hooks are also loaded must be verified against the pinned SDK. | `options.py:293-295`, `:1307`, `:1380` | new, severity depends on verification (high if hooks load) | Use `setting_sources=[]` for target clones and load personas only from the image, or allowlist which `.claude` paths are read | mctl-agents |
| D4 | code-exec | Untrusted repository code (builds, tests, package installs run by the model through `Bash`) runs with the full pod env. Only the type-check child is env-scrubbed. | `run_implementer.py` `_TYPECHECK_ENV_KEEP` | covered-by-807:G2 (credentials) plus a new sub-gap: apply the same allowlist to model `Bash` | Run model `Bash` with a scrubbed env and git/gh credentials through a helper | mctl-agents |
| D5 | input | Untrusted issue and PR text enters prompts. The only mitigation is tag-wrapping in prompts, so the effective boundary is the capability ceiling (D1-D4). | investigator prompt template; `run_issue_investigator.py` | new-informational, low | None separate. Covered by fixing D1-D4 | - |
| -- | kernel | Shared node kernel | #807 G5 | covered-by-807 | - | - |
| -- | network | Pod egress | #807 G1, #830 | covered | - | - |
| -- | fs | Cross-run filesystem persistence | CWFT `emptyDir` | not a gap (enforced) | - | - |
| -- | resources | Quota and fan-out | #807 G6 | covered-by-807 | - | - |

4. **Decision.** The recommended token is `NEW_GAPS_FOLLOW_UP` if D1, D2 or D3 is confirmed `new`, and
   `NO_NEW_GAPS` otherwise. `FOLD_INTO_807` applies if the owner prefers to extend #807's matrix with the
   process layer. The report merges as `STATUS: DRAFT` unless the owner records the token.
5. **Follow-ups.** One draft issue body per confirmed `new` gap: title, owner repo, control and rollback
   note. The issues are not filed by the spike.

### 2. `tests/test_spike_852_report.py`

This test is modelled on `tests/test_spike_796_report.py`. It checks four things:

- the report has `STATUS: DRAFT` or exactly one of the three tokens;
- every gap-table row has a non-empty `evidence` cell and a `status` from the closed set
  `new | covered-by-807 | covered-by-830 | not-observed | not-a-gap`;
- `orchestrator/`, `config/` and `agents/_manifests/` are unchanged against `origin/main` (the test skips
  if there is no `origin/main`);
- the report contains no token-shaped strings. The regex covers `ghp_`, `gho_`, `sk-ant-` and
  `-----BEGIN`.

## Alternatives

1. **Close #852 as a duplicate of #807 and #830 with no artefact.** This is the cheapest option, but code
   reading already shows process-layer candidates (D1-D3) that neither spike scopes. #807 explicitly says
   the in-process controls do not mediate `Bash`, but it ranks only pod primitives. Closing without
   evidence would leave those gaps untracked. Dropped.
2. **Extend PR #810's auditor to the process layer.** This would couple an open PR to new scope and turn a
   YAML auditor into a Python AST analyser of `options.py`. It is recorded as the `FOLD_INTO_807` option
   for the owner, but not done here.
3. **Fix D1-D3 directly.** Changing tool grants or `setting_sources` alters agent behaviour across every
   builder and needs its own review and rollout. It is out of scope for a spike. Dropped in favour of
   follow-up issues.

## Platform impact

- **Migrations / backward compatibility:** none. The change is one Markdown report and one test.
- **Resource impact:** none at runtime.
- **Risks and mitigations:**
  - *The report becomes a map of weaknesses.* It cites only configuration already visible in the repo and
    in gitops, with no payloads or secret values, and the guard test rejects token-shaped strings.
  - *Gaps are overstated from an unread article.* Every row needs code evidence or is marked
    `not-observed`, and the article-access limitation is stated in section 1.
  - *#810's numbering drifts.* The report cites #807 gaps by name as well as by number, and records the
    PR #810 head SHA the coverage map was built against (`7b1c9267f5cf80d738e3b2f3134415740402d764` at amendment time, while #810 is
    open and draft). Before the spike PR merges, the implementer compares that SHA with #810's current head
    and re-checks the mapping if it moved.
