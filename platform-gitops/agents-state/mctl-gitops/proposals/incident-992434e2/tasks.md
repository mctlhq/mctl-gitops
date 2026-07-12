# Tasks: incident-992434e2

1. [ ] In the mctl-gitops repo, run `kubectl get vmagent -n monitoring -o yaml` (or check the VMAgent CR) to list all configured scrape pools and identify which one has 0 targets. Alternatively, check the VMAgent UI (port-forward to :8429, navigate to /targets) to see the empty pool by name.
2. [ ] Locate the source of the orphaned scrape pool: check `platform-gitops/helm/monitoring/values.yaml` for `additionalScrapeConfigs` entries, and `platform-gitops/manifests/monitoring/` for ServiceMonitor / PodMonitor resources.
3. [ ] Remove the stale scrape config entry or update its selector so it matches existing pods/services. Edit only the single affected file/field.
4. [ ] Commit and push the change to the mctl-gitops main branch (or open a PR if branch protection requires review).
5. [ ] Verify: after the Helm/manifest change is applied, confirm the VmagentScrapePoolEmpty alert clears in AlertManager and the scrape pool no longer appears in the VMAgent /targets UI.
