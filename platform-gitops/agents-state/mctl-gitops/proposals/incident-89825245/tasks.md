# Tasks: incident-89825245

1. [ ] Check whether proposal mctl-gitops/proposals/incident-cc221e40 has
       already been merged (it makes the identical change). If it has, no
       further gitops change is needed for this proposal — skip to task 3.
2. [ ] Otherwise, in platform-gitops/tenants/labs/values.yaml, under
       tenant.quotas, change limits.cpu from "12" to "14", with a dated
       comment (see incident-cc221e40/design.md for the exact wording).
3. [ ] Verify labs-agent-worker-preview's ArgoCD health so the
       post-deploy-verify gate this alert came from will pass on the next
       run. No changes to the shepherd/issue-364 proposal itself are needed.
