# Tasks: incident-89811906

1. [ ] Check whether proposal `mctl-gitops/proposals/incident-89812083`
       (sibling incident argo-mctl-agents-implement-4df6cd9e, same root cause)
       has already been implemented; if so, this proposal is resolved by the
       same change and only needs its acceptance criteria re-verified.
2. [ ] Otherwise: inspect the mctl-agents `implement` Argo
       WorkflowTemplate/CronWorkflow definition in mctl-gitops for how the
       account-2 fallback Claude credential is wired (secret name/key, env
       var), and check the corresponding Vault path / ExternalSecret for a
       current value.
3. [ ] If the account-2 credential is missing or stale, restore it (rotate or
       re-populate the secret) and confirm the ExternalSecret syncs.
4. [ ] If both credentials check out valid, add an Argo Workflow
       `synchronization` semaphore (or equivalent concurrency limit) around
       the `run-implementer` step so concurrent `implement` runs cannot
       exhaust both accounts' rate-limit windows simultaneously.
5. [ ] Note in the PR description that proposals mctl-agents/issue-591 and
       mctl-agents/issue-242 were pushed to `needs-triage` by this failure and
       will need an operator to move them back to `accepted` once the fix is
       verified.
