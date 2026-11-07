# Design: issue-1032-devloop-997-s1-deterministic-offline-imp

## Current state

Nothing in `mctlhq/mctl-agents` evaluates implementability today.

- **Digest.** `orchestrator/proposal_state.py` defines
  `PROPOSAL_DIGEST_FILES = ("requirements.md", "design.md", "tasks.md", "proposed-content.md")`
  and `content_digest_of(files)`, a length-prefixed sha256 pinned by
  `tests/test_proposal_digest.py`. The approval grant binds this digest. S1
  reuses it read-only and changes neither the files nor the function.
- **Investigator template.** `orchestrator/run_issue_investigator.py` (around
  line 2273) gives the tasks format `- [ ] 2. <task> (depends on 1) — DoD: ...`.
  It does not parse the result.
- **Real `tasks.md` shapes** (read from `$MCTL_GITOPS_ROOT/agents-state`):
  - `mctl-agents/proposals/issue-997-*/tasks.md`: 8 tasks. Most
    `(depends on N)` clauses sit alone on a line after nested sub-bullets
    inside the task block.
  - `issue-993-*`: 17 tasks under `## Part M`. Ids include `4b`. Clauses
    include `(depends on 3 and 4b)`, `(depends on 4-11)` and
    `(depends on 10, 1)`. Task 10 is a spike, and one task "must be merged and
    live before the switch is turned on".
  - `issue-996-*`: inline `(depends on 0)` and `(depends on 0-4)`. Ids include
    `3b`.
  - `issue-1021-*`: 11 tasks under `## Implementation`, including `5a`, with
    `T-10`-style test references in DoD text.
  - `issue-414-*`: 8 dense single-line tasks.
  - `mctl-gitops/proposals/issue-911-*/tasks.md`: `(depends` wraps to `on 4)`
    on the next line, and "After merge, confirm ArgoCD ..." is a post-merge
    gate.

  Non-task sections seen: `## Tests`, `## Rollback`, `## Release blockers (not M1 acceptance)`.
- **Implementer capabilities.**
  - `orchestrator/run_implementer.py` clones only `mctlhq/{service}` at the
    default branch, so it has single-repo write authority and one base.
  - The prompt (around line 2190) asks for a Conventional Commits subject "like
    `feat(agents): {ref.slug}` (or fix:/chore: as appropriate)" and allows
    "multiple small commits".
  - `agents/mctl-agents/.claude/agents/implementer.md` says "two or three small
    commits are fine; a dozen is not".
  - `agents/_manifests/implementer/agent.yaml` declares `budgetUsd: 3.00`,
    `timeoutSeconds: 900`.
  - `orchestrator/options.py` reads `IMPLEMENTER_BUDGET_USD` (default `3.00`),
    `IMPLEMENTER_TIMEOUT_SECONDS` (default `900`) and
    `IMPLEMENTER_TIMEOUT_CEILING_SECONDS` (default `1800`, used for review
    work).
- **Record style precedent.** `orchestrator/implementation_completion.py` is
  frozen dataclasses with bounded string helpers (`_str`, `redact_text`) and a
  canonical `_hash_body`. S1 follows it.
- **Fixture precedent.** `tests/fixtures/<area>/` directories (for example
  `tests/fixtures/sdd/`) are read by table tests. `pyproject.toml` sets
  `testpaths = ["tests"]`.

Deployed state checked:

- `$MCTL_GITOPS_ROOT/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
  - env `IMPLEMENTER_BUDGET_USD: "20.00"`. A comment records the raises
    3.00 -> 10.00 -> 20.00;
  - env `IMPLEMENTER_TIMEOUT_SECONDS: "5400"`;
  - `activeDeadlineSeconds` 7200 is noted as the outer net;
  - no `IMPLEMENTER_TIMEOUT_CEILING_SECONDS` override was found.

  So the effective budget is $20 and the timeout is 5400 s, not the manifest
  defaults. This matches mctl-agents#1025's statement.
- `$MCTL_GITOPS_ROOT/services/admins/mctl-agents-worker-implement/values.yaml`
  sets image tag `1.117.0` and `--role implementation`. That worker submits the
  Argo CWFT and waits, so the CWFT env above is what the implementer pod sees.
- `gh issue view 1025`: #1021's implementer run (`mctl-agents-implement-ca0f0420`)
  quoted a prompt fixing the subject to `feat(agents): <slug>` with a
  `Co-Authored-By` ending. That differs from the clone HEAD prompt text, and
  which one image `1.117.0` contains was not verified. The commit contract is
  therefore treated as unverified (see Open questions in requirements.md).
- The mctl MCP tools were not called. No live pod env was observed. The values
  above are declared gitops config, not observed runtime state.

## Proposed solution

S1 adds pure modules, offline tools, fixtures and tests. It modifies no
existing module.

### 1. `orchestrator/feasibility_tasks.py`: the task parser

`parse_tasks(text: str) -> TaskGraph` is line-based and deterministic.

- **Sections.** A `## ` heading starts a section. `Tests`, `Rollback` and
  `Release blockers*` (case-insensitive, prefix match) are non-task sections.
  Any other heading, or none, is a task section. Unknown headings are recorded
  in `graph.sections`.
