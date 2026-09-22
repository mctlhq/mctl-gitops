# Design: incident-90035494

## Confidence: LOW

## Diagnosis
This is not an mctl-agents code/orchestrator bug. The shepherd run correctly
merged the one PR that was merge-clean (mctlhq/mctl-agents#442) and correctly
left two others waiting (mctl-gitops#1286 pending review findings,
mctl-telegram#652 sent back for review-fixes) -- none of those touched
labs-mctl-telegram. Its `post-deploy-verify` step then did exactly what it is
designed to do: it polled ArgoCD, found `argocd/labs-mctl-telegram` newly
Degraded, waited out the rolling-update grace period, confirmed it was still
Degraded, and failed the workflow so the incident would surface instead of
being silently swallowed. That gate behaved correctly.

The underlying Degraded condition is the same one reported directly by mctl
incident f79e783d-3400-4fd1-9656-09125ae3a90e (`ArgoCDApplicationDegraded`),
already diagnosed and proposed in `mctl-gitops/proposals/incident-5ae3a90e`:
a one-shot `labs-mctl-telegram-local-mode-flip-1` Job (extraObjects in
`platform-gitops/services/labs/mctl-telegram/values.yaml`) failed against
shared-pg-rw and, lacking an ArgoCD hook annotation, pins the Application's
overall health as Degraded independent of the actual service's health.

## Proposed Fix
Same fix as `mctl-gitops/proposals/incident-5ae3a90e`: add ArgoCD hook
annotations to the `labs-mctl-telegram-local-mode-flip-1` Job (and, if a
retry of its DB mutation is confirmed wanted, rename it to `-2`) in
`platform-gitops/services/labs/mctl-telegram/values.yaml`. No change is
needed in mctl-agents itself -- the shepherd's post-deploy-verify gate is
working as intended and should keep failing loudly on a genuinely Degraded
Application.

This proposal is written separately because it originated from a distinct
incident record, but implementing `incident-5ae3a90e` resolves both. Do not
implement this proposal a second time if that one has already merged; treat
it as a duplicate and skip to verification.

## Scope
None beyond `mctl-gitops/proposals/incident-5ae3a90e`. If that proposal is
already merged/in-flight when this one is picked up, verify
`labs-mctl-telegram` is Healthy in ArgoCD and close this out as a duplicate
with no further change.
