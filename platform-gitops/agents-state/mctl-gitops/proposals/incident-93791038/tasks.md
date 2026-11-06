# Tasks: incident-93791038

1. [ ] Find the clone-gitops step in the shared shepherd workflow templates (run-shepherd, commit-and-push) and add a 3-attempt retry with 10s then 30s backoff, printing git stderr on each failure.
2. [ ] Verify the change looks correct and does not alter credential references or secrets.
3. [ ] Apply the same retry wherever else the identical clone-gitops step is defined.
