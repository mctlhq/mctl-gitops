# DevLoop #997 S1: deterministic offline implementability evaluator and failure fixtures

## Context

mctlhq/mctl-agents#997 proposes a pre-approval implementability preflight. Its
current proposal ships a pure evaluator together with investigator publication,
new Temporal activities, a workflow patch and hold, grant digest propagation and
replay fixtures, all in one Tier 2 attempt. That is the oversized,
replay-sensitive kind of proposal the feature is meant to catch. Issue #1032
splits off slice S1 only. S1 is a pure, read-only, offline evaluator, proven
against real MCTL-shaped proposal fixtures before anything touches the
investigator, the approval path, the Temporal workflow or a deployment.

The evaluator has to read the `tasks.md` convention proposals actually use, not
an idealised one. Proposals in agents-state wrap the parenthetical across lines
(`(depends` / `on 4)` in mctl-gitops issue-911), use suffixed ids (`5a`, `3b`),
ranges (`depends on 4-11`), conjunctions (`depends on 3 and 4b`), nested
sub-bullets and `## Tests` / `## Rollback` / `## Release blockers` sections.
The evaluator must also judge against what the implementer is actually
configured with. The manifest default is `budgetUsd: 3.00` /
`timeoutSeconds: 900`, while the checked-in GitOps CWFT declares `20.00` / `5400`. This is
**declarative configuration**, not runtime-observed evidence: the running
image/pod environment was not checked. Unknown effective capabilities must
not support a real-world `feasible` claim.

## User stories

- AS a DevLoop owner I WANT a deterministic verdict on whether a proposal fits
  one implementer attempt SO THAT I can decide on S2/S3 integration from
  measured behaviour on real proposals, not from the design's claims.
- AS a proposal reviewer I WANT bounded reason codes, evidence and suggested
  slices SO THAT I can amend an oversized or blocked proposal before spending
  an approval.
- AS a platform operator I WANT proof that evaluation has no side effects SO
  THAT running it can never create a grant, issue, PR or execution.

## Acceptance criteria (EARS)

Evaluation and verdicts:

- `feasible` means *no detected blocker under the supplied provenance-bound profile*, not a guarantee of implementation success. Synthetic fully specified profiles may exercise the `feasible` branch in fixtures, but their report SHALL say `synthetic_fixture`, not `runtime verified`.
- Source-code facts, GitOps-declared config and actual runtime-observed properties SHALL have different provenance. A GitOps snapshot SHALL never be relabelled as a live runtime observation.

- WHEN `evaluate(files, target_repo, profile)` is called with the bytes of
  `requirements.md`, `design.md`, `tasks.md` and `proposed-content.md` THE
  SYSTEM SHALL return a `ProposalFeasibility` record. The record carries:
  - exactly one verdict from `feasible | needs_split | blocked_dependency | uncertain`;
  - reason entries from a closed, versioned set of codes, each with a severity
    class, task ids and capped evidence;
  - bounded suggested slices;
  - `content_digest` equal to `proposal_state.content_digest_of(files)`;
  - `runner_profile_digest`, `runner_profile_id` and `evaluator_version`.
- WHEN the same files and the same profile are evaluated twice, in the same or
  different processes, THE SYSTEM SHALL produce byte-identical canonical JSON,
  with no timestamps, no host data and sorted keys.
- IF any byte of a digest file changes, or any field or source of the runner
  profile changes, THEN `is_current(record, files, profile)` SHALL return False.
- WHILE evaluating THE SYSTEM SHALL do no I/O: no filesystem, environment,
  network or subprocess access. It SHALL import nothing from `temporalio`,
  `orchestrator.action_approvals`, `orchestrator.policy_checkpoint` or any
  GitHub client.
- IF a reason that permits a positive claim depends on a runner capability
  whose status is not `verified` THEN THE SYSTEM SHALL NOT return `feasible`,
  and SHALL return `uncertain` with `runner-capability-unknown`, naming the
  capability.
- IF `tasks.md` is missing, has no parseable tasks, or contains a task-shaped
  line or dependency clause the grammar does not recognise THEN THE SYSTEM
  SHALL return at least `uncertain` (`tasks-unparseable` or
  `dependency-syntax-ambiguous`), never `feasible`.

Task parsing:

- WHEN a `(depends on ...)` clause is split across lines, whether on the line
  following the checklist item or wrapped inside the parenthesis, THE SYSTEM
  SHALL attribute it to the enclosing task and collect its edges.
