# Tasks: incident-92264810

1. [ ] Find the post-deploy-verify step ("Newly Degraded apps detected") in the shepherd workflow definition and read how it selects apps.
2. [ ] If it checks all ArgoCD apps, scope it to the app(s) of the merged service, or downgrade unrelated Degraded apps to a warning instead of failing the workflow.
3. [ ] If the step is already scoped and this was a one-off transient (labs-portfolio is Healthy now), make no change and note that in the PR or status.
