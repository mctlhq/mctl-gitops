# Tasks: incident-92743401

1. [ ] Locate the post-deploy-verify step of the shepherd workflow template (mctl-agents or mctl-gitops).
2. [ ] Skip the step when run-shepherd reported no merge; when it did, filter Degraded apps to the merged service only.
3. [ ] Verify the change reads correctly and does not alter the implement/other workflows' verification.
