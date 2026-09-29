# Design: incident-90640590

## Diagnosis
This shepherd run's own work (proposal `issue-528-feat-context-platform-472-slice-c-produc`,
target service `mctl-agents`) succeeded: `run-shepherd` and `commit-and-push`
both completed and the transition was pushed to `mctl-gitops` main. The
workflow only failed at the final `post-deploy-verify` step, which by design
(see `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`,
step 4 doc comment) lists **every** ArgoCD Application that newly became
Degraded since the workflow started, regardless of whether that Application
is the one this run touched. That is intentional — it was added to close the
gap exposed by the 2026-05-01→05-07 external-secrets incident, where a
shepherd merge broke an unrelated downstream Application and nobody noticed
for six days.

The flagged Application, `argocd/labs-mctl-telegram`, has nothing to do with
`mctl-agents` or this run's proposal. It was already Degraded before this
workflow started (see sibling incident `18bc5134-18f5-4959-b594-6f2f2932eaa0`,
proposal `mctl-gitops/proposals/incident-2932eaa0`) and stayed Degraded
through this run's 300s+120s check window. This is a correct, working-as-
designed safety-net trip, not a bug in the shepherd or in proposal
`issue-528`'s own change — it is pure collateral noise from an unrelated,
already-tracked incident.

## Confidence: MEDIUM
The causal chain (this run's own change was unrelated and succeeded; the
flagged app was independently and already Degraded) is well supported by the
workflow logs and the sibling incident's evidence. What is not certain is
whether the platform maintainers consider today's noise level (every shepherd
tick failing/alerting for the full duration of an unrelated incident)
acceptable, or worth a targeted fix (e.g. de-duplicating against an already-open
`argocd_app_degraded` incident) — that judgment call is left to a human; no
behavior change is proposed here beyond documentation.

## Proposed Fix
No code or config behavior change — the check is working as designed and
should not be narrowed (narrowing it would reopen the exact external-secrets
gap it was built to close). Add a short clarifying note to the step's own
description in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
(the `post-deploy-verify` bullet under `workflows.argoproj.io/description`),
stating explicitly that a `workflow_failed` alert naming `post-deploy-verify
flagged: argocd/<app>` can be caused by an app unrelated to the run's own
target service, and that operators/incident-responders should check for an
existing `argocd_app_degraded` incident on that app before treating the
shepherd failure as a separate root cause.

## Scope
Minimal. Comment-only addition to the existing description block; no
behavioral change.
