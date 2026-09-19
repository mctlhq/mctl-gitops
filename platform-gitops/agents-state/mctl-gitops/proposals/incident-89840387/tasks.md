# Tasks: incident-89840387

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`, in the
   `post-deploy-verify` template's script, add `| select((.metadata.name | endswith("-preview")) | not)`
   to the jq pipeline that computes `BAD` (the initial newly-Degraded check), right after
   `select(.status.health.status == "Degraded")`.
2. [ ] Apply the same `| select((.metadata.name | endswith("-preview")) | not)` addition to the jq
   pipeline that computes `BAD2` (the 120s post-grace recheck).
3. [ ] Leave the unfiltered snapshot block (`degraded_unfiltered.txt`) unchanged — it must continue
   to include preview apps.
4. [ ] Verify the edited jq expressions are syntactically valid (e.g. `echo '{}' | jq '<expr>'` or
   equivalent local check).
5. [ ] No image tag bump needed — this is a ClusterWorkflowTemplate manifest picked up by ArgoCD on
   sync. Confirm the `mctl-gitops` Application syncs cleanly after merge.
