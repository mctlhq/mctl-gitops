# Tasks: incident-2932eaa0

1. [ ] Confirm root cause: check the live status of the
   `labs-mctl-telegram-local-mode-flip-1` Job in namespace `labs` (kubectl or
   ArgoCD UI resource tree for the labs-mctl-telegram Application) and verify
   it is the resource ArgoCD is reporting as Degraded.
2. [ ] Edit `platform-gitops/services/labs/mctl-telegram/values.yaml`: add
   `argocd.argoproj.io/hook: PostSync` and
   `argocd.argoproj.io/hook-delete-policy: HookSucceeded,HookFailed`
   annotations to the `metadata` of the `labs-mctl-telegram-local-mode-flip-1`
   Job under `extraObjects` (~line 538), matching the pattern already used in
   the sibling `vault-cleanup.yaml` in the same directory.
3. [ ] If step 1 confirmed the Job is currently Failed, delete the existing
   stuck Job object in-cluster so the Application returns to Healthy
   immediately instead of waiting for its 24h TTL.
4. [ ] Verify the change looks correct: values.yaml still parses as valid
   YAML, the Job's command/spec are otherwise untouched, and no other
   extraObjects were modified.
5. [ ] After sync, confirm `labs-mctl-telegram` ArgoCD Application health
   returns to `Healthy` and the alert clears.
