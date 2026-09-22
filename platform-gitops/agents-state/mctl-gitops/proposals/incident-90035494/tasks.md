# Tasks: incident-90035494

1. [ ] Check the status of `mctl-gitops/proposals/incident-5ae3a90e` (same
   target service).
2. [ ] If it is already merged/applied: verify in ArgoCD that
   `labs-mctl-telegram` is Healthy, then close this proposal as a duplicate
   with no further code change.
3. [ ] If it is not yet applied: implement it once, from
   `incident-5ae3a90e` (add `argocd.argoproj.io/hook` +
   `hook-delete-policy` annotations to the `labs-mctl-telegram-local-mode-flip-1`
   Job in `platform-gitops/services/labs/mctl-telegram/values.yaml`, and only
   rename it to `-2` after confirming the DB-side retry is wanted). Do not
   open a second, redundant PR for the same change.
4. [ ] No change is needed in mctl-agents/mctl-gitops shepherd logic itself --
   post-deploy-verify's failure here was correct behavior, not a bug.
