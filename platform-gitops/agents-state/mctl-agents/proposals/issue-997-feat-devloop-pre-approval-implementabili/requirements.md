# DevLoop pre-approval implementability and safe-slicing feasibility preflight

## Context

Today the DevLoop asks a human to approve a proposal (an `aar_` grant bound to
the proposal content digest, `orchestrator/temporal/activities/delegated_approval.py`
`request_devloop_approval`) without first checking whether the Tier 2
implementer can actually build it. The implementer works on exactly one
repository (`mctlhq/<service>`, cloned at its default branch by
`run_implementer._clone_target`) within one budget/timeout envelope
(`agents/_manifests/implementer/agent.yaml`: `budgetUsd: 3.00`,
`timeoutSeconds: 900`). A proposal that needs a mctl-gitops companion write, a
spike whose answer gates later tasks, a merge/deploy between steps, or
stacking on someone else's draft PR cannot be done in one attempt. The
implementer then refuses after approval (mctl-agents#993 ->
`mctl-agents-implement-178e8b3d`, no commits, no PR). By then the owner has
spent an approval on a plan that could not run.

This proposal adds a bounded, read-only, deterministic **feasibility
preflight**. It evaluates the exact digested proposal bytes against the
implementer's declared runner profile and returns a typed verdict:
`feasible`, `needs_split`, `blocked_dependency` or `uncertain`. The verdict
carries blocking task ids, evidence, and proposed slices in dependency order,
and is bound to the content digest and the runner profile. It is published
with the proposal, shown on the issue before the approval decision and, in
`enforce` mode, keeps a hard-blocked proposal out of the ordinary
approve->implement path until the proposal is amended. This proposal is the
smallest observable slice. Automatic issue creation, slice scheduling,
refusal-marker semantics (#414) and cross-work-item coordination (#994) are
out of scope.

## User stories

- AS a proposal owner I WANT to see, before I approve, whether the proposed
  tasks can be built by the implementer in one single-repository attempt
  SO THAT I do not spend an approval on a plan that will be refused.
- AS a proposal owner I WANT a hard-blocked proposal to come back with
  concrete blocking task ids and a suggested ordered split SO THAT I can
  amend it or open separate work items.
- AS a platform operator I WANT the preflight to be deterministic, digest-bound
  and side-effect free SO THAT re-running it never creates issues, PRs,
  executions or grants, and a changed proposal never inherits an old verdict.
- AS a platform operator I WANT an `observe` rollout mode SO THAT I can measure
  false positives and false negatives before the gate holds any proposal.
- AS the issue-investigator I WANT a documented task-annotation convention
  (repo, spike, gate, base) SO THAT the facts the gate depends on are declared
  in the digested content rather than guessed from prose.

## Acceptance criteria (EARS)

Evaluator (pure function, `orchestrator/feasibility.py`)

- WHEN the evaluator is given the four `PROPOSAL_DIGEST_FILES` byte contents, the
  target service and a runner profile THE SYSTEM SHALL return a
  `ProposalFeasibility` record with `verdict` in {`feasible`, `needs_split`,
  `blocked_dependency`, `uncertain`}, `content_digest` equal to
  `proposal_state.content_digest_of(files)`, the runner profile id and digest,
  the evaluator version, `blockers[]`, `advisories[]`, `slices[]` and a
  `content_hash` over the record.
- WHEN the evaluator is called twice with identical inputs THE SYSTEM SHALL
  return byte-identical serialized records (no timestamps or randomness in
  the hashed fields).
- IF any task declares `[repo: X]` where X is not the target service, AND a
  target-repository task depends on it (directly or transitively) THEN THE
  SYSTEM SHALL return `blocked_dependency` with reason
  `cross-repo-prerequisite` naming both task ids.
- IF any task declares `[repo: X]` where X is not the target service and no
  target-repository task depends on it THEN THE SYSTEM SHALL return
  `needs_split` with reason `cross-repo-write` and propose a separate slice
  for the foreign-repository tasks.
- IF a task tagged `[spike]` has dependents THEN THE SYSTEM SHALL return
  `needs_split` with reason `spike-gates-downstream`, placing the spike (and its
  own prerequisites) in the first proposed slice.
- IF a task carries `[gate: merge|release|deploy|approval]`, meaning that gate
  must be satisfied between it and its dependents, THEN THE SYSTEM SHALL
  return `needs_split` with reason `inter-step-gate` and cut the slices at
  that gate.
- IF any task declares `[base: ...]` other than the runner profile's base
  branch (for example an open draft PR's branch) THEN THE SYSTEM SHALL
  return `blocked_dependency` with reason `foreign-branch-base`.
- IF a task's `depends on` names a task id that does not exist, or the
  dependency graph has a cycle, THEN THE SYSTEM SHALL return
  `blocked_dependency` with reason `task-graph-unresolvable`.
- IF `tasks.md` is absent, or contains no task line the evaluator can parse,
  THEN THE SYSTEM SHALL return `uncertain` with reason `tasks-unparseable` and
  never `feasible`.
- IF no hard blocker exists but an advisory signal is present (an untagged
  reference to another mctlhq repository or to `platform-gitops/`, an untagged
  "draft PR" / "on top of #N" phrase, an untagged "spike"/"investigate first"
  phrase, replay-sensitive Temporal workflow changes with no task that adds a
  replay history fixture, or a combination of more than 12 tasks spanning 3 or
  more top-level source components) THEN THE SYSTEM SHALL return `uncertain` and
  list each signal as an advisory. An advisory signal is never a hard blocker on
  its own, and no lines-of-code or token threshold is a gate.
- WHEN no blocker and no advisory exists THE SYSTEM SHALL return `feasible`
  with exactly one proposed slice containing every task.
- WHILE producing evidence THE SYSTEM SHALL bound it (at most 32 blockers, 32
  advisories and 16 slices; each detail at most 256 characters), and quote only
  task ids, tag values, repository names and issue/PR refs, never file
  contents.

Investigator publication

- WHEN the investigator has staged a valid triplet THE SYSTEM SHALL compute the
  feasibility record from the staged digest files and write it to
  `feasibility.json` in staging, overwriting any agent-written or
  carried-forward file of that name, before the directory swap.
- THE SYSTEM SHALL NOT add `feasibility.json` to `PROPOSAL_DIGEST_FILES`. The
  record is derived from the digest and is not part of it.
- WHEN the investigator posts the proposal comment (`post_proposal_comment`)
  THE SYSTEM SHALL include a bounded feasibility section: verdict, content
  digest, blocking task ids with reasons, advisories, and proposed slices.
  For `uncertain`, the section SHALL say the result is uncertain, not that
  the proposal is rejected.
- IF computing the feasibility record raises THEN THE SYSTEM SHALL publish
  the proposal without `feasibility.json` and say in the comment that
  feasibility could not be determined. It SHALL NOT write a `feasible` record.
- THE SYSTEM SHALL extend the investigator prompt (`_build_prompt`) with the
  task-annotation convention (`[repo: <name>]`, `[spike]`,
  `[gate: <kind>]`, `[base: <ref>]`) and the instruction to slice work that
  the single-repository implementer cannot do in one attempt.

DevLoop integration (`orchestrator/temporal/workflows/dev_loop.py`)

- WHEN a canonical-approval DevLoop is about to request an approval grant,
  and the new `workflow.patched(FEASIBILITY_PREFLIGHT_PATCH)` marker is set,
  THE SYSTEM SHALL first run the `evaluate_proposal_feasibility` activity.
  The activity reads the proposal files at one gitops commit, the same way
  `read_proposal_content_digest` does, and evaluates them.
- WHEN the activity returns a verdict for a digest that this loop has not yet
  reported THE SYSTEM SHALL post one issue comment for that digest. The comment
  carries a hidden marker `<!-- mctl-feasibility:<digest> -->`, and the activity
  SHALL NOT post if a comment with that marker already exists.
- WHEN the approval grant is requested after a preflight THE SYSTEM SHALL pass
  the evaluated digest as `ApprovalRequestInput.expected_content_digest`.
- IF the proposal digest the request activity reads differs from that
  expected digest THEN THE SYSTEM SHALL create no grant, return
  `ok=False, reason="content-moved"`, and have the workflow re-run the
  preflight. The number of re-runs SHALL be bounded.
- WHILE the activity reports mode `observe` (the default) THE SYSTEM SHALL
  request the approval grant exactly as it does today, whatever the verdict.
- IF the mode is `enforce` and the verdict is `needs_split` or
  `blocked_dependency` THEN THE SYSTEM SHALL NOT request an approval grant.
  It SHALL enter a bounded feasibility hold that re-evaluates every
  `GRANT_FRESHNESS_INTERVAL`, observes `abandon` and the source issue
  closing, and ends at `CANONICAL_APPROVAL_WAIT` with
  `ended="feasibility hold expired: <verdict>"`.
- WHEN a re-evaluation during the hold returns `feasible` or `uncertain` THE
  SYSTEM SHALL leave the hold and request the approval grant for the new
  digest.
- WHEN the proposal digest changes while a grant is parked (the existing
  grant-freshness supersede path) THE SYSTEM SHALL re-run the preflight
  before requesting the fresh grant. A verdict bound to an earlier digest
  SHALL never be reused.
- WHILE running the preflight or the hold THE SYSTEM SHALL NOT write
  `.status.yaml`, create or decide an approval grant, open issues or PRs,
  create executions, merge or deploy.
- WHERE a history was recorded before `FEASIBILITY_PREFLIGHT_PATCH` existed THE
  SYSTEM SHALL replay it unchanged.

## Out of scope

- Changing the mctl-api approval card or approval intent. The intent hash
  (`approval_intent`) is unchanged. Showing the feasibility record inside the
  mctl-api card is a separate mctl-api change (see Open questions).
- Automatic issue/work-item creation, slice scheduling or a dependency
  coordinator (#994). Proposed slices are text only.
- Persisting or interpreting implementer `refused-scope` markers (#414). This
  slice only defines an optional `prior_refusal` input on the evaluator. The
  DevLoop passes `None`, and #414 wires it.
- Cross-repo input fetching before implementation (#911), the implementation
  completion contract and inner loop (#428/#429), and failed-implement
  recovery (#300).
- Any change to the accepted #993 proposal, to draft PR #992, or to
  `.status.yaml` semantics.
- Model-based (LLM) feasibility judgement. This slice is deterministic only.

## Open questions

- Should the feasibility record also appear in the mctl-api approval card
  (mctlhq/mctl-api#931)? That needs an mctl-api read of `feasibility.json`
  or a new non-hashed field on the approval request. This proposal assumes
  the GitHub issue comment is the pre-decision surface for now.
- Is a human override of an `enforce`-mode hold needed beyond amending the
  proposal or switching the mode to `observe`? This proposal assumes no
  override: the remedies are amending the proposal or abandoning the loop.
- Thresholds for the advisory "broad multi-component" signal (more than 12
  tasks and 3 or more top-level components) are initial values, to be
  re-tuned from the fixture false-positive/false-negative report.
- The runner profile is read from the implementer manifest and the
  `IMPLEMENTER_BUDGET_USD` / `IMPLEMENTER_TIMEOUT_SECONDS` settings visible to
  the DevLoop control worker. The deployed implement CWFT may override these.
  If the worker cannot observe the values, the profile records them as
  `unknown` and no rule treats them as a capability.
