# Tasks: incident-43d9e608

1. [ ] Access the vmagent /targets UI (http://vmagent.monitoring.svc.cluster.local:8429/targets) or run `kubectl get vmscrapeconfiguration,vmservicemonitor -n monitoring` to identify the job_name of the scrape pool with 0 configured/discovered targets.
2. [ ] Locate the corresponding manifest in platform-gitops/tenants/monitoring/ (VMScrapeConfig CRD file, VMServiceMonitor CRD file, or vmagent ConfigMap scrape_configs block).
3. [ ] Either delete the orphaned scrape config manifest (and remove it from kustomization.yaml) OR fix its selector so it matches currently running pods/services.
4. [ ] Verify the change locally: confirm no other scrape jobs are affected by the edit.
5. [ ] Commit and push; wait for ArgoCD to sync the monitoring namespace and confirm the alert clears in AlertManager.
