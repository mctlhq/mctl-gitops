# Tasks: incident-895edee7

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-implement.yaml`,
       remove the workflow-level `synchronization: mutex: name: mctl-gitops-main-writes`
       block from `spec:` (currently around line 43-45).
2. [ ] Add an equivalent `synchronization: mutex: name: mctl-gitops-main-writes`
       block as a field on the `commit-and-push` template (currently around
       line 487), sibling to that template's `script:` key, so only the git
       commit/push step acquires the lock.
3. [ ] Verify the resulting YAML is valid (e.g. `argo lint` or a Kubernetes
       dry-run apply) and that indentation matches other template-level
       fields in the same file.
4. [ ] After merge, trigger a manual run via `mctl_trigger_implementer` (or
       wait for the next 5-minute CronWorkflow tick) and confirm it
       completes without a mutex-wait-related failure.
5. [ ] Confirm concurrent `mctl-agents-run` / `mctl-agents-implement` ticks
       no longer show "Waiting for argo-workflows/Mutex/mctl-gitops-main-writes
       lock" for the full duration of another run in `mctl_list_recent_agent_runs`.
6. [ ] Follow-up (not required for this fix, tracked separately): apply the
       same mutex-scope narrowing to `cwft-mctl-agents-run.yaml` and
       `wft-delete-tenant.yaml`, which share the same workflow-wide lock
       pattern.
