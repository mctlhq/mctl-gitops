# Design: incident-90639911

## Diagnosis
This shepherd tick drove proposal `issue-705-media-responses-amplify-memory-10x-fetch`
(fingerprint names target service `mctl-telegram`) to a successful merge —
`run-shepherd` and `commit-and-push` both completed. `post-deploy-verify` then
slept 300s and found `argocd/labs-mctl-telegram` newly Degraded (relative to
this workflow's own creation timestamp, 2026-09-28T23:31:49Z), confirmed it
was still Degraded after a further 120s grace period, and failed the
workflow — which is exactly the check's job (see
`cwft-mctl-agents-shepherd.yaml` step 4 doc: catch a merge that broke a
downstream Application, rather than let it surface days later).

Because this run's own proposal explicitly targets `mctl-telegram` and is
about memory usage on media-fetch responses (per the slug), it is the more
plausible of the two flagged shepherd runs to actually be causally connected
to `labs-mctl-telegram` going Degraded (unlike the sibling incident
`argo-mctl-agents-shepherd-744786f6-1790640590`, whose own change targeted the
unrelated `mctl-agents` service). However, per the investigation for sibling
incident `18bc5134-18f5-4959-b594-6f2f2932eaa0`, the Application's own
Deployment/pods have been serving traffic without errors or restarts
throughout the Degraded window — the leading hypothesis there is a stuck
one-shot Kubernetes `Job` resource in that service's manifest, not a broken
Deployment rollout from this merge. This agent has no kubectl/ArgoCD
resource-tree access to confirm that the Job (rather than something this
merge changed) is the actual Degraded resource, so a direct causal link from
`issue-705`'s code change to the Degraded status is NOT confirmed.

## Confidence: LOW
Whether this run's merge caused the degradation, or merely coincided with an
already-independently-failing resource, is not established. The concrete
remediation for the Degraded Application itself is tracked in
`mctl-gitops/proposals/incident-2932eaa0` — do not duplicate that fix here.

## Proposed Fix
No independent code change proposed for this incident. Track and apply the
fix in `mctl-gitops/proposals/incident-2932eaa0` (the primary
`argocd_app_degraded` proposal); once `labs-mctl-telegram` returns to
Healthy, this shepherd run's own change needs no further action — it already
merged successfully, and `post-deploy-verify` only blocks the *workflow's own
success signal*, not the merge itself.

If, after applying `incident-2932eaa0`'s fix and confirming
`labs-mctl-telegram` is Healthy again, the next shepherd tick's
`post-deploy-verify` for a future change to `mctl-telegram` still flags a
newly-Degraded app, that would indicate `issue-705`'s change itself has a
real regression (e.g. the media-fetch memory work not actually landing) and
should be investigated as a separate, fresh incident with its own evidence.

## Scope
None (no file change) beyond what `incident-2932eaa0` already proposes.
