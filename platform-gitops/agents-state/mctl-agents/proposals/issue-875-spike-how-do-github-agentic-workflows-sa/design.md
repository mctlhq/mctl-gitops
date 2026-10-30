# Design: issue-875-spike-how-do-github-agentic-workflows-sa

## Current state

DevLoop guardrails that line up with gh-aw's four guardrails, as read in the clone and in gitops:

- **Output mediation (gh-aw "safe outputs" analog).** The investigator never writes to the live proposal.
  `orchestrator/run_issue_investigator.py:_staging_dir` creates `.staging-*` under
  `agents-state/<service>/`, which sits outside the CWFT's commit glob. After publish,
  `_landed_triplet_defects` re-checks through a directory fd that `TRIPLET` and `.status.yaml` are regular
  files and that the status still says what the orchestrator wrote. This blocks forged `accepted`
  approvals. `_ReadOnlyDirsHook` / `_read_only_dirs_hooks` (`orchestrator/options.py:1175-1205`) deny
  edits to the gitops reference directories. The orchestrator, not the agent, posts the proposal comment
  (`post_proposal_comment`) and runs the commit-and-push step in the CWFT. The implementer's push and PR
  are also orchestrator code: `run_implementer.py` `git push --force-with-lease` (lines 2596, 4425) and
  `_open_pr_for_branch` (line 3761). Human clarification is a structured output (`human-input/draft.json`,
  ADR 013, `orchestrator/human_input.py` with `_reject_unknown_keys`). None of these outputs has a
  per-type count limit or content validation of the kind gh-aw documents (body length bounds, placeholder
  rejection, `max` per output type).