- IF a dependency-looking clause or a malformed/wrapped task head is left
  outside a captured block, including an **unindented continuation**, THE
  SYSTEM SHALL emit `dependency-syntax-ambiguous` and SHALL NOT claim
  `feasible`. The tests SHALL include both detached/unindented clauses and
  malformed task heads as negative controls.
- WHEN a dependency clause uses `,`, `and`, numeric ranges `a-b` or suffixed
  ids (`4b`) THE SYSTEM SHALL expand it deterministically against the declared
  task ids.
- IF a dependency names an id that no task declares THEN THE SYSTEM SHALL emit
  `dependency-target-missing` (class `uncertain`).
- IF the dependency graph has a cycle or a duplicate task id THEN THE SYSTEM
  SHALL emit `task-graph-cyclic` or `task-id-duplicate` (class
  `blocked_dependency`).
- WHILE inside a `## Tests`, `## Rollback` or `## Release blockers` section THE
  SYSTEM SHALL NOT treat checklist items as implementation tasks or edges.

Rules:

- WHEN a task writes to a repository other than the target (an explicit
  `[repo: X]` tag, or a write verb on a path or repo owned by another
  repository) THE SYSTEM SHALL emit `cross-repo-write` (`needs_split`). WHEN a
  target-repository task transitively depends on such a task THE SYSTEM SHALL
  emit `cross-repo-prerequisite` (`blocked_dependency`).
- WHEN a task requires a base other than the target's default branch (a
  foreign draft PR or branch, `on top of #N`, `stack on`, `[base: ...]`) THE
  SYSTEM SHALL emit `foreign-branch-base` (`blocked_dependency`).
- WHEN a spike task has dependents THE SYSTEM SHALL emit
  `spike-gates-downstream` (`needs_split`).
- WHEN a task requires an approval, merge, release or deploy before a later
  task can start THE SYSTEM SHALL emit `inter-step-gate` (`needs_split`).
- WHEN a proposal changes replay-sensitive Temporal code (`workflow.patched`,
  `*_PATCH`, `orchestrator/temporal/workflows/`) and no task records or
  replays a history fixture THE SYSTEM SHALL emit
  `replay-sensitive-without-fixture` (`uncertain`).
- WHEN a proposal **explicitly** requires ordered/multiple commits or specific
  commit subjects that the verified runner **commit-shape** contract cannot
  support THE SYSTEM SHALL emit `commit-contract-incompatible`
  (`blocked_dependency`). If the actual commit contract is unverified,
  report `commit-contract-unverified` (`uncertain`).
- Requirements for red-before-code, green-after-code, reproducible test
  evidence or mutation testing SHALL be treated as **test-evidence**
  obligations, not a demand for separate `test:` and `feat:` commits.
  Per owner decision #1025, one implementation commit is acceptable with
  reproducible red/green evidence. The corpus SHALL prove that `red before`
  with one commit is **not** `commit-contract-incompatible`.
- WHEN the task count or the distinct-component count exceeds the versioned
  thresholds THE SYSTEM SHALL emit `scope-over-broad` (`needs_split`).
- THE SYSTEM SHALL resolve the verdict by the fixed lattice
  `blocked_dependency > needs_split > uncertain > feasible`, and SHALL return
  `feasible` only when no reason of any of those classes is present.

Runner profile:

- WHEN deriving a runner profile from source, manifest defaults, GitOps
  declarations and optional runtime observations THE SYSTEM SHALL bind
  each capability to its origin (`source_code`, `gitops_declared`,
  `runtime_observed`, `synthetic_fixture`, `unknown`), evidence ref and
  available revision identifiers (code/config SHA, image and observation).
- Capabilities include write-repository scope, base, attempts, budget,
  timeout, commit-shape contract and test-evidence contract. Source-code
  facts pinned to a SHA can prove a **static code property**, but cannot
  prove which code/image is executing. GitOps config cannot by itself prove
  a live effective pod environment.
- For runtime-sensitive properties, `verified` requires a runtime-bound
  observation. A real candidate with required runtime properties unresolved
  SHALL be `uncertain`, even if GitOps declares $20 / 5400 seconds.
- IF there is no live observation THEN `20.00` and `5400` from the CWFT
  SHALL retain `gitops_declared` origin; manifest-only values retain their
  default-only provenance. Never silently upgrade either to verified.
