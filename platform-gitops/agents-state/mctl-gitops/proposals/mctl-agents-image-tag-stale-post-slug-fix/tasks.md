# Tasks: mctl-agents-image-tag-stale-post-slug-fix

1. [ ] In the `mctl-agents` repo, find the earliest released tag that
       contains commit `e316c46341b6fcc3b767a2035c09cee6fcd055d2` (PR #61,
       the slug-collision fix). If no such tag/release exists yet, cut one
       first (or flag this proposal as blocked and stop here).
2. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-run.yaml`,
       change the `image: ghcr.io/mctlhq/mctl-agents:1.17.0` field
       (~line 171) to `ghcr.io/mctlhq/mctl-agents:<tag from step 1>`.
3. [ ] Verify no other `image:` reference to the pre-fix `mctl-agents` tag
       was missed in the same file (there are two `image:` lines in this
       file besides the alpine/git ones — confirm only the `mctl-agents`
       one needs the bump).
4. [ ] Do not modify `agents-state/mctl-gitops/proposals/incident-argo-mct/`.
5. [ ] After merge/deploy, trigger a manual incident-responder run
       (`mctl_trigger_incident_responder`) and confirm it completes with
       status Succeeded, then confirm the next scheduled tick (:15 or :45
       past the hour) also completes Succeeded.
