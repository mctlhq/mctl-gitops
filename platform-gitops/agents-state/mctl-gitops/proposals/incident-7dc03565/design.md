# Design: incident-7dc03565

## Diagnosis
The alert "Vmagent has scrape_pool with 0 configured/discovered targets" fires because AlertManager is monitoring a scrape pool configuration that has no targets bound to it. This typically occurs when a scrape_pool definition exists in prometheus.yml or AlertManager rules but the service it targets is either not deployed, not registered in service discovery, or has misconfigured relabeling rules that drop all targets. The monitoring/vmagent service itself does not exist in the deployment (confirmed by service lookup returning "not found"), indicating either (1) the scrape pool is orphaned from a previous deployment, or (2) a Prometheus relabeling rule is filtering out all targets for this pool.

## Proposed Fix
Option A (Recommended): Remove or comment out the vmagent scrape_pool definition from the AlertManager or Prometheus scrape configuration in mctl-gitops Helm values.
- File: platform-gitops/helmfiles/mctl-core/values.yaml (or similar monitoring stack values)
- Field: prometheus.scrape_configs[].job_name or scrape_pool where job_name == "vmagent"
- Action: Delete the entire scrape_pool block OR set enabled: false on the job

Option B (If intentional): If vmagent is meant to run, redeploy the service to monitoring tenant with proper Prometheus annotations for service discovery.

Option A is more likely — remove the orphaned scrape pool definition.

## Confidence: MEDIUM
The root cause is clear (0 targets = misconfigured or orphaned pool), but without access to the full Prometheus and AlertManager configuration files, we cannot pinpoint the exact field to change. The implementer should verify the scrape_pool name matches "vmagent" or similar in the monitoring stack configuration.