- A labelled synthetic fixture MAY produce a synthetic `feasible` result,
  but the result is not proof of production readiness. The runner profile
  digest SHALL bind all values and provenance/revision fields.

Corpus and evidence:

- THE SYSTEM SHALL ship a fixture corpus covering #993, #996, #1021,
  #997-self, #911 cross-repo, #414 oversized, a #1025 commit-contract mismatch
  and a small single-repo proposal, plus synthetic mutation fixtures.
- WHEN the corpus report tool runs THE SYSTEM SHALL print, to stdout only:
  - verdict, reasons, independently reviewed human label and evidence origin;
  - the complete 4×4 confusion matrix for `feasible`, `needs_split`,
    `blocked_dependency` and `uncertain`, including **critical false-feasible**
    counts for objectively blocked fixtures and reason/severity breakdown;
  - known limitations and per-fixture median runtime/input size.
- IF a verified impossible fixture is classified `feasible` THEN S1 acceptance
  SHALL report **STOP / no promotion to S2** until the cause is addressed.
  Ambiguous human ground truth must remain unverified and is not eligible
  to suppress this stop condition.
- THE #997-self fixture test SHALL assert the parsed task count, the exact
  edge set and the detected reason codes, and SHALL NOT assert a desired
  verdict.
- WHEN evaluation runs over the whole corpus with the approval client,
  subprocess, socket and file-open entry points patched to fail THE SYSTEM
  SHALL complete without calling any of them, and without writing any file or
  any `.status.yaml`.

## Pre-approval S1 implementer envelope

The proposal has seven task headings but comprises three modules, two CLI
tools, a substantial real/synthetic corpus, mutation tests and documentation.
GitOps declares a $20 / 5400-second limit, but the actual worker state and
commit contract remain unobserved. Before approval, the reviewer SHALL
document an explicit file/test breakdown and argue that this fits one
single-repository attempt **without assuming runtime capacity**. If that
cannot be substantiated, amend into independently approved **S1a**
(parser/profile/evaluator + critical tests) and **S1b** (expanded corpus,
tools, report and docs); neither slice inherits a previous digest or approval.

## Out of scope

- Investigator publication (`feasibility.json`, issue comment or prompt
  changes in `orchestrator/run_issue_investigator.py`). That is S2.
- New Temporal activities, `dev_loop.py` patches, holds, grant digest
  propagation, `DEVLOOP_FEASIBILITY_MODE` and replay fixtures. That is S3,
  gated by the B4 release hold.
- Any change to `.status.yaml`, approval intent fields,
  `PROPOSAL_DIGEST_FILES` or `content_digest_of`.
- Model runs, automatic issue creation, slot dispatch, production enforcement.
- Changes to #993, release controls, mctl-api, the bridge or mctl-gitops.
- Triggering an implementer, merge, release or deploy.

## Open questions

- Fixture sourcing. The implementer clones only `mctlhq/mctl-agents`. Proposals
  for mctl-gitops-service issues (#911) live in mctl-gitops agents-state, which
  may not be readable from the implementer run. The design copies verbatim
  where the source is readable and otherwise writes a reduced "shaped" fixture
  whose `SOURCE.md` says it is not verbatim and pins the source path and
  commit. A reviewer should check which fixtures are verbatim.
- Commit contract truth. #1025 quotes a fixed `feat(agents): <slug>` prompt,
  while source HEAD permits `fix:`/`chore:` and multiple small commits. The
  live image/prompt was not observed. The effective shape contract stays
  unverified without runtime evidence. In any case, #1025 explicitly permits
  a single implementation commit with reproducible red/green test evidence:
  those are separate contract dimensions, with separate fixtures.
- Severity of a missing dependency target. The issue groups "cycle/missing
  dependency" together. This proposal treats a cycle as a demonstrated
  impossibility (`blocked_dependency`) and a missing target as ambiguity
  (`uncertain`). The owner may prefer both to be hard.
- Scope thresholds (`MAX_TASKS_ONE_ATTEMPT = 8`, `MAX_COMPONENTS = 4`) are
  uncalibrated starting points. The corpus report exists to measure them, and
  they may change before S2.
- The human labels on the corpus are the investigator's reading of each
  proposal. The independent S1 review should confirm or correct them, because
  the FP/FN numbers depend on them.
