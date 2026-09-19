# Design: incident-89840364

## Diagnosis
Same root cause as the sibling incident `argo-mctl-agents-shepherd-1ea2ae72-1789840387`
(proposal `mctl-gitops/proposals/incident-89840387`), occurring 23 seconds apart against the same
flagged Application: the shepherd's `post-deploy-verify` step, defined in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, lists ALL
ArgoCD Applications in the `argocd` namespace and fails the whole workflow if ANY Application
transitioned to `Health=Degraded` after the workflow started and is still Degraded after a 120s
grace period — with no scoping to the service/repo this particular tick actually touched. Here,
`run-shepherd` was evaluating a `wait` decision on an unrelated proposal's PR (`mctl-agents#409`,
blocked on review, no merge attempted), yet the workflow still failed because the unrelated
Application `argocd/labs-agent-worker-preview` (team `labs`, a preview environment) flipped to
Degraded during the 300s+120s verify window and had not recovered. `mctl_get_service_status` for
`labs/agent-worker-preview` still reports `Degraded` an hour later, while its own pod logs show
`agent-worker` jobs completing successfully throughout — evidence this is a flaky/false-positive
health signal on an ephemeral preview app, not an outage this shepherd tick caused or could have
caused (this tick made no merge at all).

Because the safeguard is unscoped, any Application anywhere in the `argocd` namespace becoming
newly Degraded during any shepherd tick's ~7-minute verify window fails that tick, regardless of
which service/proposal it was advancing.

No skill matched this incident (analysis field empty), which is expected: this is a workflow/gitops
configuration bug, not a service runtime fault a skill would recognize.

## Proposed Fix
Identical fix to `mctl-gitops/proposals/incident-89840387`: in
`platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, in the
`post-deploy-verify` template's script, exclude preview-environment Applications (name suffix
`-preview`) from the newly-Degraded check in both the initial `BAD` jq pipeline (~line 1119-1125)
and the post-grace `BAD2` recheck pipeline (~line 1133-1139), by adding
`| select((.metadata.name | endswith("-preview")) | not)` right after
`select(.status.health.status == "Degraded")` in each. Leave the unfiltered snapshot
(`degraded_unfiltered.txt`, ~line 1161-1165) untouched.

If proposal `incident-89840387` has already been implemented by the time this proposal is picked
up, this one is a duplicate of the same fix — the implementer should verify the change is already
present in the target file and, if so, treat this task as already satisfied rather than
re-applying it.

## Scope
Minimal. Only touch the two jq filter pipelines (`BAD` and `BAD2`) inside the `post-deploy-verify`
template of this one ClusterWorkflowTemplate. Does not change the safeguard's behavior for
non-preview (production) Applications, and does not touch `degraded_unfiltered.txt`.

## Confidence: MEDIUM
Same basis as `incident-89840387`: based on actual step logs and current file content read at
diagnosis time. Implementer should confirm line numbers/exact surrounding context still match, and
check whether the sibling proposal already applied this exact change.
