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
`timeoutSeconds: 900`, but the deployed `cwft-mctl-agents-implement.yaml`
overrides these to `20.00` / `5400`. A setting that cannot be verified must be
reported as unknown and must never back a `feasible` claim.

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
- WHEN a proposal requires a commit shape the profile's commit contract
  verifiably does not support THE SYSTEM SHALL emit
  `commit-contract-incompatible` (`blocked_dependency`). Examples are separate
  ordered `test:` then `feat:` commits, or more commits than allowed. IF the
  contract is not verified THEN THE SYSTEM SHALL emit
  `commit-contract-unverified` (`uncertain`).
- WHEN the task count or the distinct-component count exceeds the versioned
  thresholds THE SYSTEM SHALL emit `scope-over-broad` (`needs_split`).
- THE SYSTEM SHALL resolve the verdict by the fixed lattice
  `blocked_dependency > needs_split > uncertain > feasible`, and SHALL return
  `feasible` only when no reason of any of those classes is present.

Runner profile:

- WHEN a runner profile is derived from the implementer manifest, the
  `orchestrator/options.py` defaults and an optional effective-deployment
  snapshot THE SYSTEM SHALL record each capability's value and its source
  (`deployed`, `default-only` or `unknown`). Capabilities: write repos, base
  ref, attempts, budget USD, timeout seconds and commit contract. Only
  `deployed` SHALL count as `verified`.
- IF no effective-deployment snapshot is supplied THEN budget and timeout SHALL
  be `default-only` and SHALL NOT count as verified.

Corpus and evidence:

- THE SYSTEM SHALL ship a fixture corpus covering #993, #996, #1021,
  #997-self, #911 cross-repo, #414 oversized, a #1025 commit-contract mismatch
  and a small single-repo proposal, plus synthetic mutation fixtures.
- WHEN the corpus report tool runs THE SYSTEM SHALL print, to stdout only:
  - a table of verdict, reasons, human label and FP/FN class per fixture;
  - known limitations;
  - per-fixture evaluation time (median of N runs) and input size.
- THE #997-self fixture test SHALL assert the parsed task count, the exact
  edge set and the detected reason codes, and SHALL NOT assert a desired
  verdict.
- WHEN evaluation runs over the whole corpus with the approval client,
  subprocess, socket and file-open entry points patched to fail THE SYSTEM
  SHALL complete without calling any of them, and without writing any file or
  any `.status.yaml`.

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
- Commit contract truth. #1025 quotes a prompt fixing the subject to
  `feat(agents): <slug>`. `orchestrator/run_implementer.py` at the clone HEAD
  (`2ddcf96`) says `feat(agents): <slug>` "or fix:/chore: as appropriate" and
  "multiple small commits are also fine". So the deployed image (`1.117.0`) and
  HEAD may differ. S1 therefore marks the commit contract `unverified` unless
  the profile snapshot pins it from the deployed prompt. The #1025 fixture is
  evaluated against both a verified-incompatible profile and an unverified
  one.
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