- **Permission defaults.** Profiles under mctl-gitops `agent-platform/execution-profiles/*/profile.yaml`
  declare `permissions.repository.{read,branchCreate,commit,pullRequestCreate,merge}`,
  `mutationScopes` and `approval.requiredBefore`. `agent-platform/policy.yaml` fails closed on unknown
  references. ADR 014 (`orchestrator/policy_checkpoint.py` `decide()`/`checkpoint()`) gates MCP tool calls
  default-deny (`no_matching_rule`, `grant_missing`) through `_policy_hooks` (`options.py:1071`). The
  agent's SDK tool grant is still broad, though: `build_issue_investigator_options` grants
  `Read, Write, Edit, Glob, Grep, WebSearch, WebFetch, Bash` with `permission_mode="acceptEdits"`
  (`options.py:1304-1314`, `1377-1388`, `1527-1540`). The investigate CWFT puts a `GITHUB_TOKEN`
  (`mctl-agents-secrets/github-token`, documented as needing `issues: write`) into the same container the
  agent's `Bash` runs in (`cwft-mctl-agents-investigate.yaml` around line 839). gh-aw's model, by
  contrast, gives the agent job no write permission at all. Tracked overlap: #807 G2, #852 D2/D4 -> #869.
  `MCTL_TOKEN` was already removed from this container (#717); that is the same credential-separation
  pattern applied to mctl.
- **Network/sandbox isolation.** Agents run in per-pod Argo CWFTs with `emptyDir` workdirs (#852 F1).
  Egress goes through the `mctl-agents-egress-proxy` Squid, whose `proxy.yaml` ends with
  `http_access allow all`. No agents egress NetworkPolicy exists yet (`argo-workflows/config/` has only
  `networkpolicy.yaml`). Profiles still state `network: approved-providers-only`, which is not enforced
  (#807 G1, #830 stages B/C). The kernel is shared (#807 G5). Provider-side WebSearch bypasses pod egress
  (#852 D1 -> #870). gh-aw's AWF domain allowlist plus micro-VM is the direct analog.
- **Threat detection.** Before merge there are review workflows (`.github/workflows/claude-review.yml`,
  `agy-review.yml`, `security.yml`) and the shepherd/merge approval of ADR 016. Nothing scans the agent's
  output before the orchestrator publishes it. gh-aw runs a dedicated detection job between the agent and
  the safe-output jobs.
- **Spike conventions.** Reports live in `docs/spikes/<n>-<slug>.md` with one `STATUS:` line and a fixed
  table that a guard test checks (`tests/test_spike_852_report.py`, `tests/test_spike_830_report.py`).
  `orchestrator/spike_issue.py` makes the implementer emit `Refs`, not `Closes`, for spike issues.

Deployed state checked:
- `$MCTL_GITOPS_ROOT/agent-platform/execution-profiles/issue-investigator-default/profile.yaml`: tools
  include Write/Edit/Bash/WebSearch/WebFetch; `network: approved-providers-only`; repository writes all
  false; mutationScopes `proposal-directory-write`, `issue-comment`.
- `$MCTL_GITOPS_ROOT/agent-platform/policy.yaml`: fail-closed reference lists; `approvedSandboxes` backend
  `argo` with named CWFTs.
- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-investigate.yaml`: `GITHUB_TOKEN`
  from secret `mctl-agents-secrets` key `github-token` in the run container; `MCTL_TOKEN` absent (#717).
- `$MCTL_GITOPS_ROOT/infra-components/mctl-platform/mctl-agents-egress-proxy/proxy.yaml`:
  `http_access allow all` at line 47.
- `$MCTL_GITOPS_ROOT/argo-workflows/config/`: no agents egress NetworkPolicy file.
- WebSearch grants per profile (grep): implementer 1, issue-investigator 1, service-agent 2, others 0.
- gh-aw GA changelog (fetched): read-only default permissions, safe outputs, sandboxed container behind
  AWF, optional Cloud Hypervisor / micro-VM, threat detection job, Copilot CLI default engine or BYO agent.
- gh-aw safe-outputs reference (first 100k of 183k characters fetched): agent has no write permission;
  separate permission-scoped jobs execute requests from `agent_output` / `$GH_AW_AGENT_OUTPUT`; per-type
  `max` (create-issue 1, add-comment 1, add-labels 5); body validation; label filters. The later sections
  (staged mode, threat detection details) were not read.
- No mctl MCP tool calls were made. This spike concerns cron/CWFT agents that are not a tenant service,
  and the gitops files above are the deployed source of truth. Live pod state was not observed.

## Proposed solution

A docs-only spike, with the same shape and guard-test discipline as #852:

1. **Report** `docs/spikes/875-gh-aw-guardrail-comparison.md`:
   - `STATUS:` one of `DRAFT`, `ADOPT_PATTERNS`, `REFERENCE_ONLY`, `NO_ACTION`.
   - `## 1. Source and limits`: URLs, what was and was not retrieved, and the date checked.
   - `## 2. Canonical boundaries`: Temporal/Argo, ADR 014, ExecutionProfiles, ADR 013/016/018/021 stay
     authoritative. gh-aw is a pattern source only.
   - `## 3. Comparison`: a 7-column table (`id | dimension | gh_aw_pattern | devloop_today | status |
     owner | follow_up`). Expected starting rows, to be re-verified at implementation:

     | id | dimension | gh-aw pattern | DevLoop today | expected status |
     |---|---|---|---|---|
     | S1 | safe outputs | agent emits structured requests; a separate job executes them | staging dir + `_landed_triplet_defects`; orchestrator commits, comments, pushes, opens PRs | already-covered |
     | S2 | safe outputs | per-output-type `max` and content validation (body bounds, placeholder rejection, label filters) | no count limit or content check on comments, human-input drafts, or triplet size | adopt |
     | S3 | safe outputs | staged/preview mode with no side effects | `trigger_shepherd`/`reconcile` `dry_run`; investigator has none | not-observed (gh-aw details unread) |
     | P1 | permissions | agent job holds no write credential | `GITHUB_TOKEN` with `issues: write` sits in the agent container | covered-by-852 (#869) plus adopt the explicit target "agent container holds read-only GitHub credentials" |
     | P2 | permissions | read-only default for tools | profile tools broad, `acceptEdits`; MCP default-deny via ADR 014 | covered-by-852 (#868/#869) |
     | N1 | network | AWF domain allowlist | Squid `allow all`; NetworkPolicy stage C not started | covered-by-807 (G1, #830) |
     | N2 | sandbox | micro-VM option | shared kernel | covered-by-807 (G5) |
     | N3 | network | provider-side tools | WebSearch bypasses pod egress | covered-by-852 (#870) |
     | T1 | threat detection | detection job between agent and output jobs | PR review workflows + ADR 016 gate after the PR exists; nothing before publish | adopt (evaluate) or not-observed if gh-aw detection details stay unread |
     | R1 | reusable enforcement | declarative frontmatter compiled to a locked workflow | ExecutionProfile + `policy.yaml` + `validate_manifest.py` | already-covered |
     | I1 | interop | gh-aw workflow calling mctl via Actions OIDC/MCP | deploy endpoint accepts Actions OIDC; no MCP path | not-applicable now; recorded |
     | I2 | interop | BYO engine in gh-aw | Claude Agent SDK pinned in `pyproject.toml` | not-applicable |

   - `## 4. Decision`: the owner's token and the date.
   - `## 5. Follow-ups`: one issue per `adopt` row, each with owner repo, control and rollback. Expected:
     (a) an orchestrator-side output limiter that applies per-type count caps and content validation
     before `post_proposal_comment`, `gh pr create` and human-input draft acceptance, routed through the
     ADR 014 checkpoint as a rule rather than a new mechanism; (b) a pre-publish output scan stage
     (evaluation only); (c) a note on #869 adding the "no write credential in the agent container" target.
2. **Guard test** `tests/test_spike_875_report.py`, modelled on `tests/test_spike_852_report.py`: one
   STATUS line with an allowed value, 7-cell rows, non-empty evidence, allowed status values, all six
   dimensions present, every `adopt` row with a non-empty follow_up, and no token-shaped strings.

Why this way: it follows the established spike pattern, keeps the decision with the owner, and sends each
real change through its own reviewable issue. It does not duplicate #807/#852 work.

## Alternatives

- **Run DevLoop stages on gh-aw.** Rejected. The issue's boundary forbids it, and it would move identity,
  approval and evidence out of MCTL.
- **Adopt safe-output limits directly in this PR.** Rejected. A spike must not change runtime behaviour
  before an owner decision, and the limiter belongs in the ADR 014 checkpoint, which needs its own design.
- **Fold everything into #807/#852.** Rejected. S2 (output count/content limits) and T1 (pre-publish
  detection) are not covered by either, and folding them in would lose them.

## Platform impact

- Migrations: none. Backward compatibility: unaffected, since the change is docs plus one test.
- Resources: none at runtime. CI gains one small pytest file.
- Risk: claims rest on partially retrieved gh-aw docs. Mitigation: unverified rows are `not-observed` and
  cannot justify `adopt`.
- Risk: the evidence line numbers in the report drift. Mitigation: cite symbol names as well as lines,
  as #852 does.
- Risk: the implementer auto-closes the spike. Mitigation: `orchestrator/spike_issue.py` already forces
  `Refs`.

## Open questions

- Unread gh-aw sections (AWF rules, threat detection internals, staged mode, integrity filters). The
  affected rows stay `not-observed` until they are read.
- Owner's decision token. Expected `ADOPT_PATTERNS` for S2 and P1/T1, not presumed.
- Whether interop via Actions OIDC to mctl MCP (I1) is wanted at all.
- Live pod and Squid state not observed. This is inherited from #830.
