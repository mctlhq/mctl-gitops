# Tasks: incident-6c4c2e3b

1. [ ] Verify which scrape pool has 0 targets: exec into the vmagent pod and query `curl -s http://localhost:8429/api/v1/targets | jq '.data.activeTargets[] | select(.health!="up") | .labels'`, or check the vmagent UI at its service URL; identify the job name with 0 discovered targets.
2. [ ] If the problematic pool is `labs-openclaw-codex-metrics`: check whether the Kubernetes Service `labs/labs-openclaw-codex-metrics` and its backing Deployment exist and have ready pods (`kubectl get endpoints labs-openclaw-codex-metrics -n labs`).
3. [ ] If the service has no endpoints and is no longer needed: locate and delete the corresponding VMServiceScrape manifest in the mctl-gitops repo (likely `platform-gitops/monitoring/vmservicescrapes/labs-openclaw-codex-metrics.yaml` or embedded in a Helm values file), commit, and push to trigger GitOps reconciliation.
4. [ ] If the service should be running: scale or redeploy the `labs-openclaw-codex-metrics` service so it has at least one ready pod with the metrics port exposed and listed in the VMServiceScrape's `spec.endpoints[].port`.
5. [ ] After applying the fix, confirm the alert clears in AlertManager (typically within 2-5 minutes after vmagent re-discovers targets).
