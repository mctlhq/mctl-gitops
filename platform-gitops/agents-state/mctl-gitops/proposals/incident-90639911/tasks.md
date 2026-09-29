# Tasks: incident-90639911

1. [ ] No independent action for this proposal — apply and verify
   `mctl-gitops/proposals/incident-2932eaa0` first (the primary
   `argocd_app_degraded` fix for `labs-mctl-telegram`).
2. [ ] After `labs-mctl-telegram` is confirmed Healthy, no further action is
   needed here: this run's own change (`issue-705-media-responses-amplify-memory-10x-fetch`)
   already merged successfully.
3. [ ] If a FUTURE shepherd tick touching `mctl-telegram` again fails
   `post-deploy-verify` with `labs-mctl-telegram` newly Degraded (after
   `incident-2932eaa0` is applied and confirmed Healthy), open a fresh
   incident/proposal — that would indicate a real regression in the
   `issue-705` change itself, not this same stuck resource.
