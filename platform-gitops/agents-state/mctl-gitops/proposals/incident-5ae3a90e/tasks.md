# Tasks: incident-5ae3a90e

1. [ ] In `platform-gitops/services/labs/mctl-telegram/values.yaml`, open the
   `extraObjects` entry with `metadata.name: labs-mctl-telegram-local-mode-flip-1`
   (kind: Job, `mctl.me/component: local-mode-flip`).
2. [ ] Add `argocd.argoproj.io/hook: Sync` and
   `argocd.argoproj.io/hook-delete-policy: HookSucceeded,HookFailed` under its
   `metadata.annotations` (create the `annotations` map if absent).
3. [ ] Confirm with a human/operator whether the one-shot DB mutation this Job
   performs (flipping telegram account 8745115872 to `mode = 'local'`) still
   needs to run, before proceeding to step 4. If it already succeeded via a
   prior unlogged attempt, stop here and instead delete the stuck
   `local-mode-flip-1` Job out-of-band (kubectl/ArgoCD UI) so its Failed
   status stops blocking Application health.
4. [ ] If a retry is confirmed wanted: rename `metadata.name` (and the
   `local-mode-flip-1` reference in the Job's own labels/comments if any) from
   `labs-mctl-telegram-local-mode-flip-1` to
   `labs-mctl-telegram-local-mode-flip-2`, keeping the rest of the spec
   (image, command, env, securityContext) unchanged.
5. [ ] Verify the diff touches only this one `extraObjects` entry in this one
   values.yaml file.
6. [ ] After merge and sync, confirm in ArgoCD that `labs-mctl-telegram`
   returns to Healthy and the new Job (if renamed) completes successfully or
   is pruned per the hook-delete-policy.
