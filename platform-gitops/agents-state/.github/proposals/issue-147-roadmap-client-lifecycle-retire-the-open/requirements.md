# Retire the OpenClaw-only identity branch from the client-lifecycle epic manifest

## Context

`roadmap/epics/client-lifecycle.yaml` is the authored desired state for epic
`mctlhq/.github#22`. It still carries an `identity` phase with two work items:
`lookup-deployment` (bound to `mctlhq/mctl-gitops#1182`) and
`operator-identity-lookup` (bound to `mctlhq/mctl-telegram#400`). The
owner-approved roadmap cleanup in `mctlhq/.github#141` decided that this branch
is retired: the mctl-telegram half of #400 is already delivered (#511 added the
`admin:users` lookup tier, #575 documented it), and the remaining deployment
half is being dropped rather than sequenced, so neither item should continue to
be authored as required epic work. The explanatory comment block above the two
items exists only to justify that modelling, so it goes with them, and the
`identity` phase is then empty.

This is step 2 of 2 of the Client Lifecycle part of accepted proposal
`platform-gitops/agents-state/.github/proposals/issue-141-roadmap-pause-communication-agent-and-re/`
("Reconciliation and sequencing"). Step 1 landed as #146 (`26846e6`): it dropped
`operator-identity-lookup` from `onboarding-integration.dependsOn`, and its
governed apply landed on 2026-09-30 (`RemoveDependency` `f955af581e0687da`,
`applied: 1`), so `mctl-telegram#679` is now blocked only by #439 and #440. With
that edge already removed from the live graph, `plan.assert_authored()`
(`roadmap/scripts/plan.py:212`, called from `roadmap/scripts/apply.py:317`) no
longer refuses this step: removing the two bindings can no longer orphan an
authored dependency endpoint. The change matters because the manifest is the
single source of truth the publication pipeline, readiness evaluator and wave
launcher all read; leaving retired work authored as `required: true` keeps
`allRequired` completion permanently unreachable and keeps a dead phase in every
derived artifact.

## User stories

- AS the roadmap owner I WANT the retired OpenClaw-only identity branch removed
  from the `client-lifecycle` manifest SO THAT the authored desired state matches
  the owner-approved decision in #141 and `allRequired` completion is reachable.
- AS an operator planning a wave I WANT `ready.py` and `health.py` to stop
  counting `#1182` and `#400` as required client-lifecycle work SO THAT the
  published `RoadmapReadySet` and `RoadmapHealth` describe only work that is
  still intended.
- AS a reviewer of a governed apply I WANT this manifest change to authorize zero
  GitHub writes SO THAT retiring authored intent never silently mutates the live
  issue graph.

## Acceptance criteria (EARS)

- WHEN the pull request is opened THE SYSTEM SHALL contain exactly one changed
  file, `roadmap/epics/client-lifecycle.yaml`.
- WHEN the diff of `roadmap/epics/client-lifecycle.yaml` is inspected THE SYSTEM
  SHALL show only these removals: the `lookup-deployment` work item, the
  `operator-identity-lookup` work item, the multi-line comment block immediately
  above them (currently lines 31-35), and the `- id: identity` /
  `title: Operator identity lookup` phase entry.
- WHILE the change is in review THE SYSTEM SHALL keep
  `client-reachability-preferences`, `login-bot-update-receiver`,
  `safe-broadcast`, `product-update-feed` and `onboarding-integration`
  byte-identical, including every `dependsOn` list, and SHALL keep
  `metadata`, `spec.title`, `spec.goal`, `spec.lifecycle`, `spec.github`,
  `spec.completion` and `spec.successCriteria` byte-identical.
- WHEN `python3 roadmap/scripts/validate.py roadmap/epics` runs on the branch THE
  SYSTEM SHALL exit `0` and report `PASS roadmap/epics/client-lifecycle.yaml`.
- WHEN `python3 -m unittest discover -s roadmap/tests -p 'test_*.py'` runs on the
  branch THE SYSTEM SHALL report `OK` with no test file modified.
- WHEN `plan.py` is run for `roadmap/epics/client-lifecycle.yaml` against an
  observed graph in which #1182 and #400 are still sub-issues of #22 THE SYSTEM
  SHALL emit a `RoadmapApplyPlan` with zero `operations` and exactly two
  `HierarchyUnexpectedChild` notes, one per retired issue, and SHALL exit `0`.
- WHILE #1182 and #400 remain sub-issues of #22 THE SYSTEM SHALL treat those two
  notes as informational and SHALL NOT report the epic as `drift` in
  `health.py`.
- IF a reviewer expects the retired issues to be closed or detached by this
  change THEN THE SYSTEM SHALL leave them untouched, because `plan.py` never
  emits an operation that removes a child the manifest does not own
  (`roadmap/README.md`, "Diff entry to operation").
- WHEN the pull request body is written THE SYSTEM SHALL use `Refs
  mctlhq/.github#141` and SHALL NOT use any closing keyword for #141, #22, #400
  or #1182; it MAY use a closing keyword for #147 only.
- WHEN the change merges to `main` THE SYSTEM SHALL let
  `.github/workflows/roadmap-publish.yml` refresh `roadmap-state` from the push
  event, with no manual `publication_request.py` dispatch required.

## Out of scope

- Closing `mctlhq/mctl-gitops#1182` or `mctlhq/mctl-telegram#400` as not
  planned, and detaching either from #22. Both are operator actions after this
  merges; the roadmap write boundary deliberately cannot perform them.
- Any other issue-state change, including `mctlhq/mctl-telegram#440`.
- Any change to another manifest under `roadmap/epics/`, to Communication Agent
  work, or to `roadmap/scripts/`, `roadmap/schemas/`, `roadmap/tests/` or
  `roadmap/fixtures/`.
- Editing `spec.successCriteria`, including the line "Operator-facing identity
  lookup is scoped, auditable and privacy-safe." The issue scopes the diff to the
  four removals above and says nothing else in the file changes; revisiting
  success criteria is a separate authoring decision.
- Running a governed `apply.py --execute` for this epic. The plan is empty, so
  there is nothing to apply.

## Open questions

- `spec.successCriteria` still contains "Operator-facing identity lookup is
  scoped, auditable and privacy-safe.", which described the phase being removed.
  The issue explicitly scopes the diff to the four removals and states nothing
  else in the file changes, so this proposal leaves the criterion in place and
  records the mismatch for the owner rather than widening the diff. Note that
  `#511`/`#575` did deliver the mctl-telegram half of that capability, so the
  criterion is not simply false.
- The issue says the PR "may close this issue" (#147). This proposal uses
  `Closes mctlhq/.github#147` plus `Refs mctlhq/.github#141`; if the owner
  prefers #147 be closed by hand, drop the closing keyword and the diff is
  unaffected.
