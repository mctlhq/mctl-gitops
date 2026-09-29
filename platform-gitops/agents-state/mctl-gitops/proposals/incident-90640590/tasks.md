# Tasks: incident-90640590

1. [ ] In `platform-gitops/argo-workflows/cluster-templates/cwft-mctl-agents-shepherd.yaml`,
   extend the existing `post-deploy-verify` bullet in the
   `workflows.argoproj.io/description` annotation (step 4) with a short note:
   this check flags ANY newly-Degraded ArgoCD Application platform-wide, not
   just ones touched by the current run's proposal, by design — a
   `workflow_failed` naming an unrelated app is collateral from an existing
   `argocd_app_degraded` incident, not a new bug. Check for an open incident
   on that app first.
2. [ ] Confirm the file still passes YAML/manifest validation (comment-only
   change; no functional diff expected).
3. [ ] No dependent changes — this run's own proposal (`issue-528-...`) already
   merged successfully and needs no further action here.
