# Tasks: incident-87878910

1. [ ] Locate the mctl-agents Helm chart values file at platform-gitops/services/admins/mctl-agents/values.yaml
2. [ ] Check if volumeMounts exist in the container spec; if missing, add a volumeMount for /workdir/mctl-gitops/platform-gitops/agents-state
3. [ ] Verify that the corresponding volume is defined (either a PVC, emptyDir, or a mount from another service's storage)
4. [ ] If the volume references the mctl-gitops service, ensure the PVC name and namespace are correct
5. [ ] Apply the chart update and trigger an ArgoCD sync to redeploy mctl-agents
6. [ ] Verify that the new mctl-agents pod(s) log no more warnings about state_dir not found
7. [ ] Monitor one implementer workflow run to confirm it completes without timeout
