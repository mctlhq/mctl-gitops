# Tasks: incident-72218f49

1. [ ] Locate the argocd-self-managed Application definition and values in mctl-gitops and determine which resources drift from the live state.
2. [ ] If drift is a controller-mutated field, add a minimal ignoreDifferences entry; otherwise fix the single incorrect manifest value. If no cause is found in the repo, make no change.
3. [ ] Verify the change is limited to one field or rule and does not alter sync policy or prune behaviour.
