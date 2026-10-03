# Design: incident-21ed36ff

## Confidence: LOW

## Diagnosis
mctl-agent escalated this because `argocd_app_degraded` / `ArgoCDApplicationOutOfSyncLong`
has no matching skill — it collects the alert but never inspects ArgoCD or gitops state.
Investigation with the tools available to this responder (mctl service-status/logs/config
queries, plus read-only inspection of the mctl-gitops working tree — no kubectl/argocd CLI
access) confirms:

- `admins-openclaw`'s ArgoCD Application is `Healthy` but `OutOfSync`, and was still
  `OutOfSync` when queried well over an hour after the alert fired.
- The `apps` ApplicationSet (`platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`)
  sets `syncPolicy.automated.selfHeal: true` and `prune: true` for every service Application,
  including this one. selfHeal normally corrects drift within a few minutes of the next
  reconcile. An Application that stays `OutOfSync` for 1h+ despite selfHeal being enabled
  is the signature of one of two known ArgoCD failure modes, and this responder cannot
  distinguish between them without a live diff:
  1. A sync attempt is failing validation/apply repeatedly (e.g. a change to an immutable
     field such as a Deployment `selector`, a Service `clusterIP`, or a PVC spec) and the
     `syncPolicy.retry` budget (`limit: 5`, backoff up to 3m) has been exhausted, so ArgoCD
     stops retrying until the next git or cluster change triggers a fresh attempt. The
     currently-running (old) resources stay healthy, which matches the observed
     `Healthy`+`OutOfSync` combination.
  2. Some field on a live resource is being reset by something outside ArgoCD's own apply
     (another controller, a mutating webhook, or a manual `kubectl` change) faster than the
     reconcile loop can correct it, and that field is not covered by this Application's
     `ignoreDifferences` list.
- This repo already has precedent for both classes of this exact symptom on this same
  Application: the `ghcr-credentials` Secret ownership fight (684 reconciliations Degraded,
  fixed by an `ignoreDifferences` entry) and the ExternalSecret `spec.data[]` array-shrink
  bug (#789 / upstream argo-cd#17694, fixed by stating ESO's CRD defaults explicitly in
  `externalsecret-extra.yaml` instead of ignoring the field). Both fixes are already present
  in the current chart/ApplicationSet, so this is very likely a *new*, as-yet-unidentified
  drift source, not a regression of either prior bug.
- No error, warning, or drift-relevant log line was found in the `admins-openclaw` pod logs
  (s3-sync sidecar noise only) — ArgoCD's own reconciliation state is not surfaced there, so
  pod logs cannot narrow this further.
- `mctl_get_service_status` does not expose a resource-level diff, and this responder has no
  `kubectl`/`argocd` CLI access, so the specific drifted resource/field could not be
  identified in this run.

## Proposed Fix
No specific file/field change is proposed here — doing so without seeing the actual diff
would be a guess, and an incident-responder proposal is auto-accepted and applied without
human review, so it must not touch working config on a guess. Instead:

1. An operator or the Tier 2 implementer should run `argocd app diff admins-openclaw`
   (or the ArgoCD UI "App Diff" view) against the app's current target revision to see the
   exact resource and field that differs between git and the live cluster.
2. Once the specific field is known, the fix is almost certainly one of:
   - add a targeted `ignoreDifferences` entry (same pattern as the two existing entries in
     `platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`) if the diff is
     caused by something legitimately mutating the field outside git (webhook/controller
     default), or
   - update `platform-gitops/services/admins/openclaw/values.yaml` (or the shared
     `platform-gitops/helm-charts/base-service` templates, if other tenants share the same
     symptom) so the rendered manifest matches the intended live state, if the diff is a
     stale/incorrect git value.
3. This `argocd_app_degraded` / `ArgoCDApplicationOutOfSyncLong` alert type has no skill in
   mctl-agent at all (per the escalation `analysis`). Once the root cause here is confirmed,
   it is worth adding a builtin or YAML skill that runs `argocd app diff`-equivalent
   inspection automatically so future occurrences do not require human/operator escalation.

## Scope
Diagnostic only in this run — no config changes are proposed, because none could be
verified against a live diff. The Tier 2 implementer's job for this proposal is to obtain
that diff and open a minimal, targeted PR based on it (see tasks.md), not to apply a
speculative change.
