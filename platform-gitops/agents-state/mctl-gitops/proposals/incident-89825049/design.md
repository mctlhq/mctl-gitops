# Design: incident-89825049

## Diagnosis
Same shared root cause and mechanism as incident-89825245 (see that proposal's design.md for
the full read of `post-deploy-verify` in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`): the
shepherd's post-merge safeguard lists every ArgoCD Application in the `argocd` namespace that
became Degraded after this workflow's own creation timestamp (2026-09-19T13:29:22Z), found
`argocd/labs-agent-worker-preview` still Degraded after its 120s grace period, and failed the
whole workflow — even though `labs-agent-worker-preview` (a `labs`-tenant preview worker) has
no relationship to the mctl-agents issue-305 proposal this run was shepherding, and
commit-and-push's own log shows this tick made no proposal-state change at all.

Root cause and full evidence for why `labs-agent-worker-preview` is Degraded: incident
b1eb40f5-a589-4745-a720-5b64cc221e40, proposal `mctl-gitops/proposals/incident-cc221e40/`
(this same batch).

As with incident-89825245, I am not proposing any change to the post-deploy-verify safety net
itself — it is a deliberate, documented tradeoff (see its own comments referencing the
2026-05-01 external-secrets incident) and narrowing it without human review risks
reintroducing the gap it was built to close.

## Confidence: LOW
(Causal chain confirmed from source and logs; root cause of the underlying Degraded app is
still lower-confidence — see the sibling proposal.)

## Proposed Fix
Same fix as `mctl-gitops/proposals/incident-cc221e40/` and `incident-89825245/`: add a
`podAnnotations` restart marker to
`platform-gitops/services/labs/agent-worker-preview/values.yaml` to force a fresh rollout of
the stuck Deployment. If already applied by either sibling proposal, this is a no-op — check
the file first.

```yaml
podAnnotations:
  rollout-restart-at: "2026-09-19T14:11:18Z"
```

No change to `cwft-mctl-agents-shepherd.yaml` or the issue-305 proposal is needed or proposed.

## Scope
Minimal, and shared with both sibling proposals — do not duplicate the edit if it is already
present.
