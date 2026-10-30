# Tasks: incident-92767461

1. [ ] Find the shepherd workflow template's post-deploy-verify step in mctl-gitops (search "Listing applications that became Degraded after").
2. [ ] Skip the step when the shepherd summary reports no merge; otherwise check only the merged service's ArgoCD app.
3. [ ] Verify the change does not weaken the check for a run that did merge a service.
