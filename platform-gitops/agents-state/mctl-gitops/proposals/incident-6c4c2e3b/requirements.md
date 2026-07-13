# Requirements: incident-6c4c2e3b

## Incident
- ID: 6c4c2e3b-0777-43d9-829e-eb15127809f5
- Tenant: monitoring
- Service: (none specified — alert originates from vmagent)
- Alert: Vmagent has scrape_pool with 0 configured/discovered targets
- Created: 2026-07-12T23:45:58.366744Z
- Summary: Vmagent has scrape_pool with 0 configured/discovered targets

## Evidence
### Labels
- source: alertmanager
- type: generic
- tenant: monitoring
- severity: warning
- status: analyzing

### Log Snippet
```
2026-07-13T00:15:58Z controller.VMAgent selected vmnodescrape count=4, invalid rules count=0, namespaced names monitoring/monitoring-victoria-metrics-k8s-stack-cadvisor,monitoring/monitoring-victoria-metrics-k8s-stack-kubelet,monitoring/monitoring-victoria-metrics-k8s-stack-probes,monitoring/monitoring-victoria-metrics-k8s-stack-resources vmagent=monitoring-victoria-metrics-k8s-stack namespace=monitoring
2026-07-13T00:15:58Z controller.VMAgent selected vmpodscrape count=1, invalid rules count=0, namespaced names monitoring/prometheus-pushgateway vmagent=monitoring-victoria-metrics-k8s-stack namespace=monitoring
2026-07-13T00:15:58Z controller.VMAgent selected vmservicescrape count=19, invalid rules count=0, namespaced names argo-workflows/argo-workflows-controller,argocd/argocd-application-controller,argocd/argocd-repo-server,argocd/argocd-server,labs/labs-openclaw-codex-metrics,monitoring/mctl-agent,monitoring/mctl-api,monitoring/mctl-telegram,monitoring/monitoring-victoria-metrics-k8s-stack-core-dns,monitoring/monitoring-victoria-metrics-k8s-stack-grafana,monitoring/monitoring-victoria-metrics-k8s-stack-kube-api-server,monitoring/monitoring-victoria-metrics-k8s-stack-kube-state-metrics,monitoring/monitoring-victoria-metrics-k8s-stack-prometheus-node-exporter,monitoring/monitoring-victoria-metrics-operator,monitoring/prometheus-pushgateway,monitoring/vmagent-monitoring-victoria-metrics-k8s-stack,monitoring/vmalert-monitoring-victoria-metrics-k8s-stack,monitoring/vmalertmanager-monitoring-victoria-metrics-k8s-stack,monitoring/vmsingle-monitoring-victoria-metrics-k8s-stack vmagent=monitoring-victoria-metrics-k8s-stack namespace=monitoring
2026-07-13T00:15:44Z controller.VMAlert selected vmrule count=41, invalid rules count=0, namespaced names monitoring/mctl-agent-cleanup-alerts,...
2026-07-13T00:16:16Z controller.VMAlertmanager no pod needs to be updated vmalertmanager=monitoring-victoria-metrics-k8s-stack namespace=monitoring
```

## Acceptance Criteria
- WHEN the change is applied THEN the alert stops firing for this tenant/service.
