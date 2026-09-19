# Tasks: incident-89840364

1. [ ] Check whether `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`
   already has the preview-exclusion filter (it may have been applied already via the sibling
   proposal `mctl-gitops/proposals/incident-89840387`). If present, skip to task 4.
2. [ ] Otherwise, in the `post-deploy-verify` template's script, add
   `| select((.metadata.name | endswith("-preview")) | not)` to the jq pipeline that computes `BAD`
   (the initial newly-Degraded check), right after `select(.status.health.status == "Degraded")`.
3. [ ] Apply the same `| select((.metadata.name | endswith("-preview")) | not)` addition to the jq
   pipeline that computes `BAD2` (the 120s post-grace recheck). Leave `degraded_unfiltered.txt`
   unchanged.
4. [ ] Verify the jq expressions are syntactically valid.
5. [ ] No image tag bump needed — ClusterWorkflowTemplate manifest picked up by ArgoCD on sync.
   Confirm the `mctl-gitops` Application syncs cleanly after merge.
