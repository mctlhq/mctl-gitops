# Design: incident-89825245

## Diagnosis
This is a downstream symptom of a separate, already-diagnosed root cause, not an independent
bug in the shepherd or in the proposal it was processing.

I read the actual template
(`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, the
`post-deploy-verify` template, lines ~1016-1170) to confirm the mechanism: `run-shepherd`
succeeded and `commit-and-push` succeeded (the proposal for issue-364 was actually merged
successfully), but the workflow's final `post-deploy-verify` step lists every ArgoCD
Application in the `argocd` namespace whose health flipped to `Degraded` after
`{{workflow.creationTimestamp}}` (2026-09-19T13:29:02Z), waits 120s, and fails the whole
workflow if any are still Degraded. That check is intentionally platform-wide and
time-correlated only, by design (its own comments cite the 2026-05-01 -> 2026-05-07
external-secrets incident this exists to catch, and explicitly note that establishing real
causation — "commit-SHA -> owning-app correlation" — is deferred to a future version). It has
no way to tell "this app broke because of the PR I just merged" from "this unrelated app
happened to start degrading at the same time."

`argocd/labs-agent-worker-preview` is that unrelated app: it is a separate preview worker in
the `labs` tenant with no relationship to the mctl-agents issue-364 proposal this shepherd run
was shepherding. Its Deployment rollout stalled at almost exactly the same time (ArgoCD
Degraded, `updatedAt` around 2026-09-19T13:29-13:33Z) for reasons documented in the sibling
incident/proposal below. The coincidence in timing, not any effect of this merge, is what
tripped the guard.

Root cause and full evidence: incident b1eb40f5-a589-4745-a720-5b64cc221e40, proposal
`mctl-gitops/proposals/incident-cc221e40/` (this same batch). That proposal forces a fresh
rollout of `labs-agent-worker-preview` via a `podAnnotations` restart marker.

I am deliberately NOT proposing any change to the post-deploy-verify check itself (e.g.
narrowing it to apps related to the merged repo/service): that check is a safety net added
specifically because assuming "unrelated" is safe was the cause of a prior multi-day incident.
Weakening it without a human evaluating the tradeoff is out of scope for an auto-accepted
proposal.

## Confidence: LOW
(Causal chain from post-deploy-verify's own source and logs is solid; the reason
labs-agent-worker-preview itself is Degraded is still an open, lower-confidence diagnosis —
see the sibling proposal.)

## Proposed Fix
Same fix as `mctl-gitops/proposals/incident-cc221e40/`: add a `podAnnotations` restart marker
to `platform-gitops/services/labs/agent-worker-preview/values.yaml` to force a fresh rollout
of the stuck Deployment. If that proposal has already been applied by the time this one is
picked up, this proposal is a no-op (check the file for an existing `podAnnotations` entry
before editing again).

```yaml
podAnnotations:
  rollout-restart-at: "2026-09-19T14:11:18Z"
```

No change to `cwft-mctl-agents-shepherd.yaml` or the issue-364 proposal is needed or proposed.

## Scope
Minimal, and shared with the sibling proposal — do not duplicate the edit if it is already
present.
