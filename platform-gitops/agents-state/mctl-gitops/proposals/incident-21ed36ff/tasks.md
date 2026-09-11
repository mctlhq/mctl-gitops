# Tasks: incident-21ed36ff

1. [ ] Run `argocd app diff admins-openclaw` (or open the ArgoCD UI diff for the
   `admins-openclaw` Application) to identify the exact resource kind, name, and field(s)
   that differ between git (`platform-gitops/services/admins/openclaw/values.yaml` rendered
   through `platform-gitops/helm-charts/base-service`) and the live cluster state.
2. [ ] Based on the diff, classify the drift:
   - If a live resource is being mutated by something outside ArgoCD's own apply (a
     controller/webhook default not expressed in git) -> add a minimal, targeted
     `ignoreDifferences` entry for that field in
     `platform-gitops/bootstrap/templates/bootstrap/applicationset-apps.yaml`, following the
     existing `ghcr-credentials` Secret and `external-secrets.io/ExternalSecret` entries as
     the pattern (scope to `group`/`kind`/`name` plus specific `jqPathExpressions`; do not
     add a broad ignore).
   - If git holds a stale or incorrect value (e.g. a resource field that was changed
     manually in-cluster, or a chart template regression) -> update
     `platform-gitops/services/admins/openclaw/values.yaml` (or the shared
     `platform-gitops/helm-charts/base-service` template, only if the same drift is expected
     to recur for other tenants using this chart) so the rendered manifest matches the
     intended state.
3. [ ] Verify the change is minimal — touch only the single field/resource causing this
   alert, do not restructure unrelated parts of the values file or chart.
4. [ ] After the fix lands and syncs, confirm `admins-openclaw`'s ArgoCD Application reports
   `Synced` (not just `Healthy`) to close the loop on the alert.
5. [ ] If step 1 shows this is a systemic pattern affecting other tenants on the
   `base-service` chart (not admins-specific), note that in the PR description so a
   follow-up proposal can be filed for the shared chart.
