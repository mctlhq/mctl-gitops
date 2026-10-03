# Design: incident-89786722

## Diagnosis
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`
declares a single `spec.activeDeadlineSeconds: 7200` at the WORKFLOW level
(line 59), even though the template's own comment describes it as a
per-attempt "hard 2h safety ceiling." Argo applies `spec.activeDeadlineSeconds`
to the workflow's total wall-clock runtime, not per step, so the
`implement-fallback` retry, `commit-and-push`, and `assert-attempt` steps all
share the SAME 7200s budget as the primary `implement` step. In this
incident's workflow, the primary `implement` step ran for the full ~7200s and
was killed for exceeding the deadline ("Step exceeded its deadline"). Argo
still started `implement-fallback` and `commit-and-push` afterward, but with
no real time budget left, and both failed the same way. `commit-and-push`
normally finishes in well under a minute; it failed here purely because the
shared deadline had already elapsed, not because of any problem in the
commit logic itself. Net effect: the proposal's `.status.yaml` update is
never pushed to `main`, so the run reports Failed and generates this
incident even when the underlying SDK work may have substantially succeeded.

## Proposed Fix
In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`:
1. Add `activeDeadlineSeconds: 7200` to the `run-implementer` template itself
   (currently starting at line 238), so the 2h ceiling bounds ONE implementer
   attempt (primary or fallback) instead of the whole workflow.
2. Raise the workflow-level `spec.activeDeadlineSeconds` (line 59) from
   `7200` to `16200` (4.5h) — enough for a primary attempt (7200s) + a
   fallback attempt (7200s) + commit-and-push with its existing retries
   (~600s budget) + assert-attempt (~60s) + margin — so `commit-and-push`
   always has real time to run regardless of how long the implementer
   attempts took.

## Scope
Minimal. Only the two `activeDeadlineSeconds` values in
`cwft-mctl-agents-implement.yaml` change — no changes to run_implementer.py,
retry policy, mutex behavior, or other templates.

## Confidence: MEDIUM
The shared-deadline mechanism is directly confirmed by Argo's own failure
messages ("Step exceeded its deadline") cross-referenced with the literal
`activeDeadlineSeconds: 7200` field in the CWFT source, and the same pattern
repeats across multiple independent incidents from this template (see
incident-89786271, incident-89786272, incident-89786602, incident-89786744
for corroborating traces). The exact reason `implement-fallback` itself also
consistently ran to a further ~1200s before being killed (rather than
failing immediately) was not independently root-caused here and may warrant
implementer follow-up.
