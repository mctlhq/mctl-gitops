# Tasks: incident-93791738

1. [ ] Locate the assert-attempt step in the shepherd workflow template and make it print the exit code and last error lines of each attempt's pod.
2. [ ] Verify the change only alters log output and does not touch secrets or token references.
3. [ ] Confirm the cause for mctl-agents-shepherd-168a17bd; if it was clone-gitops exit 128, defer to the retry change in incident-93791038.
