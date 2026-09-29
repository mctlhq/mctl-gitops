# Tasks: incident-90640590

1. [ ] Apply the fix tracked in proposal `mctl-gitops/proposals/incident-2932eaa0`
   (add ArgoCD hook-delete-policy annotations to the
   `labs-mctl-telegram-local-mode-flip-1` Job in
   `platform-gitops/services/labs/mctl-telegram/values.yaml`) - do not
   duplicate the edit if that proposal has already landed it.
2. [ ] Verify the merged PR for issue-528
   (issue-528-feat-context-platform-472-slice-c-produc) is otherwise healthy
   and needs no follow-up of its own.
3. [ ] After the labs-mctl-telegram Application returns to Healthy, confirm
   this workflow_failed alert does not recur on the next shepherd run.
