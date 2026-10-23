# Tasks: incident-92766848

1. [ ] Check whether incident-92767461 already changed the post-deploy-verify step; if so, mark this done.
2. [ ] Otherwise apply the same change: skip when nothing merged, else check only the merged service's ArgoCD app.
3. [ ] Verify the change does not weaken the check for a run that did merge a service.