- **Task head.** `^- \[[ xX]\] (?P<id>\d+[a-z]?)\.\s+(?P<body>.*)$` at column 0
  in a task section. The task block is the head plus every following line that
  is indented or blank, up to the next head, heading or column-0 non-task
  line.
- **Unknown checklist lines.** A column-0 `- [ ]` line in a task section that
  does not match the head pattern, such as `- [ ] Step two` or `- [ ] 3)`, is
  `unknown-task-syntax`. It drives `tasks-unparseable` when no task parses, and
  `dependency-syntax-ambiguous` otherwise.
- **Dependency clause.** The block is joined with single spaces, then matched
  with `\(depends\s+on\s+(?P<spec>[^)]*)\)` (case-insensitive). This covers the
  next-line clause (#997), the clause wrapped inside the parenthesis (#911)
  and inline clauses. The spec grammar:
  - items separated by `,` or `and`;
  - an item is an id (`\d+[a-z]?`) or a range `\d+-\d+`;
  - a range expands to every declared id whose numeric prefix lies in the
    range, so `4-11` includes `4b` and `5a`. This is recorded as
    `range-expanded` evidence.

  Any other token in the spec makes the clause ambiguous, for example
  `(depends on 3 and 4b) - names` is fine but `(depends on the M1 PR)` is not.
  A bare `depends on` outside parentheses is also ambiguous.
- **Annotations.** Optional explicit tags `[repo: X]`, `[base: R]`, `[spike]`
  and `[gate: approval|merge|release|deploy]`. An unknown tag value is an
  advisory. Explicit tags win over heuristics.
- **Graph checks.** Duplicate ids, missing targets, and cycles found by an
  iterative DFS in sorted-id order. Topological layers use Kahn's algorithm
  with lexicographic tie-break, so the result is deterministic.

### 2. `orchestrator/feasibility_profile.py`: the runner profile

- `Capability(value, source)` where `source` is `deployed`, `default-only` or
  `unknown`. `verified` is `source == "deployed"`.
- `RunnerProfile` (frozen) has these capabilities:
  - `write_repos` (target only), `base_ref` (`default-branch`) and
    `attempts` (1). These are `deployed`, because they are structural facts of
    `run_implementer.py` pinned by S1 constants and tests;
  - `budget_usd`, `timeout_s`;
  - `commit_contract`, with fields `subject_types`, `max_commits` and
    `ordered_typed_commits`.

  `profile_id` is `implementer/single-repo-v1`. `digest()` is the sha256 of the
  canonical JSON of values and sources.
- **Derivation (pure, from data).**
  `derive_profile(manifest: Mapping, option_defaults: Mapping, deployed: Mapping | None)`
  applies the precedence deployed value, then default-only, then unknown.
- **Loader (the only I/O, outside `evaluate`).** `load_deployed_snapshot(path)`
  reads a small JSON snapshot. It holds `IMPLEMENTER_BUDGET_USD`,
  `IMPLEMENTER_TIMEOUT_SECONDS`, an optional `commit_contract`, and provenance
  (`source_path`, `gitops_commit`). The offline tool can produce it from a CWFT
  file with `--from-cwft PATH`, by extracting the named env entries from YAML.
  An unreadable input is an error, never a defaulted profile.
- **Committed snapshot.** `tests/fixtures/feasibility/profiles/deployed-2026-11.json`
  pins 20.00 / 5400 with provenance. `default-only.json` has no deployed
  snapshot. `commit-verified-single-type.json` sets
  `ordered_typed_commits: false`.

### 3. `orchestrator/feasibility.py`: the evaluator and record

- **Constants.** `API_VERSION = "feasibility.mctl.ai/v1alpha1"`,
  `KIND = "ProposalFeasibility"`, `EVALUATOR_VERSION = "s1.0.0"` (bumped on any
  rule, lexicon or threshold change), `VERDICTS`, `REASON_CODES` (a frozen dict
  from code to class), and the bounds `MAX_REASONS = 32`,
  `MAX_EVIDENCE_PER_REASON = 4`, `MAX_EVIDENCE_CHARS = 160`, `MAX_SLICES = 16`.
  Thresholds: `MAX_TASKS_ONE_ATTEMPT = 8`, `MAX_COMPONENTS = 4`.
- **Entry point.** `evaluate(files: Mapping[str, bytes | None], target_repo: str, profile: RunnerProfile) -> ProposalFeasibility`.
  Rules run in a fixed order and each appends reasons:

  | # | Rule | Reason code | Class |
  | --- | --- | --- | --- |
  | 1 | Parse | `tasks-unparseable` | uncertain |
  | 1 | Parse | `dependency-syntax-ambiguous` | uncertain |
  | 1 | Parse | `dependency-target-missing` | uncertain |
  | 1 | Parse | `task-graph-cyclic` | blocked_dependency |
  | 1 | Parse | `task-id-duplicate` | blocked_dependency |
  | 2 | Repository | `cross-repo-write` | needs_split |
  | 2 | Repository | `cross-repo-prerequisite` | blocked_dependency |
  | 3 | Base | `foreign-branch-base` | blocked_dependency |
  | 4 | Spike | `spike-gates-downstream` | needs_split |
  | 5 | Gates | `inter-step-gate` | needs_split |
  | 6 | Replay | `replay-sensitive-without-fixture` | uncertain |
  | 7 | Commit contract | `commit-contract-incompatible` | blocked_dependency |
  | 7 | Commit contract | `commit-contract-unverified` | uncertain |
  | 8 | Scope | `scope-over-broad` | needs_split |
  | 9 | Capability | `runner-capability-unknown` | uncertain |

  How the rules detect their conditions:
  - **Repository (2).** A task is a foreign write if it has an explicit
    `[repo: X != target]` tag, or if it pairs a write verb (`add|edit|update|change|create|remove|set|open a PR`)
    with a foreign-owned reference. Foreign-owned references are
    `mctlhq/<repo>` with repo != target, `platform-gitops/`,
    `services/<tenant>/`, `argo-workflows/` or `cluster-templates/`, using a
    fixed `REPO_PATH_OWNERS` table. A mere mention without a write verb is
    `cross-repo-reference`, an info reason with no class.
  - **Base (3).** `on top of #N`, `stack(ed)? on`, `based on (PR|draft|branch)`,
    `[base: R]`, or a `feat/...` branch that is not `feat/agents-<slug>`.
  - **Spike (4).** An explicit `[spike]` tag, or a task head containing the
    word `spike`, that has at least one dependent.
  - **Gates (5).** The lexicon is `after (merge|release|deploy|approval)`,
    `must be merged`, `merged and (live|deployed)`, `once .* is (deployed|released)`
    and `wait for (approval|review)`, or an explicit `[gate: K]` tag. It fires
    only when the task is not the last layer, or has dependents.
  - **Replay (6).** It fires when `workflow.patched`, `_PATCH\b` or
    `orchestrator/temporal/workflows/` appears in design or tasks, and no task
    block mentions `replay`, `histories/` or `record_workflow_history`.
  - **Commit contract (7).** Proposal demands come from a lexicon:
    `separate .*test:.* commit`, `red before`, `` `test:` commit ``,
    `\d+ commits`, `commit (subject|message) must`. Each demand is checked
    against `profile.commit_contract`. A verified contract that does not
    support the demand gives `incompatible`. An unverified contract gives
    `unverified`. No demand means the rule is silent.
  - **Scope (8).** Task count above `MAX_TASKS_ONE_ATTEMPT`, or distinct
    top-level components above `MAX_COMPONENTS`. A component is the first two
    path segments of every backticked path in task blocks.
  - **Capability (9).** Emitted when any rule that would otherwise let the
    verdict be `feasible` relies on a capability that is not `verified`.
    Budget and timeout always qualify, because a `feasible` claim asserts that
    the work fits one attempt.
- **Verdict.** The lattice is `blocked_dependency > needs_split > uncertain > feasible`.
- **Slices.** Topological layers are cut at spike, gate and foreign-repo
  boundaries and at every `MAX_TASKS_ONE_ATTEMPT` tasks. Consecutive tasks
  with the same repo are grouped into `{index, repo, task_ids, cut_reason}`. A
  cyclic graph yields no slices. The slices are suggestions only.
- **Record.** Frozen dataclass with a canonical `to_json()` (sorted keys,
  `separators=(",", ":")`, no timestamps). `content_hash` is computed over the
  body. `parse_summary` holds the task ids, edges, sections and unknown lines.
  `is_current(record, files, profile)` compares `content_digest`,
  `runner_profile_digest` and `evaluator_version`.
- **Evidence.** Evidence strings are `task <id>: <matched token>`, truncated to
  `MAX_EVIDENCE_CHARS`. File contents are never echoed beyond the matched
  token.
- **Purity.** The module imports only stdlib (`re`, `json`, `hashlib`,
  `dataclasses`), the two modules above, and `orchestrator.proposal_state` for
  `content_digest_of`. It never reads `os.environ`. A test enforces the import
  allowlist via AST.

### 4. Offline tools (stdout only)

- `tools/evaluate_feasibility.py PROPOSAL_DIR --target REPO [--profile JSON | --from-cwft PATH]`
  reads the four files and prints the record JSON, or `--markdown`. It writes
  nothing.
- `tools/feasibility_corpus_report.py [--runs N]` evaluates every fixture under
  `tests/fixtures/feasibility/` against its declared profile and prints:
  - the fixture table: verdict, reason codes, `human_label` and FP/FN class
    (an FP is evaluator `feasible` where the label is not feasible; an FN is
    evaluator hard-blocked where the label is feasible);
  - limitations;
  - the median and p95 evaluation time over N runs, and the input bytes.

  The S1 PR description pastes this output.

### 5. Fixtures: `tests/fixtures/feasibility/<name>/`

Each fixture directory holds the digest files, `meta.json`
(`target_repo`, `profile`, `human_label`, `asserts`) and `SOURCE.md`
(verbatim/shaped, source path, gitops commit).

| Fixture | Source | Exercises |
| --- | --- | --- |
| `issue-993` | verbatim, mctl-agents agents-state | `4b`, `and`, ranges, spike task 10, "merged and live" gate, replay |
| `issue-996` | verbatim | `(depends on 0)`, `0-4`, `3b` |
| `issue-1021` | verbatim | `5a`, `## Implementation`, `T-n` references |
| `issue-997-self` | verbatim | next-line clauses, 8 tasks, replay-sensitive work with a fixture task |
| `issue-911-cross-repo` | verbatim if readable, else shaped | wrapped `(depends` / `on 4)`, post-merge gate, target `mctl-gitops` |
| `issue-414-oversized` | verbatim | dense tasks, scope |
| `issue-1025-commit-contract` | shaped from #1025's text | `test:`-before-`feat:` demand, run under verified and unverified profiles |
| `small-single-repo` | synthetic | 2 tasks, `deployed` profile |

Synthetic mutation fixtures:

- `multiline-depends`: the only edge `3 -> 1` is on the following line;
- `cycle`, `missing-target`, `duplicate-id`, `unknown-task-syntax`,
  `ambiguous-depends`;
- `foreign-base`, `cross-repo-prerequisite`;
- `gate-deploy`, `spike-gated`, `replay-without-fixture`;
- `tasks-missing`.

### Why this shape

- Splitting the parser and the profile from the evaluator keeps each module
  testable and lets S2/S3 import `evaluate` unchanged.
- The heuristic lexicons are versioned constants, so a false positive is fixed
  by a reviewed lexicon change plus an `EVALUATOR_VERSION` bump, never at
  runtime.
- No `feasibility.json` is written and no digest file changes, so S1 cannot
  affect any approval.

## Alternatives

- **Implement #997 as proposed in one attempt.** Dropped. That is the
  oversized, replay-sensitive change S1 exists to avoid, and it would put an
  unmeasured heuristic into the approval path.
- **Require explicit tags only (`[repo:]`, `[spike]`, `[gate:]`) and ignore
  prose.** Dropped as the sole mechanism. No existing proposal uses the tags,
  so the corpus would all come out `feasible` or `uncertain` and teach nothing.
  Tags are kept as the authoritative override, with heuristics as fallback.
- **Model-based (LLM) judgement.** Dropped. It is non-deterministic, costs
  model budget, and cannot produce byte-identical verdicts or
  mutation-discriminating tests. The issue excludes model runs.
- **Read the runner profile live from the environment inside `evaluate`.**
  Dropped. That is I/O in evaluation, the result would differ per host, and an
  unset env would silently yield the manifest default. That is exactly the
  `budgetUsd: 3` mistake from #1025.

## Platform impact

- **Migrations and compatibility.** None. S1 adds new modules, tools, fixtures,
  tests and one doc. No existing import or call site changes. The digest,
  `.status.yaml` and the approval intent are untouched.
- **Runtime.** No worker or CWFT change, and no deploy is needed. Nothing calls
  the evaluator in production.
- **Resources.** The CI suite gains about 25 fast tests. Expected evaluation
  time is well under 50 ms per fixture, measured by the corpus report.
- **Risks and mitigations.**
  - *Heuristic false positives* (for example "add" near a gitops path in a
    Rollback note). Mitigation: non-task sections are excluded, the corpus
    reports FP/FN, and the thresholds and lexicons are documented as
    uncalibrated.
  - *Fixture staleness.* The source proposals may be amended later.
    Mitigation: `SOURCE.md` pins the gitops commit, and fixtures are
    snapshots, not live reads.
  - *Profile snapshot drift.* The deployed budget may change again.
    Mitigation: the snapshot carries provenance, and a changed snapshot
    invalidates every record via `runner_profile_digest`.
  - *Reading tests as approval.* Docs and the report state that a verdict is
    advisory and S1 has no consumer.
