# Design: incident-90640590

## Diagnosis
This is not a failure of the shepherd-managed PR (issue-528). The shepherd's
`post-deploy-verify` step correctly detected that the labs-mctl-telegram
ArgoCD Application was Degraded and stayed Degraded through its 120s grace
window, and failed the workflow as designed. The Degraded state itself
predates this workflow's own threshold timestamp (2026-09-28T23:53:27Z) and
is the same underlying condition tracked in sibling incident
18bc5134-18f5-4959-b594-6f2f2932eaa0 (ArgoCDApplicationDegraded, escalated
separately): the unconditional, non-hooked one-shot Job
`labs-mctl-telegram-local-mode-flip-1` declared in
`platform-gitops/services/labs/mctl-telegram/values.yaml` most likely reached
BackoffLimitExceeded (its target account has no active/non-revoked Telegram
session to flip) and, lacking any ArgoCD hook-delete-policy, lingers as a
Degraded resource for up to its 24h `ttlSecondsAfterFinished` - dragging the
whole Application's health down independent of any real deploy regression.
See incident-2932eaa0's design.md in this same proposals tree for the full
diagnosis and fix.

## Confidence: LOW
Same caveat as incident-2932eaa0: inferred from gitops config and the
Application-vs-workload health split, not from a direct live Job status
query.

## Proposed Fix
Apply the same fix as incident-2932eaa0: add
`argocd.argoproj.io/hook: PostSync` and
`argocd.argoproj.io/hook-delete-policy: HookSucceeded,HookFailed` to the
`labs-mctl-telegram-local-mode-flip-1` Job's metadata in
`platform-gitops/services/labs/mctl-telegram/values.yaml`, so a finished run
never lingers as a Degraded resource. This resolves the underlying condition
that made shepherd's post-deploy-verify flag an otherwise-unrelated,
successful merge. No change is needed to the shepherd workflow itself or to
issue-528's code.

## Scope
Minimal - no code or workflow change for issue-528; the only file touched is
the shared `labs/mctl-telegram/values.yaml` (see incident-2932eaa0).
