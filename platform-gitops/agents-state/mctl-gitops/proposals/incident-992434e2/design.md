# Design: incident-992434e2

## Confidence: LOW

Confidence is LOW because vmagent logs were unavailable (0 lines returned for all time windows), so the exact scrape pool name and its origin cannot be confirmed from evidence. The implementer must verify the specific pool before applying the fix.

## Diagnosis

VMAgent fires the VmagentScrapePoolEmpty alert when a configured scrape pool has zero discovered or active targets. This typically means a `ServiceMonitor`, `PodMonitor`, or static scrape config entry exists that no longer matches any running Kubernetes workload in the monitoring namespace. Common causes: (1) a ServiceMonitor whose label selector or namespace selector no longer matches the target service (e.g. the service was renamed, deleted, or its labels changed); (2) a static scrape config referencing a host or IP that no longer exists; (3) a VMAgent additionalScrapeConfigs entry added for a service that was subsequently removed. Because the incident source is AlertManager and the type is generic, no platform skill matched it automatically, which is expected for monitoring-infrastructure alerts. The scrape pool has been empty for at least 30 minutes as of triage time.

## Proposed Fix

Locate and remove or repair the orphaned scrape pool. The fix lives in one of these locations in mctl-gitops:

1. Helm values for the kube-prometheus-stack or victoria-metrics-k8s-stack chart:
   - File: `platform-gitops/helm/monitoring/values.yaml` (or environment-specific overlay)
   - Look for `additionalScrapeConfigs` entries with a `job_name` whose targets no longer exist.
   - Remove the stale entry or update its `static_configs.targets` / `kubernetes_sd_configs` selector.

2. A `ServiceMonitor` or `PodMonitor` custom resource committed to the repo:
   - Directory: `platform-gitops/manifests/monitoring/` (or similar)
   - Find the resource whose `selector.matchLabels` no longer matches a running service.
   - Either delete the manifest or update the selector to match the correct labels.

3. VMAgent CR `additionalScrapeConfigs` secret reference:
   - If scrape configs are injected via a Kubernetes Secret, update the secret source in values.yaml to remove the orphaned job.

Minimal scope: touch only the single scrape pool / ServiceMonitor that is causing the empty-pool condition. Do not alter any other scrape configs.
