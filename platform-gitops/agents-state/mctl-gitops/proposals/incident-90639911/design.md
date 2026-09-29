# Design: incident-90639911

## Diagnosis
Same underlying condition as incident-90640590 and incident-2932eaa0: the
labs-mctl-telegram ArgoCD Application was already Degraded before this
workflow's own threshold timestamp (2026-09-28T23:31:49Z), independent of
this run's merged PR (issue-705-media-responses-amplify-memory-10x-fetch).
The most likely root cause is the unconditional, non-hooked one-shot Job
`labs-mctl-telegram-local-mode-flip-1` in
`platform-gitops/services/labs/mctl-telegram/values.yaml`, which most likely
reached BackoffLimitExceeded (its target account has no active/non-revoked
Telegram session to flip) and, lacking any ArgoCD hook-delete-policy, lingers
as a Degraded resource for up to its 24h `ttlSecondsAfterFinished`. See
incident-2932eaa0's design.md in this same proposals tree for the full
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
issue-705's code.

## Scope
Minimal - no code or workflow change for issue-705; the only file touched is
the shared `labs/mctl-telegram/values.yaml` (see incident-2932eaa0).
