# Tasks: incident-89812083

1. [ ] Inspect the mctl-agents `implement` Argo WorkflowTemplate/CronWorkflow
       definition in mctl-gitops for how the account-2 fallback Claude
       credential is wired (secret name/key, env var), and check the
       corresponding Vault path / ExternalSecret for a current value.
2. [ ] If the account-2 credential is missing or stale, restore it (rotate or
       re-populate the secret) and confirm the ExternalSecret syncs.
3. [ ] If both credentials check out valid, add an Argo Workflow
       `synchronization` semaphore (or equivalent concurrency limit) around
       the `run-implementer` step so concurrent `implement` runs cannot
       exhaust both accounts' rate-limit windows simultaneously.
4. [ ] Note in the PR description that proposals mctl-agents/issue-242 and
       mctl-agents/issue-591 were pushed to `needs-triage` by this failure and
       will need an operator to move them back to `accepted` once the fix is
       verified — this proposal only addresses the credential/capacity cause,
       not the individual proposals.
